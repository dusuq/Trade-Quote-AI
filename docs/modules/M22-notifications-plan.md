# T205 — Notifications Service: Complete Development Plan

**Module:** M22 · **Owner:** Agent 4 (Mobile & Platform / Opus+Sonnet 4.6) · **Support:** Agent 3 (Gemini / Antigravity)
**Deps:** T203 ✅ (Proposal Builder) · **Unblocks:** T204b (E-Sign Web UI), T303 (Payments)
**Bounded Context:** `services/notification-service` · **Phase:** 2

---

## Executive Summary

T205 builds the **Notifications Service** (`services/notification-service`) — the centralized multi-channel messaging engine of TradeQuote AI. The service manages template configuration, personalizes messages with tenant variables, tracks delivery state, and dispatches messages across two channels:

1. **Email** (via SendGrid or Resend SDK)
2. **SMS** (via Twilio SDK)

To facilitate reliable, decoupled delivery, this plan implements a REST API for quote and proposal delivery, template customization, and message delivery audit logs. Because the transactional outbox relay is a future capability, services trigger delivery synchronously using secure service-to-service HTTP requests (fully authorized under ADR-0003).

---

## User Review Required

> [!IMPORTANT]
> **Provider Strategy:** This plan details concrete adapters for **SendGrid** and **Resend** (for Email), and **Twilio** (for SMS). During development, we default to a **Console provider fallback** (`console`) which prints the formatted emails/SMS messages directly to the server logs. This allows full developer validation without requiring active API keys or credentials. Confirm this approach is acceptable.

> [!IMPORTANT]
> **API Webhook Bypass:** Webhook callbacks from Twilio/SendGrid to track SMS/email statuses (e.g. `delivered`, `bounced`) require public endpoint access. This plan introduces a path pattern `/v1/notifications/webhooks/*` which will bypass JWT authentication in the API Gateway.

> [!WARNING]
> **PII Redaction:** Following compliance and data protection guidelines, recipient email addresses and phone numbers must be redacted when logged in system files or published as domain events (e.g., `j***@domain.com` or `+1***4567`). The plain-text values remain securely stored only in the PostgreSQL database under tenant isolation.

---

## Open Questions

> [!IMPORTANT]
> **Q1: Template Engine choice** — For personalizing templates, should we use python's standard library formatting (e.g. `str.format`) or integrate **Jinja2**?
> **Recommendation:** Integrate `jinja2` (added to dependencies). It is the industry standard, handles conditional logic and loops easily, and prevents crashes if a contractor accidentally includes or excludes variables.

> [!IMPORTANT]
> **Q2: Sync vs Async delivery in notification-service** — When a request to `POST /v1/notifications/send` is received, should it block the HTTP thread until SendGrid/Twilio responds, or return immediately and dispatch in the background?
> **Recommendation:** Dispatch in the background using FastAPI's built-in `BackgroundTasks`. The REST API returns a `202 Accepted` status with the message ID immediately. This prevents external API latency (often 1-3 seconds) from hanging the client's proposal-send workflow.

> [!IMPORTANT]
> **Q3: Outbox tracking** — Should the notification-service publish events directly to the DB outbox table, similar to other backend services?
> **Recommendation:** Yes, notification-service should write `notification.message.sent` events into its own SQL database outbox table. This maintains consistency with the domain events convention (§4) for eventual consumer sync.

---

## Architecture Design

### Core Delivery Flow

```mermaid
sequenceDiagram
    participant Client as Web/Mobile Client
    participant GW as API Gateway
    participant upstream as Quote/Proposal Service
    participant NS as Notification Service (T205)
    participant DB as Postgres (RLS)
    participant Provider as SendGrid/Resend/Twilio

    Client->>GW: POST /v1/proposals/{id}/send
    GW->>upstream: Forward Request
    upstream->>upstream: Mark Proposal SENT, emit proposal.document.sent
    upstream->>NS: POST /v1/notifications/send (sync HTTP, tenant_id, ref_id)
    NS->>DB: Insert notification (status: 'queued')
    NS-->>upstream: 202 Accepted (notification_id)
    upstream-->>GW: 200 OK
    GW-->>Client: Success Screen
    Note over NS,Provider: Async Background Task triggers
    NS->>DB: Read tenant settings & templates
    NS->>NS: Render Jinja2 template with variables
    NS->>Provider: Call SendGrid/Twilio API
    Provider-->>NS: Return status + provider message_id
    NS->>DB: Update status to 'sent' (or 'failed'), emit notification.message.sent
```

