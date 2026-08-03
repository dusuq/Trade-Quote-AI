# T308b — Integrations: real OAuth/encryption/sync + web UI

**Status: DONE (2026-08-03).** Turns T308's connection-state/token-storage/sync-log scaffold
(see [T30x batch audit](T30x-batch-signoff-audit.md), T308 section) into working QuickBooks/Xero/
Zapier integrations, closing every item that audit flagged as open.

## A note on what this builds on

T303b's audit (`docs/handoffs/T303b-payment-hardening-audit.md`, "Gates" section) recorded that
`scripts/run_all_tests.py` failed on `integration-service` in the same sweep because "its working
tree has uncommitted, in-progress changes (new `providers.py`, `crypto.py`,
`infrastructure/http.py`, a changed `activate_connection` signature)" — apparently a prior,
in-progress attempt at this exact task.

That work does not exist in this session's checkout. `git status` showed `services/integration-service`
completely clean before this task started (only the T308 scaffold, as committed in `6eaaf11`); there
is no `git stash` entry, and `git fsck --unreachable` finds no dangling commit touching any
integration-service path (the two unreachable commits it does find are unrelated auto-stash
artifacts from a `feat/t202b-ai-copilot-web-ui` branch, dated 2026-07-30, containing analytics/
copilot files). The most likely explanation is that it lived only in a different, ephemeral
session's working directory and was never committed — the same "marked DONE with no commit"
failure mode T308's own audit called out. Everything below was built fresh against T308's
committed scaffold, independently of that lost attempt.

## What changed

### 1. Real OAuth2 — QuickBooks + Xero (`app/infrastructure/providers/`, `app/domain/providers.py`)

New domain ports (`app/domain/providers.py`), mirroring the existing Repository Pattern:

- `OAuthProvider` — `build_authorize_url`, `exchange_code`, `refresh`
- `InvoiceSyncClient` — `push_invoice`
- `TokenCipher` — `encrypt`, `decrypt`
- `ProviderTokens` — the plaintext result of an exchange/refresh, never persisted as-is

`QuickBooksProvider` and `XeroProvider` (`app/infrastructure/providers/{quickbooks,xero}.py`)
implement both provider-facing ports against each vendor's real API shape:

- QuickBooks's callback carries the company id (`realmId`) as a query param directly — no
  extra lookup needed, so `exchange_code` reads it straight from `callback_params`.
- Xero's callback carries no organisation id at all (a token can be authorized for multiple
  orgs) — `exchange_code` makes one extra `GET /connections` call after the token exchange to
  discover the connected org's `tenantId`, and raises `ProviderAuthError` if the user granted
  access to none (the consent screen allows that).
- Both rotate the refresh token on every use; `refresh()` returns the new one and the caller
  (`services.push_invoice_sync`) is responsible for persisting it, not just the new access
  token — an easy detail to miss that would otherwise break the *second* refresh silently.
- `push_invoice` sends `Authorization: Bearer <token>` to each vendor's real endpoint shape
  (`POST /v3/company/{realmId}/invoice` for QuickBooks, `POST /api.xro/2.0/Invoices` with an
  `Xero-tenant-id` header for Xero).

Zapier has no `OAuthProvider` — per the task brief it is API-key/webhook-based, not OAuth.
`services.connect_zapier` mints a `secrets.token_urlsafe(32)` signing secret server-side,
encrypts and stores it, and returns it in plaintext **exactly once** in the HTTP response (like
an API key — not retrievable again, only rotatable by calling it again). It also now checks
`conn.provider == "zapier"` before touching the connection, so the endpoint can't be pointed at
a QuickBooks/Xero connection and silently corrupt its stored credential.

### 2. Outbound HTTP — the ADR-0003 pattern, ported (`app/infrastructure/http.py`)

