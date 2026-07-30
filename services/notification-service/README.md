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