---

## Database Migration Design

### [NEW] `infra/db/migrations/0010_notifications.sql`

```sql
BEGIN;

-- Custom templates defined by tenants
CREATE TABLE IF NOT EXISTS notification_template (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  name             text NOT NULL,          -- 'quote_delivery', 'proposal_delivery', 'signature_request'
  channel          text NOT NULL,          -- 'email' | 'sms' | 'whatsapp' | 'push'
  subject_template text,                   -- Email subject (null for SMS)
  body_template    text NOT NULL,          -- Message body template (Jinja2)
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_tenant_template_channel UNIQUE (tenant_id, name, channel)
);

-- Core notification ledger
CREATE TABLE IF NOT EXISTS notification_message (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  channel             text NOT NULL,       -- 'email' | 'sms' | 'whatsapp' | 'push'
  recipient           text NOT NULL,       -- Plain-text recipient phone or email
  to_redacted         text NOT NULL,       -- Redacted version for event payloads/logs
  subject             text,                -- Sent email subject
  body                text NOT NULL,       -- Sent message body
  status              text NOT NULL DEFAULT 'queued', -- 'queued' | 'sending' | 'sent' | 'delivered' | 'failed'
  provider_message_id text,                -- Reference ID from Twilio/SendGrid
  error_message       text,                -- Log error if delivery fails
  reference_kind      text,                -- 'quote' | 'proposal' | 'esign'
  reference_id        uuid,                -- ID of associated document
  created_at          timestamptz NOT NULL DEFAULT now(),
  sent_at             timestamptz,
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Indexing
CREATE INDEX IF NOT EXISTS idx_notification_template_lookup ON notification_template(tenant_id, name);
CREATE INDEX IF NOT EXISTS idx_notification_message_tenant ON notification_message(tenant_id);
CREATE INDEX IF NOT EXISTS idx_notification_message_status ON notification_message(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_notification_message_ref ON notification_message(tenant_id, reference_kind, reference_id);
CREATE INDEX IF NOT EXISTS idx_notification_message_created ON notification_message(tenant_id, created_at DESC);

-- Enable RLS (conventions §2)
ALTER TABLE notification_template ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON notification_template;
CREATE POLICY tenant_isolation ON notification_template
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

ALTER TABLE notification_message ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON notification_message;
CREATE POLICY tenant_isolation ON notification_message
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

-- Outbox table (if not exists, for transactional outbox events)
CREATE TABLE IF NOT EXISTS outbox_event (
  event_id        uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  event_name      text NOT NULL,
  event_version   integer NOT NULL DEFAULT 1,
  payload         jsonb NOT NULL,
  actor_id        uuid,
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  correlation_id  uuid,
  causation_id    uuid,
  processed_at    timestamptz
);

ALTER TABLE outbox_event ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON outbox_event;
CREATE POLICY tenant_isolation ON outbox_event
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

INSERT INTO schema_migrations(version) VALUES ('0010') ON CONFLICT (version) DO NOTHING;

COMMIT;
```

---

## Proposed Changes

### Component 1: Scaffold Notification Service (`services/notification-service/`)

#### [NEW] `services/notification-service/pyproject.toml`

Configure dependencies, ruff lint rules, mypy typing configs, and the immutable FastAPI bugbear exception:

```toml
[project]
name = "tradequote-notification-service"
version = "0.1.0"
description = "TradeQuote AI — Notification service for email & SMS dispatch (Module M22)"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.2",
    "jinja2>=3.1",
    "httpx>=0.28.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = [
    "fastapi.Depends",
    "fastapi.Query",
    "fastapi.Path",
    "fastapi.Body",
    "fastapi.Header",
    "fastapi.Cookie",
    "fastapi.Form",
    "fastapi.File",
]

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
check_untyped_defs = true
warn_unused_ignores = true
exclude = ["\\.venv", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

#### [NEW] `services/notification-service/main.py`

Instantiate the FastAPI application on Port 8009 with global middleware and health endpoint.

#### [NEW] `services/notification-service/app/config.py`

Runtime settings matching the Pydantic BaseSettings pattern:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    app_name: str = "TradeQuote AI Notification Service"
    port: int = 8009

    # Providers: "sendgrid" | "resend" | "console"
    provider_email: str = "console"
    # Providers: "twilio" | "console"
    provider_sms: str = "console"

    # API Keys
    sendgrid_api_key: str = ""
    resend_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = "+15550000000"

    # Defaults
    email_from_address: str = "no-reply@tradequote.ai"
    email_from_name: str = "TradeQuote AI"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote"
```