`ProviderHttpClient` is [ADR-0003](../adr/ADR-0003-sync-service-to-service-http.md)'s
`ServiceClient` pattern, ported the same way `esign-service` ported it from `ai-service` (this
repo has no shared Python runtime package) — with one deliberate difference: `ServiceClient`
forwards the gateway's `x-tenant-id`/`x-user-id` identity headers via a fixed `_headers()`
method, because it calls *other TradeQuote services*. `ProviderHttpClient` calls a *third
party* that has never heard of a TradeQuote tenant, so headers are a per-request parameter
(Basic auth for token exchange, Bearer for the accounting API) instead.

Every ADR-0003 rule still holds: an explicit timeout (`upstream_timeout_seconds`, default 10s —
external providers are slower than an internal service), bounded retries with backoff only on
retryable failures (connect errors always; timeouts and 5xx only for GET/HEAD/PUT/DELETE), and
**POST is never replayed after a timeout** — replaying a timed-out invoice push could create it
twice. Every failure is raised as `ProviderHttpError`, never a raw `httpx` exception; provider
modules catch it and re-raise as `ProviderAuthError` (OAuth calls) or `ProviderSyncError`
(the invoice push), so no HTTP-layer type ever reaches `app/application/services.py`.

Error messages never include the request body or headers — verified by a dedicated test
(`test_error_message_never_includes_request_body`) that a Basic-auth header and a refresh token
passed into a failing request don't leak into the raised exception's message.

### 3. Encryption confirmed real (`app/infrastructure/crypto.py`)

The T308 audit's exact open question: *"whether `access_token_encrypted` is actually encrypted
(it may be a column name, not a guarantee)."* It was a column name — `services.py` stored
whatever string the caller handed it, verbatim.

`FernetTokenCipher` (the `cryptography` library's `Fernet` — AES-128-CBC + HMAC-SHA256,
authenticated, with a random IV per encryption) now sits on every write/read path:

