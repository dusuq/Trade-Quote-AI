# T205b — M22 Notifications Web-UI · Implementation Plan

| Field            | Value                                                                    |
| ---------------- | ------------------------------------------------------------------------ |
| **Task**         | `T205b` (or `T205c` — see note below)                                   |
| **Module**       | M22 — Notifications Web-UI (Log, Send, Custom Templates)                 |
| **Owner agent**  | Agent 2 (Sonnet 5)                                                       |
| **Phase**        | Phase 2 — AI + Delivery                                                  |
| **Dependencies** | `T205` ✅ (Backend `services/notification-service` port 8009, CTO-signed-off 2026-07-30) |
| **Date**         | 2026-07-31                                                               |
| **Bounded ctx**  | `apps/web` (Next.js 15, React 19, `@tanstack/react-query`, Tailwind)     |

> **Note on task ID:** `T205b` in `TASKS.md` currently names the **backend hardening** follow-up
> (Agent 4). If the founder wants to keep that scope separate, this web-UI work should be tracked as
> `T205c`. The plan below is identical either way; only the identifier changes.

---

## 1. Problem

`T205` delivered `services/notification-service` — Jinja2-rendered multi-channel messaging (email +
SMS), PII-redacted delivery ledger, per-tenant custom templates, and a transactional outbox — but
explicitly left the web UI out of scope. The API Gateway proxies five endpoints under
`/v1/notifications`, yet nothing in `apps/web` drives them:

1. Contractors cannot see the delivery ledger (queued / sent / failed notifications).
2. Contractors cannot manually send a notification from the web UI.
3. Contractors cannot create or edit custom notification templates.

---

## 2. Backend API Surface (Already Complete & Signed Off)

| Method | Path                             | Status | Purpose                     |
| ------ | -------------------------------- | ------ | --------------------------- |
| POST   | `/v1/notifications/send`         | 202    | Queue + background dispatch |
| GET    | `/v1/notifications/logs`         | 200    | List delivery ledger        |
| GET    | `/v1/notifications/logs/{id}`    | 200    | Single ledger entry         |
| POST   | `/v1/notifications/templates`    | 201    | Upsert custom template      |
| GET    | `/v1/notifications/templates`    | 200    | List custom templates       |

### Response DTOs (mirror field-for-field)

**`NotificationMessageResponse`**:
`id`, `channel`, `to_redacted` (PII-redacted — **never** the raw address), `template_name`,
`subject`, `status` (`queued` | `sending` | `sent` | `failed`), `provider`,
`provider_message_id`, `error_message`, `reference_kind`, `reference_id`, `created_at`, `sent_at`.

**`TemplateResponse`**:
`id`, `name`, `channel`, `subject_template`, `body_template`, `created_at`, `updated_at`.

Built-in default templates (fallback when no custom template exists):
`(quote_delivery, email)`, `(quote_delivery, sms)`, `(proposal_delivery, email)`,
`(proposal_delivery, sms)`, `(signature_request, email)`, `(signature_request, sms)`.

PII: the API **never** returns the raw recipient. `to_redacted` is the only field. The UI must
display it as-is.

---

## 3. Component & File Layout

```
apps/web/src/
├── lib/
│   ├── notifications.ts           # DTO types, API client wrappers, badge/label helpers
│   └── notifications.test.ts      # Vitest unit tests (≥10 tests)
├── components/
│   └── notifications/
│       ├── send-notification-dialog.tsx     # Modal: channel, recipient, template, vars, send
│       ├── notification-detail-dialog.tsx   # Modal: full metadata, error callout, reference link
│       └── notification-template-form.tsx   # Modal: create/edit custom Jinja2 template
└── app/
    └── (app)/notifications/
        ├── page.tsx                # Log list page with status tabs + send action
        └── templates/
            └── page.tsx            # Custom template list page with create/edit action
```

---

## 4. Detailed Specifications

### 4.1 `src/lib/notifications.ts`

**Types** (mirror backend schemas):
- `NotificationChannel = "email" | "sms"`
- `NotificationStatus = "queued" | "sending" | "sent" | "failed"`
- `NotificationMessage` — all fields from `NotificationMessageResponse`
- `NotificationTemplate` — all fields from `TemplateResponse`
- `SendNotificationInput` — mirrors `SendNotificationRequest`
- `UpsertTemplateInput` — mirrors `TemplateUpsertRequest`

**API wrappers** (all take `token: string` as first param, use `apiFetch` from `@/lib/api-client`):
- `sendNotification(token, input)` → `POST /v1/notifications/send`
- `listNotificationLogs(token, limit?)` → `GET /v1/notifications/logs?limit=...`
- `getNotificationLog(token, messageId)` → `GET /v1/notifications/logs/{id}`
- `upsertNotificationTemplate(token, input)` → `POST /v1/notifications/templates`
- `listNotificationTemplates(token)` → `GET /v1/notifications/templates`

