# CTO Audit — T205 (M22 Notifications)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-30
- **Built by:** Agent 4
- **Verdict:** ✅ **Signed off.** Every claim in the M22 doc was independently re-checked and held.
  PII handling is the best in the codebase — the redaction rule is applied consistently everywhere,
  including places nothing forced it. One real architectural finding (a provider HTTP call inside an
  open transaction) and one gap I fixed while auditing. Neither blocks.

## Independently verified

| Claim | Result |
| --- | --- |
| `pytest` — 44 passed | **44 passed** |
| `ruff check app tests` / `mypy app` clean | clean (25 source files) |
| `check_conventions.py` green | OK |
| Gateway `pnpm test` 27 passed, `/v1/notifications` wired | 27 passed; proxy + auth test present |
| Event matches the canonical registry | `notification.message.sent` payload is exactly `notificationId`/`channel`/`template`/`toRedacted` — matches `NotificationSentPayload` in `packages/types` |
| Migration creates the tables + RLS | `notification_template`, `notification_message`, **`outbox_event`** — RLS `tenant_isolation` on all three, `schema_migrations` row inserted |
| "Runs with no credentials" | `provider_email`/`provider_sms` default to `console`; all API keys default to `""`. No credential anywhere in source |
| "Idempotent — never double-sent" | **True, and correctly scoped.** `deliver()` returns early unless `status == queued`, so a re-fired task is a no-op. The doc claims exactly this and no more |
| Tests never touch a network | Providers are replaced by in-memory fakes in `conftest.py` |

### PII redaction — verified end to end, and better than required

This is the part worth calling out. The rule isn't just implemented, it's implemented *consistently*:

- `recipient` appears only in the **request** DTO. Every response carries `to_redacted` only.
- The raw value lives solely in the RLS-protected `notification_message.recipient` column.
- `redact_email` falls back to opaque redaction when there's no `@`, so a malformed value cannot slip
  through unredacted — a defensive default, not the happy path.
- `redact_for_channel` redacts an *unknown* channel opaquely rather than passing it through.
- **The console provider redacts in its own log line too.** Nothing forced that — it's a dev-only
  mock — and it's the difference between a PII rule and a PII habit.

I went looking for the usual failure (raw address in a log line on the default provider) and it
isn't there.

### Transactional outbox — genuinely first

`outbox_event` is real, RLS-scoped, and written in the same transaction as the terminal status
update. Every prior service carries a `TODO(outbox)`; this is the first one to actually land it.
That also matters beyond T205: it's the mechanism T307b's rework needs, since ADR-0003 forecloses
the inline-HTTP shortcut it was using.

## Finding — non-blocking: the provider call runs inside an open transaction

`_deliver_in_background` wraps the whole delivery in one transaction:

```python
with tenant_session(tenant_id) as session:
    _use_case(session).deliver(...)     # -> _dispatch() -> SendGrid/Twilio HTTP
```

So a pooled Postgres connection is held for the provider call's full duration — up to
`provider_timeout_seconds` (default **10s**). This is [ADR-0003](../adr/ADR-0003-sync-service-to-service-http.md)
rule 3: *no network I/O inside an open database transaction*. Rule 3 is stated generally, not
scoped to internal services, and a third-party provider is exactly the kind of call that hangs.

**Why it's not blocking:** it's in a BackgroundTask, so no user-facing latency, and correctness is
unaffected. The cost is resource contention — a burst of notifications, or one slow provider, pins
connections for seconds at a time. That's the hazard rule 3 exists to prevent, arriving through a
different door than T307b's.

**Why the current shape is understandable:** the docstring justifies the single transaction on the
grounds that the status update and the outbox event must commit together (conventions §4). That
requirement is real — but it constrains the *write*, not the network call. The two aren't in
conflict; the design just conflates them.

**Fix** — the same shape as `ai-service`'s `_run_metered`: short transaction to read the row, close
it, call the provider, then a short transaction to write status + outbox **together**. Atomicity
preserved, no connection held across the network.

## Nit

`send_notification` uses `assert message.id is not None` for type narrowing. Under `python -O`
asserts are stripped, so a `None` id would reach the scheduler instead of failing loudly. Cosmetic —
`queue()` always persists first — but a narrowing `if ... raise` is free.

## Fixed during this audit

**`notification-service` was not registered in `scripts/run_all_tests.py`**, so the sweep that
reports "all Phase 1 service test and lint suites passed" silently did not cover it. Added. The
sweep now runs 9 services and is green across all of them — the T205 verification claim was true,
but the *sweep* backing it was under-reporting scope, which is worse than a failing test because it
reads as coverage.

## Carried-forward gaps (declared, not discovered)

| Gap | Tracked as |
| --- | --- |
| RLS + outbox row shape never run against live Postgres (the doc says so plainly) | **T311b** |
| No request-level idempotency key — a client retrying `POST /send` after a timeout produces two ledger rows, each delivered once | **T205b** (new) |
| No outbox relay yet — events are persisted but nothing publishes them | **T205b** |

The idempotency gap is the same class as T201's and is stated here for the same reason: `deliver()`
is idempotent per row, which is what the doc claims; duplicate *requests* are a separate problem
that needs a dedupe key to solve properly.
