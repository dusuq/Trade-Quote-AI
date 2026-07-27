# CTO Audit — T307b (Analytics: real persistence + event wiring)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-28
- **Built by:** Agent 3 (Antigravity)
- **Verdict:** ❌ **Not accepted — reverted to in-progress.** Real, substantial work landed (the
  migration, RLS policy, SQLAlchemy wiring, and web page are all genuine improvements). But the
  event-producer wiring into `quote-service` has defects that range from "silently produces garbage
  analytics" to "can 500 quote creation," and it violates a convention the guard doesn't check.
  Code left uncommitted in the working tree for rework — nothing was discarded.

## Context

Found while committing T204. T307b had been marked `DONE` in both trackers. Per standing practice
every "done" gets independently re-verified before it's trusted; these are the findings.

## What's genuinely good

- `infra/db/migrations/0007_analytics.sql` exists, uses the reserved number correctly (no collision
  with T204's `0008_esign.sql`), and carries an RLS policy in the established pattern.
- Routes now build a per-request `tenant_session`-scoped `SqlAlchemyAnalyticsRepository` — the
  in-memory `shared_repo` singleton flagged in the T307 audit is gone.
- `apps/web` has a real `/analytics` page; `next build` compiles it (15/15 routes).
- `analytics-service` and `quote-service` both stay pytest/ruff/mypy clean, and
  `check_conventions.py` passes.

## Blocking findings

All of these are in `services/quote-service/app/interface/routes.py::_emit_analytics_event`.

### 1. The "best-effort" guard doesn't actually catch the likely failure — verified

```python
except httpx.HTTPError:
    return
```

`httpx.InvalidURL` does **not** inherit from `httpx.HTTPError` (confirmed at runtime:
`InvalidURL.__mro__` is `[InvalidURL, Exception, BaseException, object]`). So a malformed
`ANALYTICS_SERVICE_URL` — a config typo, an unset env var resolving to something unparseable —
propagates out of a function documented as best-effort and **500s quote creation, send, accept, and
reject**. Analytics being misconfigured must never be able to take down quoting.

### 2. Blocking network I/O inside an open database transaction

`_emit_analytics_event` is called *inside* `with tenant_session(tenant_id) as session:`. A
2-second `httpx.post` timeout therefore holds a pooled Postgres connection open for its full
duration. Under any real concurrency that's connection-pool exhaustion, and it makes the latency of
every write path depend on analytics-service's availability.

### 3. Event names don't match the canonical registry — conventions §4 violation

Emitted: `quote.created`, `quote.sent`, `quote.accepted`, `quote.rejected`.
Canonical (`packages/types/src/events.ts`): `quote.quote.created`, `quote.quote.sent`,
`quote.estimate.accepted`, `quote.estimate.rejected`.

Conventions §4: *"Never invent an event name or payload shape locally."* The producer and the
analytics consumer agree with each other, so tests pass — but both are wrong against the registry,
which is exactly the drift that section exists to prevent. `check_conventions.py` doesn't catch
this (it only enforces the JWT boundary and tooling config), which is itself worth fixing.

### 4. `trade` is derived from the free-text quote title — makes M21's headline feature meaningless

```python
"trade": (quote.title or "general").lower(),
```

M21 is specified as *"close rate, forecast, LTV, **profit by trade**"*. The trade taxonomy is
electrical / plumbing / HVAC. Using the quote's free-text title means every quote becomes its own
"trade" — `"replace 200a panel"`, `"annual boiler service"` — so the trade breakdown degenerates to
one bucket per quote and answers nothing. There is no trade field on the quote today; that's a real
gap to close deliberately (add one, or derive it from the pricebook items), not to paper over.

### 5. `customer_name` is fabricated

```python
"customer_name": f"Customer {str(quote.customer_id)[:8]}",
```

The customer LTV leaderboard will render `Customer 3f2a1b9c`. quote-service genuinely doesn't hold
customer names (customer-service does), which is the actual design problem — inventing a
placeholder hides it behind a feature that looks finished.

### 6. Non-atomic, and introduces a pattern the codebase deliberately avoided

If the HTTP call succeeds and the transaction later rolls back, analytics holds an event for a quote
that doesn't exist. This is precisely what the `TODO(outbox)` markers already in proposal-service
and esign-service are placeholders for.

More broadly: M8's design spec (D2) explicitly recorded that this codebase has **zero** synchronous
service-to-service HTTP calls — *"no shared client, no established retry/timeout pattern, no
precedent for partial-failure handling"* — and declined to introduce that machinery for one task.
T307b introduces exactly it, inside a transaction, with no ADR. If we're adopting sync
service-to-service calls as a pattern, that's an architecture decision that needs an ADR and a
shared client, not an inline `httpx.post`.

## Required to accept

1. Move the emit outside the transaction, and make it genuinely non-blocking (background task or
   outbox) — or adopt the outbox properly.
2. Catch `Exception`, not `httpx.HTTPError`, in a best-effort dispatcher.
3. Use canonical event names from `packages/types`.
4. Resolve `trade` honestly — add a real field or derive it — rather than reusing the title.
5. Stop fabricating `customer_name`; either carry it on the event from a caller that has it, or
   leave it null and have analytics resolve/display accordingly.
6. Write an ADR if sync service-to-service HTTP is the intended pattern.

## Also worth doing

`check_conventions.py` should grow a check that Python event-name literals exist in
`packages/types/src/events.ts`. Finding #3 is the second convention violation this quarter that the
guard couldn't see, and the guard is what makes the conventions real.

## Note on T311

T311 was marked done in the same batch, claiming live-Postgres verification on GCP. That claim
cannot be independently re-run from this machine (no Docker, nothing on 5432), so it is neither
confirmed nor disputed here — it needs its evidence reviewed separately.
