# notification-service (M22 / T205)

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6
- **Bounded Context / Purpose:** Multi-channel messaging

Centralized messaging for TradeQuote AI — delivers quotes, proposals, and
signature requests over **email** (SendGrid / Resend) and **SMS** (Twilio),
with a **console** fallback for local development.

- Port **8009**, mounted at `/v1/notifications` through the API gateway.
- Clean Architecture (`domain/` → `application/` → `infrastructure/` → `interface/`).
- `POST /send` renders a Jinja2 template, persists a `queued` ledger row, returns
  **202** immediately, and dispatches the provider call in a FastAPI
  `BackgroundTask` so the caller's workflow never blocks on provider latency.
- On delivery the status update and the `notification.message.sent` outbox event
  are written in **one transaction** (conventions §4).
- Recipient email/phone are **redacted** in every event and log
  (`j***e@domain.com`, `+1***4567`); plain values live only in Postgres under RLS.

## Delivery and the outbox relay

Delivery is **three phases across three short transactions** (ADR-0003 rule 3):
read the queued row, call the provider with **no** DB connection held, then write the
terminal status and the outbox event together. The decisions live in
`SendNotificationUseCase`; the route only sequences the transactions.

`POST /send` accepts an optional `idempotency_key`. The route's lookup is
check-then-insert, so the thing that actually closes the race is the **partial unique
index** on `(tenant_id, idempotency_key)` (`0011`) — tenant-scoped, so one tenant's key
can never collide with or be probed from another's.

The relay reads the outbox across every tenant, which RLS forbids by default. It goes
through **SECURITY DEFINER** functions (`0012`), *not* an un-scoped session:

> Leaving `app.current_tenant` unset grants no bypass. `app_current_tenant()` returns
> NULL, `tenant_id = NULL` is never TRUE, and the table simply looks empty. That was the
> T205b defect — the relay ran, logged that it had started, and published nothing.

`outbox_claim_unprocessed` uses `FOR UPDATE SKIP LOCKED`, so two replicas take disjoint
batches rather than both publishing the same events. The relay is **off by default**
(`OUTBOX_RELAY_ENABLED=false`) and currently publishes to the log; Redis Streams is next.

⚠️ Those functions and the RLS they exist to work around are **Postgres-only**. The
SQLite test harness cannot exercise either, so the relay's suite proves the batching and
marking logic, not that it can see a row in production — tracked as **T311b**.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/v1/notifications/send` | Queue + dispatch a message (202 Accepted) |
| GET | `/v1/notifications/logs` | List delivery ledger (redacted recipients) |
| GET | `/v1/notifications/logs/{id}` | One ledger entry |
| POST | `/v1/notifications/templates` | Upsert a tenant's custom template |
| GET | `/v1/notifications/templates` | List a tenant's custom templates |

## Local checks

```bash
cd services/notification-service
uv sync
uv run ruff check app tests
uv run mypy app
uv run pytest tests/ -v
```