---

### Component 2: Domain Layer (`services/notification-service/app/domain/`)

#### [NEW] `app/domain/models.py`

Entities and Value Objects:

```python
@dataclass(slots=True)
class NotificationTemplate:
    id: UUID | None
    tenant_id: UUID
    name: str
    channel: str
    subject_template: str | None
    body_template: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

@dataclass(slots=True)
class NotificationMessage:
    id: UUID | None
    tenant_id: UUID
    channel: str
    recipient: str
    to_redacted: str
    subject: str | None
    body: str
    status: str
    provider_message_id: str | None = None
    error_message: str | None = None
    reference_kind: str | None = None
    reference_id: UUID | None = None
    created_at: datetime | None = None
    sent_at: datetime | None = None
```

#### [NEW] `app/domain/protocols.py`

Abstract Ports for communication providers and repositories:

```python
class EmailProvider(Protocol):
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        from_email: str | None = None,
        from_name: str | None = None
    ) -> str:
        """Sends an HTML email, returns the provider's message ID."""
        ...

class SmsProvider(Protocol):
    def send_sms(self, to_phone: str, body: str) -> str:
        """Sends an SMS message, returns the provider's message ID."""
        ...

class NotificationRepository(Protocol):
    def save_message(self, message: NotificationMessage) -> NotificationMessage: ...
    def get_message(self, tenant_id: UUID, message_id: UUID) -> NotificationMessage | None: ...
    def list_messages(self, tenant_id: UUID, limit: int = 50) -> list[NotificationMessage]: ...
    def save_template(self, template: NotificationTemplate) -> NotificationTemplate: ...
    def get_template(self, tenant_id: UUID, name: str, channel: str) -> NotificationTemplate | None: ...
```

#### [NEW] `app/domain/events.py`

Domain event schemas mapping 1:1 onto `@tradequote/types`:

```python
def message_sent(
    tenant_id: UUID,
    *,
    notification_id: UUID,
    channel: str,
    template: str,
    to_redacted: str,
    actor_id: UUID | None = None
) -> dict[str, object]:
    """Serializes canonical notification.message.sent payload."""
    return {
        "eventId": str(uuid4()),
        "eventName": "notification.message.sent",
        "eventVersion": 1,
        "tenantId": str(tenant_id),
        "actorId": str(actor_id) if actor_id else None,
        "occurredAt": datetime.now(UTC).isoformat(),
        "payload": {
            "notificationId": str(notification_id),
            "channel": channel,
            "template": template,
            "toRedacted": to_redacted
        }
    }
```

#### [NEW] `app/domain/redact.py`

Privacy helpers for redaction:

```python
def redact_email(email: str) -> str:
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"

def redact_phone(phone: str) -> str:
    cleaned = phone.strip()
    if len(cleaned) <= 4:
        return "****"
    return f"{cleaned[:2]}***{cleaned[-4:]}"
```

---

### Component 3: Application Layer (`services/notification-service/app/application/`)

#### [NEW] `app/application/send_notification.py`

The orchestrator use case:

```python
class SendNotificationUseCase:
    def __init__(
        self,
        repo: NotificationRepository,
        email_provider: EmailProvider,
        sms_provider: SmsProvider,
        outbox_repo: OutboxRepository
    ): ...

    def execute(
        self,
        tenant_id: UUID,
        channel: str,
        recipient: str,
        template_name: str,
        template_vars: dict[str, str],
        reference_kind: str | None = None,
        reference_id: UUID | None = None,
        actor_id: UUID | None = None
    ) -> NotificationMessage:
        # 1. Resolve template (Custom DB template -> Fallback built-in template)
        # 2. Render templates via Jinja2 safely using template_vars
        # 3. Create NotificationMessage domain entity (status: 'queued')
        # 4. Save to repository
        # 5. Return immediately to caller (use case runs inside BackgroundTask)
```

#### [NEW] `app/application/templates_defaults.py`

Standard fallback dictionary strings for Email and SMS delivery.

---

### Component 4: Infrastructure Adapters (`services/notification-service/app/infrastructure/`)

