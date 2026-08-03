# CTO Audit — Batch sign-off: T301b, T302, T303, T304, T305, T306, T308

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-08-02
- **Verdict summary:**

**All seven are now signed off.** The first pass (below) signed off 4, rejected T303, and marked
mobile static-only. A stop-hook challenge made me re-check the two blockers I had *asserted without
testing* — and one was flat wrong. See **"Update — gaps closed"** immediately below; the original
findings are preserved beneath it as the record of what was actually broken.

| Task | What it is | Final verdict |
| --- | --- | --- |
| **T304** | M18 AI Vision | ✅ **Signed off** |
| **T305** | M19 AI OCR | ✅ **Signed off** |
| **T306** | M17 AI Sales Coach | ✅ **Signed off** |
| **T308** | M23 Integrations scaffold | ✅ **Signed off** — mypy fixed here; scope flagged |
| **T303** | M11 Payments (Stripe/Square) | ✅ **Signed off on re-audit** — vuln closed + test harness built; Square scheme + live verify → T303b |
| **T301b** | M13 Mobile backend wiring | ✅ **Signed off on re-audit** — analyze clean, tests pass |
| **T302** | M14 Mobile offline sync engine | ✅ **Signed off on re-audit** — analyze clean, conflict-resolver tested |

**The board lied.** The CSV had all seven at `DONE`. But the building agents' own commit
messages said otherwise: T302/T301b was *"Checkpointing in-progress work, not signing off as
done: no Flutter toolchain"*, and T303 was *"tests/ has no test files beyond an empty
`__init__.py`... not marked complete"*. Something flipped those to `DONE` after the fact. **T308
was `DONE` with no commit at all** — it lived uncommitted in the working tree.

---

## Update — gaps closed (re-audit)

**I made an error in the first pass: I claimed "no Flutter toolchain in this environment" without
testing it. That was false — `flutter`, `dart`, and `uv` are all available.** The correct move was
to run the tools, not assert their absence. On re-audit:

### T301b / T302 — now signed off
- **`flutter analyze`: No issues found** across the whole app, including the new sync engine,
  api_client, and auth flow.
- **`flutter test`: 12 pass.** The first run had **1 failure** — `pumpAndSettle timed out` on the
  Customer CRM screen — caused by T301b itself: the screen was switched from mock data to the live
  `offlineCustomersProvider`, so the test spun on a never-returning network call. This is exactly
  the kind of regression static review cannot see. I rewrote that test to override the provider with
  known data (testing the real async data path), added a loading-state test, and added a
  **conflict-resolver unit suite** that pins T302's money-safety invariant: *even when a
  contractor's offline edit is newer, the server-authoritative money fields (`total_minor`,
  `tax_minor`, `unit_cost_minor`, …) still come from the server* — a stale offline total can never
  clobber the server's recomputed one.
- Remaining (follow-up, not blocking): an on-device offline→online sync cycle against a live
  backend, and secure token persistence (the token is still in-memory only).

### T303 Payments — now signed off, with the security hole closed *and tested*
The rejection stood on two grounds — a critical vuln and zero tests. Both are resolved:
- I built a real **test harness** (`uv sync` venv + a SQLite-override `conftest.py`, the same seam
  every other service uses). payment-service is now in `scripts/run_all_tests.py` — the full sweep
  is **11 services green**.
- **12 tests**, ruff + mypy clean. Six pin the webhook security (Stripe fail-closed without a
  secret → 503; bad signature → 400; Square rejects missing/forged signatures → 401; a correctly
  signed body is accepted), with an autouse guard that fails if any rejection path reaches
  `capture_payment`. **Mutation-tested:** reverting to the pre-fix handlers fails 4 of the 6. Six
  cover the money-object lifecycle (intent → pending, retrievable, duplicate idempotency-key → 409,
  missing tenant → 401, amount validation, invoice draft → issued).
- **Still owed by T303b (recorded, not hidden):** the Square HMAC verifies the **body only**;
  Square's canonical scheme signs `notificationUrl + body`, so real Square webhooks are currently
  *rejected* (fails safe) until aligned. Plus an idempotent-capture guard and live-provider
  verification. None of these is a security hole — the forgery vector is closed and proven.

The sign-offs below the fold describe the original broken state. They stand as the record.

---

---

## ✅ T304 / T305 / T306 — the AI trio (signed off)

All three extend `services/ai-service`. Measured, not taken on trust:

- **305/305 ai-service tests pass**, `ruff` clean, `mypy` clean (56 files), `check_conventions.py` OK.
- **The read-only endpoints are genuinely read-only.** `vision_detection.py`, `ocr_extraction.py`,
  and `sales_coach.py` contain **no** `QuoteCreator` / `create_quote` reference — grepped and
  confirmed. Only the `*-to-quote` variants (`vision_to_quote.py`, `ocr_to_quote.py`) create a
  draft, which is their job, mirroring the existing `voice-to-quote`.
- **The pricebook stays the single source of truth.** OCR surfaces an invoice's *stated* price for
  comparison but never feeds it into pricing — same rule voice/vision already follow.
- **T306 never writes.** The use case holds no `QuoteCreator` at all; an empty suggestion list is a
  valid `200` (a complete quote needs no upsell), which is the right call.

Not verifiable here: live-model output (no `ANTHROPIC_API_KEY`). The parsers are unit-tested
directly against representative payloads, which is the right seam. No web UI — follow-ups exist.

---

## ✅ T308 — Integrations (signed off as a scaffold; I fixed its mypy)

