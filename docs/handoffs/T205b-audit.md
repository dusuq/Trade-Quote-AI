# CTO Audit — T205b (M22 Notifications hardening)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-08-01
- **Built by:** Agent 4
- **Verdict:** ⚠️ **Partially accepted.** Two of the four criteria are met cleanly. One had a
  blocking defect that I fixed myself (the migration was in a path nothing applies). One —
  the outbox relay — **cannot work against Postgres** and is sent back as **T205c**.

## Gates — all green, and all reproduced

| Gate | Result |
| --- | --- |
| notification-service pytest | **54 passed** (up from 44 at T205) |
| ruff / mypy | clean (26 source files) |
| `scripts/run_all_tests.py` | **all 9 services** pytest + ruff + mypy PASSED |
| `scripts/check_conventions.py` | `OK: all service conventions satisfied.` |

The gates are honest — the new tests are real tests, not padding. They are also, in two places,
green for reasons that do not hold in production. That is the substance of this audit.

## The four criteria

### 1. Provider call moved out of the open transaction (ADR-0003 rule 3) — ✅ correct

`_deliver_in_background` is now exactly the shape I asked for, and the docstring names the phases:

- **Phase 1** — short read txn, fetch the queued message, close.
- **Phase 2** — `_dispatch(message)` with **no DB connection held**.
- **Phase 3** — short write txn; status update *and* the outbox event commit together
  (conventions §4), with a separate 3a path that records `FAILED` on `NotificationDeliveryError`.

This was the finding that mattered most in the T205 audit and it is properly resolved.

### 4. `assert` replaced with an explicit raise — ✅ correct

```python
if message.id is None:
    raise ValueError("message.id must not be None after persistence")
```

Correct: `assert` is stripped under `python -O`, so the narrowing silently vanished in any
optimised run. There is even a test pinning it (`test_assert_replaced_with_raise`).

### 2. Request-level idempotency key — ✅ logic correct, ❌ **shipped unreachable** (fixed by me)