- `activate_connection`'s request schema (`ActivateConnectionRequest`) changed from
  `access_token_encrypted: str` (implying the *caller* pre-encrypts — never actually possible,
  since an HTTP client has no way to reach the service's key correctly) to plaintext
  `access_token`/`refresh_token`; the use case now calls `cipher.encrypt()` before the entity,
  and therefore the DB row, ever sees it.
- `complete_oauth_callback` never lets a plaintext token near an HTTP response or log line — it
  goes straight from the provider's token response into `cipher.encrypt()`.
- `push_invoice_sync` decrypts only the token it needs, only in memory, only for the duration
  of the provider call.
- Tokens are never logged anywhere in the new code (checked by re-reading every new file for a
  `print`/`log`/exception-message that could carry one — the closest risk, `ProviderHttpError`
  messages, is covered by the test above).

Verified with real `cryptography`, not just a fake: `tests/test_crypto.py` asserts the
ciphertext is not equal to (and does not contain, as a substring) the plaintext; two
encryptions of the same token differ (random IV) but both decrypt back to the same value; a
different key raises `TokenEncryptionError` (never leaks *why* — no ciphertext echoed); and the
service refuses to start with a missing or malformed key rather than silently storing tokens as
plaintext.

### 4. Actual sync (`app/application/services.py::push_invoice_sync`, new route)

`POST /connections/{id}/sync/push` is the new end-to-end push: it decrypts the stored access
token, refreshes it first if expired or expiring within 60 seconds (persisting the refreshed
credential *before* attempting the push, so a successful refresh is never thrown away by a push
that then fails for an unrelated reason), calls the provider's `push_invoice`, and records the
outcome as a `SyncLog` via the existing `start_sync`/`complete_sync` use cases — success or
failure, never raising for a provider-side failure (only for a request that couldn't even be
attempted, e.g. the connection doesn't exist or isn't active).

The existing `POST /connections/{id}/sync` + `POST /sync/{id}/complete` pair (T308's scaffold)
is left in place for recording a sync performed elsewhere (e.g. a future async worker) — `/sync/push`
is additive, not a replacement.

### 5. OAuth callback — public route, `state`-authenticated (`app/interface/routes.py`, gateway)

`GET /v1/integrations/{quickbooks,xero}/callback` is a new `public_router`, mounted alongside
the existing authenticated `router` in `app/main.py`. The browser lands here straight from the
provider's own redirect — there is no TradeQuote session, no bearer token, nothing but the query
string the provider sends. This is the same trust model as `esign-service`'s
`/v1/sign/{token}` and `proposal-service`'s `/v1/proposals/{id}/view`: something *other* than a
gateway-verified header has to authenticate the request.

The mechanism: `services.start_oauth_connection` mints a random `secrets.token_urlsafe(32)`
nonce, stores it on the (still-pending) connection's `config_json`, and builds
`state = f"{tenant_id}:{connection_id}:{nonce}"` for the provider's authorize URL. The tenant
and connection ids in `state` are just routing — enough to open the right `tenant_session` and
look up the right row — but the nonce is the actual credential, checked with
`secrets.compare_digest` against the value stashed at start time. A forged or replayed `state`
(right ids, wrong or reused nonce) is rejected as `OAuthStateInvalidError` before any provider
call is made, and the callback never distinguishes "no such connection" from "state mismatch" in
its response, matching `esign-service`'s public-route posture of not confirming or denying
anything about a resource to an unauthenticated caller.

The gateway (`apps/api-gateway/src/plugins/auth.ts`) already proxied `/v1/integrations`
authenticated (T308's scaffold), so the new callback paths needed adding to
`PUBLIC_PATH_PATTERNS` — two exact paths, no dynamic segment
(`/^\/v1\/integrations\/(quickbooks|xero)\/callback$/`), the same narrow-scoping discipline as
the existing `/v1/sign/{token}` entry (a broader pattern here would be a real auth bypass, not
just a bug — see that file's own warning comment).

### 6. Found and fixed in passing: every route was dead on the first real HTTP call

Every response-mapping helper in `app/interface/routes.py` — `_conn_response`,
`WebhookResponse(**wh.__dict__)`, `SyncLogResponse(**log.__dict__)` — used `**entity.__dict__` to
unpack a domain entity into a Pydantic response model. Every domain entity
(`IntegrationConnection`, `WebhookSubscription`, `SyncLog`) is `@dataclass(slots=True)`, and a
slotted dataclass instance **has no `__dict__` at all**:

```
>>> @dataclasses.dataclass(slots=True)
... class X: a: int
>>> X(1).__dict__
AttributeError: 'X' object has no attribute '__dict__'
```

This was already true in T308's committed scaffold — not introduced by this task — and would
have thrown on the very first real HTTP request to *any* route in this service. It went
uncaught because the existing 10 tests (still true after this task's 37 additions) exercise
`app/application/services.py` directly against in-memory fakes; none of them go through FastAPI's
routing layer at all. This is exactly the kind of gap this task's "wire the gateway route
end-to-end" item exists to catch, so it's fixed here rather than left for a T308c.

Fixed with `dataclasses.asdict()` (works correctly on slotted dataclasses — it reads fields via
reflection, not `__dict__`), filtered to each response schema's own field set
(`{f: v for f, v in dataclasses.asdict(x).items() if f in Schema.model_fields}`). The filtering
isn't just tidiness: an unfiltered `asdict()` on `IntegrationConnection` would have serialized
`access_token_encrypted`/`refresh_token_encrypted`/`config_json` straight into the connection
list/detail HTTP response — this fix closes that leak path at the same time as the crash.

### 7. Web UI (`apps/web`)

- `apps/web/src/lib/integrations.ts` — typed API client (list/create/oauth-start/zapier-connect/
  revoke/list-sync-logs/push-invoice), following the existing `esign.ts`/`proposal-templates.ts`
  conventions (thin functions over `apiFetch`, a `describe*Error` helper, badge-variant mappers).
- `apps/web/src/components/settings/integrations-manager.tsx` — one card per provider
  (QuickBooks/Xero/Zapier) showing connection status; "Connect" creates a pending connection and
  redirects the browser to the provider's authorize URL (QuickBooks/Xero) or activates in place
  and shows a one-time reveal dialog for the secret (Zapier); "Disconnect" revokes; "Sync
  history" opens a dialog listing `SyncLog` rows with status/external id/error message.
  Also reads the OAuth callback's `?provider=&connected=&error=` redirect and shows a banner,
  then scrubs the query string.
- `apps/web/src/app/(app)/settings/integrations/page.tsx` — new route (the callback's redirect
  target), wrapped in `<Suspense>` per Next.js's requirement for `useSearchParams`.
- `apps/web/src/app/(app)/settings/page.tsx` — links to the new page from the main Settings page.

## Tests (47/47 integration-service, up from 10/10)

- `tests/test_crypto.py` (new, 7 tests) — round-trip, ciphertext-not-a-substring-of-plaintext,
  same-plaintext-differs-per-encryption, wrong-key raises, garbage raises, missing/malformed key
  refuses to construct.
- `tests/test_http.py` (new, 8 tests) — `ProviderHttpClient` against `httpx.MockTransport`: POST
  never retried after a timeout (the one rule that matters most here), GET retried after a
  timeout and after a connect error, 4xx never retried, 5xx retried for idempotent methods only,
  and the request-body/header redaction test.
- `tests/test_providers.py` (new, 10 tests) — QuickBooks/Xero request shape (Basic auth header,
  form-encoded body, Bearer + realm/tenant path or header) and error-translation
  (`ProviderHttpError` → `ProviderAuthError`/`ProviderSyncError`), all via `httpx.MockTransport`
  injected through new constructor parameters (`oauth_http`/`api_http`) added to both provider
  classes for exactly this purpose.
- `tests/test_services.py` — the 4 existing tests that called the old `activate_connection`
  signature were updated (not deleted); 22 new tests added: `TestOAuthFlow` (start creates a
  pending connection + persists the nonce; callback activates and clears the nonce; forged nonce
  and malformed state both rejected; missing connection raises), `TestZapierConnect` (activates +
  returns the secret once; rejects a non-zapier connection), `TestPushInvoiceSync` (success path
  asserts the provider received the *plaintext* token, never ciphertext; expired-token refresh
  persists the new credential; refresh failure and push failure both record a `failed` SyncLog
  without raising; inactive connection raises).

## Gates

- `pytest` (`services/integration-service`): **47/47** green
- `ruff check app tests`: clean
- `mypy app`: clean (`Success: no issues found in 23 source files`)
- `python scripts/check_conventions.py`: OK (no JWT decode in integration-service; ruff+mypy
  config present)
- `apps/api-gateway` (`vitest run`): **39/39** green, 4 new (both callback paths proxy publicly;
  the authenticated `/v1/integrations` surface stays gated; an unlisted provider name under
  `/callback` isn't accidentally public)
- `apps/web`: `tsc --noEmit` clean; `next build` succeeds, 18/18 routes including the new
  `/settings/integrations` page; `vitest run` **149/149** green, 20 new for
  `src/lib/integrations.ts`
- `scripts/run_all_tests.py`'s `SERVICE_DIRS` already listed `services/integration-service` —
  that item from the T308 audit ("this service is not in run_all_tests.py") was already closed
  before this task started; confirmed via `git show HEAD:scripts/run_all_tests.py`, nothing to
  do here.

## Known gaps (stated plainly, not hidden)

- **No live-provider verification.** No QuickBooks/Xero sandbox credentials exist in this
  environment. Every request shape (Basic-auth header, form-encoded token request, Bearer +
  realm/tenant-id API call) is verified against the documented API contracts and exercised via
  `httpx.MockTransport`, not a real OAuth round trip against Intuit or Xero's actual servers.
  This is the same category of gap T303b's audit left open for Stripe/Square, for the same
  underlying reason (no sandbox credentials in this environment).
- **No live Postgres.** The encrypted columns are unchanged `Text` columns
  (`infra/db/migrations/0014_integrations.sql` needed no migration — a `TEXT` column stores
  ciphertext exactly as well as it stored the previous unencrypted string); encryption is
  verified at the application layer (a real `Fernet` round trip in `test_crypto.py`), not against
  an actual database row.
- **The web UI's "Sync history" and "Disconnect" flows are not verified in a live browser.**
  `next build` confirms the page compiles and prerenders; `tsc`/`vitest` confirm the client logic
  is type-correct and unit-tested. This environment's browser-preview tooling could not launch a
  dev server against this repository path (a Windows path-handling issue unrelated to the code
  itself — `pnpm --filter @tradequote/web dev` via the preview tool failed with a Windows
  "filename/directory/volume label syntax" error that plain `npx next build`/`vitest run` via a
  shell did not hit), so no screenshot or live click-through exists for this task. A
  `.claude/launch.json` was added (`name: "web"`) for whoever can run it in an environment
  without that constraint.

## Files changed

**Backend (`services/integration-service`):**
- `app/domain/providers.py` (new) — `OAuthProvider`, `InvoiceSyncClient`, `TokenCipher` ports,
  `ProviderTokens`
- `app/domain/errors.py` — new `TokenEncryptionError`, `OAuthStateInvalidError`
- `app/infrastructure/http.py` (new) — `ProviderHttpClient`, `ProviderHttpError`
- `app/infrastructure/crypto.py` (new) — `FernetTokenCipher`
- `app/infrastructure/providers/{__init__.py,quickbooks.py,xero.py}` (new)
- `app/application/services.py` — `activate_connection` now encrypts (signature changed:
  `access_token_encrypted`/`refresh_token_encrypted` params → `access_token`/`refresh_token` +
  a `cipher` argument); new `start_oauth_connection`, `complete_oauth_callback`,
  `connect_zapier`, `push_invoice_sync`
- `app/interface/schemas.py` — `ActivateConnectionRequest` fields renamed to plaintext; new
  `StartOAuthResponse`, `ZapierConnectResponse`, `PushInvoiceRequest`; `ConnectionResponse`
  gained `token_expires_at` (expiry only, never the token)
- `app/interface/routes.py` — new `oauth/start`, `zapier/connect`, `sync/push` endpoints; new
  `public_router` with the two OAuth callbacks; fixed the `__dict__`-on-a-slotted-dataclass bug
- `app/config.py` — provider URLs/scopes, `integration_token_encryption_key`,
  `upstream_timeout_seconds`/`upstream_max_attempts`, `web_app_url`
- `app/main.py` — mounts `public_router`
- `pyproject.toml` — added `cryptography>=43.0`
- `tests/fakes.py` — `FakeTokenCipher`, `FakeOAuthProvider`, `FakeInvoiceSyncClient`
- `tests/test_services.py`, `tests/test_crypto.py` (new), `tests/test_http.py` (new),
  `tests/test_providers.py` (new)

**Gateway:**
- `apps/api-gateway/src/plugins/auth.ts` — new `PUBLIC_PATH_PATTERNS` entry for the two callbacks
- `apps/api-gateway/test/server.test.ts` — 4 new tests

**Web:**
- `apps/web/src/lib/integrations.ts` (new), `integrations.test.ts` (new)
- `apps/web/src/components/settings/integrations-manager.tsx` (new)
- `apps/web/src/app/(app)/settings/integrations/page.tsx` (new)
- `apps/web/src/app/(app)/settings/page.tsx` — links to the new page

**Tracking:**
- `TASKS.md`, `tracking/PROGRESS-TRACKER.csv` — T308b entry added, rollup counts updated
- `.claude/launch.json` (new) — dev-server config for browser-preview tooling
