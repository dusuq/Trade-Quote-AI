# 03 — Domain-Event Registry & Conventions

The canonical, machine-checked contract lives in
**[`packages/types/src/events.ts`](../packages/types/src/events.ts)** (`@tradequote/types`).
This document is the human-readable companion. **Agent 1 (CTO) owns all changes here.**

---

## Naming convention

```
<context>.<aggregate>.<pastTenseVerb>
```

- lowercase `context`, camelCase `aggregate`/`verb`
- past tense only — events describe facts that already happened
- examples: `quote.estimate.accepted` · `proposal.document.signed` · `payment.deposit.captured`

Validated at runtime by `isValidEventName()` and enforced at compile time by the `DomainEventName` union.

## Envelope (every event)

| Field            | Type              | Notes                                                   |
| ---------------- | ----------------- | ------------------------------------------------------- |
| `eventId`        | UUID              | dedupe / idempotency key                                |
| `eventName`      | `DomainEventName` | canonical name                                          |
| `eventVersion`   | number            | payload schema version, starts at 1                     |
| `tenantId`       | UUID              | **consumers MUST filter by this — never cross tenants** |
| `actorId`        | UUID \| null      | `null` = system/automation                              |
| `occurredAt`     | ISO-8601 UTC      | when it actually happened                               |
| `correlationId?` | UUID              | groups all events in one business transaction           |
| `causationId?`   | UUID              | the event that directly caused this one                 |
| `payload`        | typed             | per-event, see registry                                 |

**Money rule:** always `{ amountMinor: integer_cents, currency: ISO-4217 }`. Never floats.

## Registry (v1)

| Event                           | Producer        | Key payload                             |
| ------------------------------- | --------------- | --------------------------------------- |
| `auth.tenant.created`           | auth            | tenantId, name, plan                    |
| `auth.user.invited`             | auth            | userId, email, role                     |
| `customer.customer.created`     | customer        | customerId, displayName                 |
| `customer.property.added`       | customer        | customerId, propertyId, geo?            |
| `lead.lead.captured`            | customer(lead)  | leadId, source, score                   |
| `pricebook.item.upserted`       | pricebook       | itemId, kind, sku, unitCost             |
| `quote.quote.created`           | quote           | quoteId, customerId, createdVia         |
| `quote.quote.lineItemsChanged`  | quote           | quoteId, lineItemCount, subtotal        |
| `quote.quote.sent`              | quote           | quoteId, channel                        |
| `quote.estimate.accepted`       | quote           | quoteId, total, acceptedAt              |
| `quote.estimate.rejected`       | quote           | quoteId, reason                         |
| `proposal.document.generated`   | proposal        | proposalId, quoteId, templateId         |
| `proposal.document.pdfRendered` | proposal        | proposalId, storageKey, bytes           |
| `esign.document.signed`         | proposal(esign) | proposalId, signerId, signatureHash, ip |
| `payment.deposit.captured`      | payment         | paymentId, quoteId, amount, provider    |
| `payment.invoice.issued`        | payment         | invoiceId, quoteId, total, dueAt        |
| `ai.quote.drafted`              | ai              | quoteId, modelId, inputKind, tokensUsed |
| `ai.usage.recorded`             | ai              | feature, modelId, tokensUsed, costMinor |
| `notification.message.sent`     | notification    | notificationId, channel, template       |

## Delivery guarantees

- **Transactional outbox:** producers write the event to an `outbox` table in the same DB transaction as the state change; a relay publishes to the bus. Guarantees at-least-once.
- **Idempotent consumers:** dedupe on `eventId`. All money/AI-billing side effects require idempotency keys.
- **Bus:** Redis Streams for MVP → Kafka at scale. Consumer groups per service.
- **Versioning:** additive changes bump nothing; breaking payload changes bump `eventVersion` and require an ADR. Never repurpose an event name.

## Producing an event (TypeScript)

```ts
import { createEvent } from "@tradequote/types";

const evt = createEvent("quote.estimate.accepted", {
  eventId: crypto.randomUUID(),
  tenantId,
  actorId: userId,
  payload: {
    quoteId,
    total: { amountMinor: 1299900, currency: "USD" },
    acceptedAt: new Date().toISOString(),
  },
});
// persist `evt` to the outbox inside the same DB transaction as the state change
```
