# T303b — Payments hardening: canonical Square HMAC + idempotent capture

**Status: DONE (2026-08-03).** Closes the two items T303's re-audit left open (see
[T30x batch audit](T30x-batch-signoff-audit.md) and `TASKS.md`'s T303 entry), plus a real
runtime bug found while writing the tests for the fix, not caused by this task.

## Starting point

T303 was re-audited and signed off on 2026-08-02 with a real test harness (`uv` venv +
SQLite-override `conftest.py`, matching `services/esign-service/tests/conftest.py`'s pattern)
and 12 passing tests pinning the fail-closed webhook behaviour. Its own sign-off note named
three things still owed:

1. Align the Square HMAC to its canonical `notificationUrl + rawBody` scheme (the shipped
   version HMACs the body only — safe, since it still rejects everything without the key, but
   wrong, since it would also reject every genuine Square webhook).
2. An idempotent-capture guard so a replayed webhook delivery can't double-process.
3. Live-provider verification (no sandbox credentials in this environment — still not done,
   see "Known gaps" below).

This audit covers items 1 and 2, plus a bug found in item 3's absence: nobody had exercised
the Stripe **success** path with a real signed payload before, because every existing test
only reached signature *rejection*.

## What changed

### 1. Square: canonical HMAC scheme (`app/interface/routes.py`, `app/config.py`)

`_square_signature_ok` now computes `HMAC-SHA256(notification_url + raw_body, key)`,
base64-encoded, `hmac.compare_digest`-compared — Square's actual scheme, not the body-only
approximation. `notification_url` comes from a new `square_webhook_notification_url` setting
in `app/config.py`, **read from server config only**. It is never taken from a request header:
a header is attacker-controlled, and accepting it there would let a forger simply supply
whatever URL string their own signature was computed against, defeating the check entirely —
the whole point of pinning the URL is that it's a secret the caller doesn't get to choose.

Fail-closed behaviour is preserved and extended: a missing signing key **or** a missing
configured URL both reject with 401, since neither leaves anything correct to verify against.

### 2. Idempotent capture (`app/domain/models.py`, `app/application/services.py`, `app/interface/routes.py`)

New `WebhookEventModel` (`payment_webhook_event` table) with a unique constraint on
`(provider, event_id)`. New `record_webhook_event()` / `DuplicateWebhookEventError` in
`services.py`: callers must record an event before mutating state; a replay raises
`DuplicateWebhookEventError` instead of letting the mutation repeat.

Both webhook handlers now check-and-record via a small `_first_delivery()` helper before
calling `capture_payment` / `fail_payment`. A duplicate delivery still returns 200 (so the
provider stops retrying) but skips the side effect. An event with no id (some deliveries omit
one) has nothing to dedupe against, so it always processes — the guard fails open only in the
one case where failing closed would mean silently dropping legitimate events with no way to
tell them apart.

### 3. Bug found, not caused, by this task: Stripe's "verified" path would 500

Writing the Stripe idempotency test required actually driving a signed webhook through
`stripe_sdk.Webhook.construct_event(...)` for the first time — every prior test only reached
signature *rejection* (400/503), never the success path. That surfaced that
`construct_event` returns a `StripeObject`, and **the installed SDK version's `StripeObject`
does not implement `.get()`** — verified live:

```
>>> event.get("type", "")
AttributeError: get
```

The existing (already-signed-off) handler code was `event.get("type", "")` /
`event.get("data", {}).get("object", {})` throughout — i.e. every genuinely signed,
successfully verified Stripe webhook would have crashed with an unhandled `AttributeError`
inside the route, which FastAPI turns into a 500. Stripe would see the 500, retry, and get the
same 500 again — the event would never actually be processed, and nothing before this task
could have caught it, because no test exercised a *valid* signature. Fixed by calling
`raw_event.to_dict()` immediately after `construct_event` succeeds, before any `.get()` calls.

## Tests (17/17, up from 12/12)

- `tests/test_webhook_security.py` — updated the Square positive-control test to sign with
  the canonical scheme; added `test_square_webhook_rejects_when_no_notification_url_configured`
  and `test_square_webhook_rejects_the_old_body_only_scheme` (a signature computed the pre-fix,
  body-only way must now be rejected).
- `tests/test_webhook_idempotency.py` (new) — `test_stripe_replayed_event_does_not_double_capture`,
  `test_square_replayed_event_does_not_double_capture` (both: seed a pending payment, replay
  the identical signed event twice, assert `capture_payment` ran exactly once and the second
  delivery still 200s), and `test_stripe_events_without_an_id_still_process` (also the test
  that caught the `.to_dict()` bug above — it would raise `AttributeError` without the fix).

## Mutation testing (every new claim, reverted and reproduced)

| Reverted change | Result |
|---|---|
| Square HMAC back to body-only | `test_square_webhook_rejects_the_old_body_only_scheme` **and** `test_square_webhook_accepts_a_correctly_signed_body` fail (`expected 200, got 401`) |
| Idempotency guard disabled (`_first_delivery` always `True`) | Both replay tests fail: `assert 2 == 1` on `capture_payment` call count |
| `.to_dict()` reverted to raw `StripeObject` | `AttributeError: get` reproduced exactly, crashing 2 of 3 idempotency tests |

## Gates

- `pytest`: 17/17 green (`services/payment-service`)
- `ruff check app tests`: clean
- `mypy app`: clean (`Success: no issues found in 12 source files`)
- `python scripts/check_conventions.py`: OK (no JWT decode in payment-service; ruff+mypy
  config present)
- `scripts/run_all_tests.py` full sweep: payment-service pytest/ruff/mypy all PASSED.
  `integration-service` failed in the same sweep run — **pre-existing, unrelated to this
  task**: its working tree has uncommitted, in-progress changes (new `providers.py`,
  `crypto.py`, `infrastructure/http.py`, a changed `activate_connection` signature) that
  aren't part of T303b and weren't touched by it. Not fixed here; flagged for whoever owns
  T308b.
- `apps/api-gateway` (`npm test`): 35/35 green, unaffected — no gateway file was changed by
  this task.

## Known gaps (stated plainly, not hidden)

- **No live-provider verification.** No Stripe/Square sandbox credentials exist in this
  environment. The canonical-scheme fix and the idempotency guard are proven against
  hand-built, correctly-signed test payloads (verified against the real `stripe` SDK's
  signature-verification code path), not an actual webhook delivery from Stripe or Square.
  This remains the one item from T303's original list that no environment here can close.
- **Gateway raw-body preservation — pre-existing, not fixed here.** `T201c`'s entry in
  `TASKS.md` already flagged that `apps/api-gateway/src/proxy.ts` re-serializes the request
  body via `JSON.stringify(request.body)` before forwarding it, so the exact raw bytes Stripe
  and Square sign are not preserved end-to-end through the gateway. Both webhook routes are
  public (gateway skips auth for them) specifically so the *service* can do signature
  verification — but if the gateway itself re-serializes the body before this service ever
  sees it, no signature scheme on either side can succeed, canonical or not. This was true
  before T303b and remains true after it; fixing it means touching the gateway's generic
  proxy path, which is out of this task's scope and affects every proxied route, not just
  payments. Whoever wires a real Stripe/Square account to this gateway needs to fix this
  first, or webhooks will 400 on every genuine delivery.

## Files changed

- `services/payment-service/app/config.py` — new `square_webhook_notification_url` setting
- `services/payment-service/app/domain/models.py` — new `WebhookEventModel`
- `services/payment-service/app/application/services.py` — new `record_webhook_event()` /
  `DuplicateWebhookEventError`
- `services/payment-service/app/interface/routes.py` — canonical Square HMAC, idempotency
  guard on both webhook handlers, `.to_dict()` fix on the Stripe success path
- `services/payment-service/tests/test_webhook_security.py` — canonical-scheme tests
- `services/payment-service/tests/test_webhook_idempotency.py` — new
- `TASKS.md`, `tracking/PROGRESS-TRACKER.csv` — T303b marked DONE