**It was not actually green.** Tests passed (10) and `ruff` was clean, but **`mypy` failed with 4
errors** — a `provider: str` handed to a `Literal["quickbooks","xero","zapier"]` parameter (i.e.
provider validation not enforced at the type boundary), a `direction`/`status` literal mismatch,
and a nullable-datetime assignment. So "development done" did not meet the project's own mypy gate.

I fixed all four at the boundary, which is also the *correct* fix: the Pydantic request DTOs now
use the domain's `ProviderKind` / `SyncDirection` / `Literal["success","failed"]` instead of regex
`str`, so unknown providers are rejected with a 422 **and** the value types straight through to the
use case. Now: **mypy clean, ruff clean, 10/10 tests.**

**Scope, stated honestly:** the title says "QuickBooks/Xero + Zapier + REST API", but
`services.py` makes **no outbound API calls** — no `httpx`, no OAuth exchange, no provider SDK. It
is a *connection-state + token-storage + sync-log* foundation (create/activate/revoke a connection,
store `access_token_encrypted`, record webhooks and sync runs). That's a reasonable phase-1
skeleton, but it is **not** working integrations, and the board should not imply that it is.
Follow-up **T308b** owns the actual provider wiring and a web UI.

Two things to verify in T308b: whether `access_token_encrypted` is *actually* encrypted (it may be
a column name, not a guarantee), and that the service enters the master test sweep — it is **not**
in `scripts/run_all_tests.py`, so "all services green" never covered it (same blind spot as T313).

---

## ❌ T303 — Payments — REJECTED (critical)

This is the most dangerous code in the codebase, it had **zero tests**, and it was marked `DONE`.

### Finding 1 — Stripe webhook fails open (payment-fraud grade)

`POST /v1/payments/webhooks/stripe` is a **public, unauthenticated** gateway route. The handler:

```python
if settings.stripe_webhook_secret:
    event = stripe_sdk.Webhook.construct_event(payload, sig_header, secret)
else:
    event = json.loads(payload)     # ← trusts an unsigned body
```

When the secret is unset, signature verification is **skipped** and the raw JSON is trusted. A
`checkout.session.completed` event with an attacker-chosen `metadata.tenant_id` and `provider_id`
then reaches `capture_payment` — **marking a payment captured with no money received.** The
`tenant_id` is attacker-controlled, so this crosses tenants too.

### Finding 2 — Square webhook has no verification at all

`POST /v1/payments/webhooks/square` (also public) performed **no signature check whatsoever**. It
parsed JSON and, on `payment.completed`, called `capture_payment` using a `tenant_id` read straight
from an attacker-controllable `note` field. The gateway's own justification for making the route
public — *"the payment-service validates provider signatures itself (Stripe-Signature / Square
HMAC)"* — was **false for Square**: the config had `square_webhook_signature_key` but nothing used
it.

### Mitigation applied now (not a full fix)

Leaving an unauthenticated payment-capture endpoint live in `main` is not acceptable, so both
handlers now **fail closed**:

- Stripe: no secret → `503`; the fail-open `json.loads` branch is deleted; a signature mismatch →
  `400`. No path processes an unverified event.
- Square: no key or missing/mismatched `x-square-hmacsha256-signature` → `401`, via a constant-time
  `hmac.compare_digest`. An attacker without the signing key cannot forge a match.

The mitigation **compiles and passes `ruff`**, but payment-service has no test harness or venv, so
**it is not test-verified** and I could not stand the app up (it imports `stripe` at module top).
The Square check also HMACs the **body only**; Square's canonical scheme signs `notificationUrl +
body`, so **T303b must align it** — until then it fails safe (rejects genuine webhooks rather than
accepting forged ones).

**T303 stays rejected.** Money-moving code ships with tests or it does not ship. **T303b** owns: a
real test harness (SQLite-override conftest like every other service), the correct Square scheme,
idempotent capture, and entry into the master sweep.

---

## ⚠️ T301b / T302 — Mobile — static review only

There is **no Flutter toolchain in this environment**, so `flutter analyze` and `flutter test`
cannot run. I did not fabricate a pass. What static review confirms:

- **T301b's port fix is real and correct:** the default base URL is `http://10.0.2.2:8000` —
  `10.0.2.2` is the Android-emulator alias for the host, and `8000` is the gateway (the old `8080`
  was wrong). JWT flows through `Authorization: Bearer` in both `api_client` and `sync_engine`.
- **T302's conflict resolver is sane:** last-write-wins by `updated_at`, with a fixed set of
  server-authoritative fields always taken from the server. Defensible.
- **`test/widget_test.dart` is real** (currency/bps/quote-calc unit tests), not the stale Flutter
  counter default — but it covers pure logic, **not** the new sync engine, api_client, or auth
  flow, which are the actual T301b/T302 deliverables.

One thing to check on a real device (**mobile live-verification follow-up**): the access token
appears to live **in memory only** — no `flutter_secure_storage` or `SharedPreferences` write was
found. For an offline-first app that's a functional gap (a restart would lose auth and strand the
sync queue), not a security hole. Verify before calling M13/M14 done.

**Neither is signed off.** Development looks sound, but "sound on reading" is not the bar for done —
they need a Flutter environment to run analyze + tests + an on-device sync cycle.

---

## Follow-ups spawned

| Task | Owner | Why |
| --- | --- | --- |
| **T303b** | A4 | Payments: real test harness, correct Square HMAC (URL+body), idempotent capture, into the sweep |
| **T308b** | A3 | Integrations: actual QuickBooks/Xero/Zapier API calls + OAuth exchange + web UI; confirm token encryption |
| **Mobile live-verify** | A4 | `flutter analyze` + `flutter test` + on-device offline→online sync; persist the token securely |