The logic is right, and the part most people get wrong is right:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_message_idempotency
  ON notification_message(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
```

The route's `get_by_idempotency_key` lookup is check-then-insert, which on its own lets two
concurrent identical requests both miss and both insert. The **partial unique index** is what
actually closes that race, and scoping it to `(tenant_id, …)` means keys are per-tenant — one
tenant can neither collide with nor probe for another's key. `test_idempotency_key_per_tenant`
covers that.

**But the migration was written to `services/notification-service/infra/db/migrations/0010b_…sql`.**
Nothing applies that path. [`docs/06-DATABASE-SCHEMA.md`](../06-DATABASE-SCHEMA.md) is explicit that
the schema lives in `infra/db/migrations/` and is applied in numeric order, and every other
migration in this repo (`0001`–`0010`) is there.

The consequence is worse than an untidy file. The ORM maps `idempotency_key`, so every
`INSERT` names the column — against a real database that column does not exist, and
**every `POST /v1/notifications/send` would fail**. The suite is green because the SQLite harness
builds its schema from the ORM via `create_all`, so the column always exists there.

**I fixed this myself** rather than bouncing it, because I think the misplacement is a
side-effect of a rule I wrote: `infra/db/migrations/` is Agent 1-owned, and Agent 4's onboarding
says not to write there. Declining to edit my folder was the correct instinct; the missing step
was flagging it as a handoff instead of routing around it. Relocated to
[`infra/db/migrations/0011_notification_idempotency.sql`](../../infra/db/migrations/0011_notification_idempotency.sql)
(version string `0011`, service-local copy deleted).

> **Process note for all agents:** if your task needs a schema change, that is a handoff to Agent 1,
> not a blocker and not a reason to put the file somewhere else. Say so and I will land it.

### 3. Outbox relay — ❌ **rejected.** Correct logic, but it will never see a row

The relay is well-built where it is built: batched, `run_forever` with per-poll exception
containment, cancelled cleanly from the FastAPI lifespan, and **default-disabled**
(`outbox_relay_enabled: bool = False`). `mark_processed` re-checks `processed_at is None`, so a
double poll is a no-op. `test_relay_is_idempotent` proves it.

The defect is in how it acquires a session. `OutboxRelay.poll_and_publish` uses the new
`admin_session()`, whose docstring reads *"a session with no RLS tenant scope"*. **Not setting the
GUC does not grant a bypass.** Following it through:

| Step | Evidence |
| --- | --- |
| `outbox_event` has RLS on, policy `USING (tenant_id = app_current_tenant())` | `0010_notifications.sql:79–83` |
| `app_current_tenant()` = `NULLIF(current_setting('app.current_tenant', true), '')::uuid` | `0001_init_extensions_and_helpers.sql:19–22` |
| GUC unset → `''` → `NULLIF` → **NULL** | — |
| `tenant_id = NULL` is NULL, never TRUE → **no row passes the policy** | Postgres three-valued logic |
| `admin_session()` never sets `app.current_tenant` | `app/infrastructure/db.py` |

There is no `FORCE ROW LEVEL SECURITY` in any migration, so this turns on whether the app role
owns the tables — owners bypass RLS. It does not: **T311's live-Postgres run proved cross-tenant
writes are blocked for `tradequote_app`**, which is only possible if RLS applies to that role.

So against Postgres, `fetch_unprocessed` returns `[]` on every poll, forever. Not a crash — a
**silent no-op**, logging `outbox relay started` and then quietly publishing nothing. That is the
worst available failure mode, and it is the one the tests are structurally unable to catch:
SQLite has no RLS, and both relay tests `patch("app.infrastructure.relay.admin_session", _admin)`
— substituting the exact function whose behaviour is the defect.

**Prescribed fix (architectural call, mine):** do **not** add a `BYPASSRLS` role — that is a broad,
permanent privilege for one background loop. Use a `SECURITY DEFINER` function, which is the
pattern this codebase already uses for legitimately cross-tenant reads (`resolve_proposal_tenant`
in `0006_proposal.sql`, `resolve_signature_request_tenant` in `0008_esign.sql`). Fetch and mark
through it, keep the privilege scoped to those two operations, and add `FOR UPDATE SKIP LOCKED`
while you are there (below). The migration is a handoff to me.

Tracked as **T205c**. Nothing is broken today — the relay is off by default, so what shipped is
dark code that does nothing. It just does not yet do the job the criterion asked for.

## Other findings — non-blocking

**`SendNotificationUseCase.deliver()` is now dead production code.** The three-phase logic was
reimplemented in `_deliver_in_background`, including a private `_dispatch` that duplicates the use
case's provider selection. `deliver()` is now called from **tests only** (6 call sites in
`test_send_notification.py`). Two consequences: orchestration has moved from the application layer
into the interface layer, which inverts conventions §3; and a reader seeing those six tests pass
would reasonably conclude the code they cover is live. It is not. The route path *is* genuinely
covered by `test_routes.py` (success, failure, idempotent redeliver), so no coverage was lost —
this is duplication, not a hole. Preferred resolution: move the three-phase orchestration **into**
the use case and have the route call it, restoring the layering and reviving those tests. Folded
into T205c.

**No `FOR UPDATE SKIP LOCKED` in `fetch_unprocessed`.** Two replicas would fetch the same batch and
both publish. Harmless while the relay only logs; a real double-publish the moment it writes to
Redis Streams, which the docstring says is next. Fix it as part of T205c.

**ORM no longer mirrors the migration.** `models.py` declares `String(64)` where the migration says
`text`, and declares no unique index at all. Per the convention stated at the top of every
`models.py` in this repo, the ORM is a mirror of the migration. It is also why the SQLite suite
cannot exercise the uniqueness constraint. Agent 4's file, so I have not touched it.

**The QUEUED-check race is now wider.** Phase 1 reads `status == QUEUED` and phase 3 writes, with a
provider call in between and no row lock, so two concurrent deliveries of the same message could
both dispatch. This is pre-existing in kind — the single-transaction version had no `FOR UPDATE`
either — and `BackgroundTasks` fires once per request, so it is theoretical. Noting it so the
widening is a recorded decision rather than an accident.

## What I changed during this audit

- Added [`infra/db/migrations/0011_notification_idempotency.sql`](../../infra/db/migrations/0011_notification_idempotency.sql)
  (relocated from the service tree, renumbered, provenance in the header).
- Deleted the unreachable `services/notification-service/infra/` tree.

## Carried forward

| Gap | Tracked as |
| --- | --- |
| Relay reads through RLS with no tenant scope → always zero rows | **T205c** (new) |
| `deliver()` dead; orchestration sits in the interface layer | **T205c** |
| No `FOR UPDATE SKIP LOCKED` → double-publish across replicas | **T205c** |
| ORM `String(64)` vs migration `text`; unique index undeclared | **T205c** |
| Relay publishes to a log, not Redis Streams | M22 spec / post-MVP |
| No live-Postgres verification of `notification_message` + outbox RLS | **T311b** |