#### [NEW] `app/infrastructure/providers/console.py`

Adapters printing to python console (used for local testing):

```python
class ConsoleEmailProvider:
    def send_email(self, to_email, subject, body_html, from_email=None, from_name=None):
        logger.info(f"[EMAIL SENDER MOCK] To: {to_email} | Subject: {subject}\nBody: {body_html}")
        return f"console-email-{uuid4()}"

class ConsoleSmsProvider:
    def send_sms(self, to_phone, body):
        logger.info(f"[SMS SENDER MOCK] To: {to_phone}\nBody: {body}")
        return f"console-sms-{uuid4()}"
```

#### [NEW] `app/infrastructure/providers/sendgrid.py`

Concrete provider invoking SendGrid's `/v3/mail/send` endpoint securely.

#### [NEW] `app/infrastructure/providers/twilio.py`

Concrete provider invoking Twilio's SMS REST API endpoint.

#### [NEW] `app/infrastructure/repositories.py`

SQLAlchemy repository persisting `NotificationMessage` & `NotificationTemplate` objects under tenant RLS constraint.

---

### Component 5: API Interface (`services/notification-service/app/interface/`)

#### [NEW] `app/interface/routes.py`

FastAPI routes managing message dispatching and templates:

```python
@router.post("/send", status_code=status.HTTP_202_ACCEPTED, response_model=NotificationMessageResponse)
def send_notification(
    body: SendNotificationRequest,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None)
) -> NotificationMessageResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    # Init use case, queue delivery task inside background_tasks
    ...
```

#### [NEW] `app/interface/schemas.py`

Pydantic DTO mapping request and response shapes.

---

### Component 6: API Gateway Integration

#### [MODIFY] [config.ts](file:///d:/TradeQuote%20AI/apps/api-gateway/src/config.ts)

Add `NOTIFICATION_SERVICE_URL` to gateway environment schema:

```diff
   ESIGN_SERVICE_URL: z.string().url().default("http://localhost:8007"),
   AI_SERVICE_URL: z.string().url().default("http://localhost:8008"),
+  NOTIFICATION_SERVICE_URL: z.string().url().default("http://localhost:8009"),
```

Register config mapper:

```diff
     esignServiceUrl: parsed.ESIGN_SERVICE_URL,
     aiServiceUrl: parsed.AI_SERVICE_URL,
+    notificationServiceUrl: parsed.NOTIFICATION_SERVICE_URL,
```

#### [MODIFY] [server.ts](file:///d:/TradeQuote%20AI/apps/api-gateway/src/server.ts)

Proxy `/v1/notifications` traffic to the new service port:

```diff
   registerServiceProxy(app, { prefix: "/v1/signature-requests", upstream: cfg.esignServiceUrl });
   registerServiceProxy(app, { prefix: "/v1/sign", upstream: cfg.esignServiceUrl });
   registerServiceProxy(app, { prefix: "/v1/ai", upstream: cfg.aiServiceUrl });
+  registerServiceProxy(app, { prefix: "/v1/notifications", upstream: cfg.notificationServiceUrl });
```

---

## Verification Plan

### Automated Tests

1. Create a suite under `services/notification-service/tests/`:
   - `test_redact.py`: Ensures PII phone and email redaction logic works.
   - `test_templates.py`: Assures Jinja2 formats strings and gracefully ignores missing parameters.
   - `test_send_notification.py`: Fakes provider delivery, asserts queued state, maps to DB log.
   - `test_tenant_isolation.py`: Emulates cross-tenant requests and guarantees data retrieval leakage is blocked.
2. Run standard syntax validation commands:

```bash
cd services/notification-service
uv sync
uv run ruff check app tests
uv run mypy app
uv run pytest tests/ -v
```

### Manual Integration Validation

1. Run the local gateway and mock databases.
2. Call the notification endpoint directly:

```bash
curl -X POST http://localhost:8000/v1/notifications/send \
  -H "Authorization: Bearer <valid-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "customer@domain.com",
    "channel": "email",
    "template_name": "quote_delivery",
    "template_vars": {
      "customer_name": "Jane Doe",
      "company_name": "ACME Electric",
      "quote_title": "Panel Upgrade",
      "quote_total": "$1,200.00",
      "view_link": "http://localhost:8000/v1/proposals/123/view"
    }
  }'
```

3. Confirm that the server log prints out the correctly rendered template body and stores the transaction log entry in Postgres.
