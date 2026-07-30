# M22 — Notifications Service (T205)

**Status:** ✅ Done · **Owner:** Agent 4 (Mobile & Platform) · **Service:** `services/notification-service`
**Deps:** T203 (Proposal Builder) · **Unblocks:** T204b (E-Sign Web UI), T303 (Payments)

The centralized multi-channel messaging engine. It renders a template, records a
delivery ledger row, and dispatches quotes / proposals / signature requests over
**email** (SendGrid or Resend) and **SMS** (Twilio), with a **console** fallback
for local development. Port **8009**, mounted at `/v1/notifications`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/v1/notifications/send` | Queue + dispatch a message → **202 Accepted** |
| GET | `/v1/notifications/logs` | List the delivery ledger (redacted recipients) |
| GET | `/v1/notifications/logs/{id}` | One ledger entry |
| POST | `/v1/notifications/templates` | Upsert a tenant's custom template |
| GET | `/v1/notifications/templates` | List a tenant's custom templates |

### `POST /send` body
```json
{
  "channel": "email",
  "recipient": "customer@domain.com",
  "template_name": "quote_delivery",
  "template_vars": { "customer_name": "Jane", "company_name": "ACME", "view_link": "…" },
  "reference_kind": "quote",
  "reference_id": "<uuid>"
}
```
Returns the queued `NotificationMessageResponse` (status `queued`, **redacted**
recipient). Errors: `401` no tenant · `422` unknown/undeliverable channel or
malformed recipient · `404` unknown template.

## Delivery flow

1. **Request (`queue`)** — validate channel + recipient, resolve the template
   (custom tenant row first, then the built-in default), render it with Jinja2,
   persist a `queued` row, return **202** with the id. The caller's workflow is
   never blocked on a provider.
2. **BackgroundTask (`deliver`)** — in its own transaction: call the channel's
   provider, then write the terminal status (`sent`/`failed`) **and** the
   `notification.message.sent` outbox event together (conventions §4). Idempotent
   — a re-fired task on an already-delivered row is a no-op, so a message is never
   double-sent.

## Key design decisions

1. **202 + BackgroundTask** (plan Q2). External provider latency (1–3 s) must not
   hang the proposal-send workflow. The ledger row is the durable record; delivery
   catches up asynchronously and is observable via `/logs`.
2. **Jinja2 rendering** (plan Q1). Email uses `autoescape=True` so a variable like
   `customer_name` can't inject HTML; SMS uses plain text. Missing variables render
   as empty strings (default `Undefined`) so a contractor's template never 500s.
3. **Transactional outbox** (conventions §4). notification-service is the first
   service to actually persist events to `outbox_event` (earlier services carry a
   `TODO(outbox)`), keyed and RLS-scoped by tenant, ready for a future relay.
4. **PII redaction** (plan §PII Redaction). Recipient email/phone are redacted in
   every event payload and log line (`j***e@domain.com`, `+1***4567`); the plain
   value lives only in the RLS-protected `notification_message.recipient` column
   and is never returned by the API.
5. **Console-by-default providers.** `provider_email`/`provider_sms` default to
   `console`, so the whole service runs and is fully testable with no credentials;
   SendGrid/Resend/Twilio activate purely by config.
6. **Template fallback chain.** Custom `notification_template` row for
   `(tenant, name, channel)` wins; otherwise a built-in default
   (`quote_delivery`, `proposal_delivery`, `signature_request` × email/SMS).

## Architecture (Clean Architecture, conventions §3)

```
domain/         Channel/MessageStatus enums, NotificationMessage/Template value objects,
                EmailProvider/SmsProvider/NotificationRepository/OutboxRepository ports,
                DomainEvent + message_sent(), redact.py, errors.py
application/    render.py (Jinja2), templates_defaults.py, SendNotificationUseCase
                (queue + deliver) — orchestration only, depends on ports
infrastructure/ db.py (tenant_session), models.py (ORM + outbox), repositories.py,
                providers/{console,email_http,twilio}.py
interface/      DTOs + mappers, deps.py (provider selection), routes.py
```

Trusts the gateway's `x-tenant-id`/`x-user-id` headers, never decodes a JWT
(conventions §1). Time is `datetime.now(UTC)` throughout (conventions §6).

## Verification

- `ruff check app tests` — clean
- `mypy app` — clean
- `pytest tests/` — **44 passed** (redaction, templates/rendering, use case, routes, tenant isolation)
- `python scripts/check_conventions.py` — green
- Gateway `pnpm test` — **27 passed** (added `/v1/notifications` auth + proxy test)
- Coverage on domain/application/repositories: **98%**

⚠️ **Not yet verified against live Postgres.** The application-layer tenant
isolation tests run on SQLite; DB-enforced RLS in `0010_notifications.sql` and the
outbox row shape can only be exercised against real Postgres — deferred to the
shared dev-stack verification task, the same standard applied to T204 and T206.