**Pure helpers** (unit-tested):
- `statusBadgeVariantForNotification(status)`:
  `queued` → `warning`, `sending` → `secondary`, `sent` → `success`, `failed` → `destructive`
- `channelLabel(channel)`: `email` → `"📧 Email"`, `sms` → `"💬 SMS"`
- `describeNotificationError(err)`: maps `422` → invalid channel/recipient, `404` → template not found, fallback for others

### 4.2 `src/lib/notifications.test.ts`

Follow `src/lib/esign.test.ts` pattern exactly:
- `mockFetchOnce` helper using `vi.stubGlobal("fetch", ...)`.
- Test each API wrapper: correct URL, HTTP method, bearer token, request body shape.
- `sendNotification` specifically: 202 is `ok`, body parsed correctly.
- `statusBadgeVariantForNotification` exhaustive for all four statuses.
- `channelLabel` tested for both channels.
- `describeNotificationError` tested for known status codes + unknown fallback.

### 4.3 `SendNotificationDialog`

- **Props:** `open`, `onClose`, `token`, `onSent`, optional `defaultRecipient?`, `defaultReferenceKind?`, `defaultReferenceId?`
- Uses `Dialog` from `@/components/ui/dialog`.
- **Form fields:**
  - Channel `Select`: email / sms.
  - Recipient `Input` (placeholder adapts to channel).
  - Template name `Select`: populated from `GET /templates` + hardcoded built-in names.
  - Template variables: dynamic key/value pair rows (add/remove). Pre-populate common keys based on template.
  - Optional: Reference kind select + reference ID input.
- **Submit:** `sendNotification(token, ...)`. On 202 → `onSent()` + close. Errors inline.
- **Form reset on close** (prevent stale state — same fix from T204b's `RequestSignatureDialog`).

### 4.4 `NotificationDetailDialog`

- **Props:** `open`, `onClose`, `token`, `messageId`
- Fetches `getNotificationLog(token, messageId)`.
- Shows: channel badge, redacted recipient, template, subject, status badge, provider + provider message ID, reference link (clickable `Link` to `/quotes/{id}` or `/proposals/{id}`), timestamps.
- **If `status === "failed"`**: red-bordered error Card with `error_message`.

### 4.5 `NotificationTemplateForm`

- **Props:** `open`, `onClose`, `token`, `onSaved`, optional `existing?: NotificationTemplate`
- Edit mode: pre-fills name, channel, subject, body from `existing`.
- Create mode: blank form.
- **Fields:** name input, channel select, subject template input (hidden for SMS), body template textarea.
- Help text listing Jinja2 variables: `{{ customer_name }}`, `{{ company_name }}`, `{{ view_link }}`, etc.
- **Submit:** `upsertNotificationTemplate(token, ...)`. On 201 → `onSaved()` + close.

### 4.6 Notifications Log Page (`/notifications`)

- `useAuthGuard()` + TanStack `useQuery` key `["notification-logs"]`.
- Header: "Notifications" + "Send Notification" button + "Manage templates →" link.
- Status filter tabs (client-side): All, Queued, Sent, Failed.
- Table: Channel, Recipient, Template, Subject, Status, Provider, Sent At.
- Row click → `NotificationDetailDialog`.
- Standard loading / error / empty states.

### 4.7 Notification Templates Page (`/notifications/templates`)

- `useAuthGuard()` + TanStack `useQuery` key `["notification-templates"]`.
- Header: "Notification Templates" + "New Template" button.
- "← Back to notification log" link.
- Table: Name, Channel, Subject, Last Updated.
- Row click → `NotificationTemplateForm` in edit mode.

### 4.8 Navigation Update (`nav.tsx`)

Add between Analytics and Settings:
```ts
{ label: "Notifications", href: "/notifications", icon: Bell }
```
Import `Bell` from `lucide-react`.

---

## 5. Definition of Done

- [ ] `src/lib/notifications.ts` DTOs and API client implemented.
- [ ] `src/lib/notifications.test.ts` ≥10 Vitest tests, all green.
- [ ] `SendNotificationDialog` component built with form reset on close.
- [ ] `NotificationDetailDialog` component built with error callout.
- [ ] `NotificationTemplateForm` component built with create/edit modes.
- [ ] Notifications Log page (`/notifications`) with status tabs and table.
- [ ] Notification Templates page (`/notifications/templates`) with list and upsert.
- [ ] Navigation item added (`Bell` icon, `/notifications`).
- [ ] `pnpm --filter @tradequote/web typecheck` clean.
- [ ] `pnpm --filter @tradequote/web test` clean.
- [ ] `pnpm --filter @tradequote/web build` green.
