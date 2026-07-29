# ADR-0003 — Synchronous service-to-service HTTP: when it's allowed

- **Status:** Accepted
- **Date:** 2026-07-28
- **Author:** Agent 1 (CTO)
- **Context tasks:** T201 (needs it), T307b (misused it), T203 (declined to introduce it)

## Context

Until now this codebase had **zero** synchronous service-to-service HTTP calls. Every service talked
only to its own database and the gateway. T203's design spec recorded that deliberately:

> "this codebase has **zero** existing synchronous service-to-service HTTP calls — no shared client,
> no established retry/timeout pattern, no precedent for partial-failure handling. Introducing that
> machinery for T203 alone is out of proportion to the task."

Two things have since forced the question:

1. **T307b introduced one anyway** — an inline `httpx.post` to analytics-service, fired from inside
   quote-service's open database transaction, with a bare `except httpx.HTTPError` that doesn't even
   catch the likely failure. The CTO audit rejected it and asked for this ADR.
2. **T201 genuinely needs one.** The AI Quote Assistant must look items up in the tenant's pricebook
   and create a quote. It cannot answer the user's request without those calls.

Those two cases look superficially alike and are architecturally opposite. This ADR draws the line.

## Decision

**Synchronous service-to-service HTTP is allowed when the call is part of fulfilling the request,
and forbidden when it is a side effect of it.**

The test is a single question:

> *If this call fails, is the user's request still meaningfully complete?*

- **No → the call is on the critical path.** Synchronous HTTP is correct. The caller is already
  blocking on a user-facing response; a failure is a real failure and should surface as one.
- **Yes → it is a side effect.** Synchronous HTTP is wrong. Use the transactional outbox (the
  `TODO(outbox)` markers already in proposal-service and esign-service mark where it will land).

Applied to the cases at hand:

| Call | Critical path? | Verdict |
| --- | --- | --- |
| ai-service → pricebook-service (match items) | Yes — no prices, no quote | ✅ sync HTTP |
| ai-service → quote-service (create the quote) | Yes — it *is* the deliverable | ✅ sync HTTP |
| quote-service → analytics-service (record an event) | No — the quote is created either way | ❌ outbox (T307b) |

### Mandatory rules for any allowed sync call

A call passing the test above must still use `app/infrastructure/http.py`'s shared client, which
enforces:

1. **An explicit timeout.** No unbounded waits. Default 5s connect+read.
2. **Bounded retries with backoff**, and **only on retryable failures** — connect errors, timeouts,
   and 5xx. Never retry a 4xx; the request was wrong and will be wrong again.
3. **No network I/O inside an open database transaction.** This is what made T307b's version a
   connection-pool hazard rather than merely slow.
4. **Failures mapped to a domain error** (`UpstreamServiceError`), never leaked as a raw
   `httpx` exception, and surfaced to the caller as `502`/`503` — not swallowed.
5. **Identity forwarded, never invented** — pass through the gateway's `x-tenant-id`/`x-user-id`
   exactly as received (conventions §1).

### What this does not authorize

- Chains. A → B → C synchronously is not covered by this ADR; raise it separately.
- Sync calls for anything the caller could reasonably do later, in the background, or not at all.
- Skipping the shared client "just this once" — that's how T307b happened.

## Consequences

**Good:** T201 can be built correctly. The pattern has one implementation with one set of
timeout/retry semantics instead of an inline `httpx.post` per call site. The rule is stated as a
question anyone can apply, not a list of blessed endpoints.

**Bad / accepted:** ai-service is now runtime-coupled to pricebook-service and quote-service — if
either is down, voice-to-quote returns 503. That is the honest behavior (the feature genuinely
cannot work without them), and it is preferable to inventing prices or creating a half-quote.

**Follow-on:** the transactional outbox is now on the critical path for T307b's rework, since this
ADR forecloses the inline-HTTP shortcut it was using.
