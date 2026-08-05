# 🚀 T205 — Notifications Service: CTO/Agent 4 Implementation Prompt

> **How to use:** Paste this entire document into a **new Claude Code session** for **Agent 4** (Opus + Sonnet 4.6).
> It is self-contained — read it fully, then begin implementation.

---

## Your Identity & Context

You are **Agent 4 (Mobile & Platform Lead)** for TradeQuote AI.
You are about to implement **T205: Notifications Service (email + SMS delivery of quotes/proposals)**.

- **Task ID:** `T205`
- **Module:** M22
- **Your lane:** Agent 4 (Opus + Sonnet 4.6)
- **Support:** Agent 3 (Gemini / Antigravity)
- **Dependency:** T203 ✅ (Proposal Builder — done & signed off)
- **Unblocks:** T204b (E-Sign Web UI), T303 (Payments)

---

## Step 1 — Read the Plan

A complete, architecture-level implementation plan has been prepared by Agent 3 and is waiting at:

```
docs/modules/M22-notifications-plan.md
```

**Read it now.** It contains:

- Full architecture sequence flow.
- Database migration schema `0010_notifications.sql` with tables for `notification_message`, `notification_template`, and RLS policies.
- Project configuration (`pyproject.toml` containing ruff/mypy configs, `main.py`, `app/config.py`).
- Domain entities, value objects, ports/protocols, event helpers, and redaction logic.
- Application use cases and Jinja2 rendering default templates.
- Infrastructure adapters for Twilio, SendGrid/Resend, and Console (local testing).
- Interface FastAPI routes, schemas, and gateway configs (to register port 8009).
- Test suite requirements (100% mocked providers in tests).

---

## Step 2 — Read the Conventions

Ensure your implementation complies with:

```
docs/07-SERVICE-CONVENTIONS.md
```

Key rules that apply to `notification-service`:

1. **No JWT decode** — trust `x-tenant-id`/`x-user-id` headers from the gateway. Do not use `import jwt` (CI will fail).
2. **Clean Architecture** — `domain/` → `application/` → `infrastructure/` → `interface/`
3. **Outbox Events** — write event envelopes to `outbox_event` inside the same database transaction as the status update. Event payload must match `@tradequote/types` definition for `notification.message.sent`.
4. **Time** — Use `datetime.now(UTC)` — import `from datetime import UTC`. Do not use `timezone.utc` (CI will fail).
5. **Tooling** — include the FastAPI bugbear exemption in `pyproject.toml`.

---

## Step 3 — Resolve Open Questions

The plan recommends the following decisions. Confirm these or adjust them if needed before you start coding:

1. **Jinja2 Template Engine:** Used for template rendering to allow safe and robust variable interpolation.
2. **FastAPI BackgroundTasks:** Used to queue the external API delivery calls asynchronously. The API will respond with `202 Accepted` immediately so user workflows are never blocked.
3. **Console Provider Fallback:** Default email and SMS provider configurations to `"console"` to allow testing and logging without credentials.

---

## Step 4 — Implement

### Implementation Order

1. **Scaffold Service:** Setup `pyproject.toml`, `main.py`, `app/config.py`.
2. **Database Migration:** Create `infra/db/migrations/0010_notifications.sql`. Apply it to local Postgres database.
3. **Domain Layer:** Define models, protocols, events, and redaction helpers in `app/domain/`.
4. **Application Layer:** Write `send_notification.py` (use case) and `templates_defaults.py`.
5. **Infrastructure Layer:** Build repository adapters, console mocks, and HTTP adapters for SendGrid/Resend and Twilio.
6. **Interface Layer:** Setup FastAPI endpoints (`/send`, `/templates`, `/logs`) in `routes.py` and `schemas.py`, and bind dependencies in `deps.py`.
7. **Gateway Integration:** Register config and proxy routes in `apps/api-gateway/src/config.ts` and `server.ts` to route `/v1/notifications` to Port 8009.
8. **Tests:** Implement unit and integration tests (mocking email/SMS providers). Ensure `ruff check`, `mypy app`, and `pytest` are all green.

---

## Step 5 — Update Tracker

When done:

1. Check the box in `TASKS.md`: `- [x] T205 ...`
2. Update `tracking/PROGRESS-TRACKER.csv`: status → `DONE`, fill end date.

---

**Begin now. Read `docs/modules/M22-notifications-plan.md` first, then start coding.**
