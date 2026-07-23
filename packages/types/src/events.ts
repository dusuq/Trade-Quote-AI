/**
 * TradeQuote AI — Canonical Domain-Event Registry
 * ------------------------------------------------
 * Single source of truth for every asynchronous event that crosses a service
 * boundary. Owned by Agent 1 (CTO). Breaking changes require an ADR + version bump.
 *
 * Naming convention:  `<context>.<aggregate>.<pastTenseVerb>`
 *   e.g.  quote.estimate.accepted   proposal.document.signed   payment.deposit.captured
 *
 * Every event is wrapped in {@link DomainEventEnvelope}. Payloads are versioned
 * independently via `eventVersion` (start at 1). Money is always integer minor
 * units (cents) + ISO-4217 currency — never floats.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Shared primitives
// ─────────────────────────────────────────────────────────────────────────────

/** Bounded contexts (each maps to a service). */
export type BoundedContext =
  | "auth"
  | "customer"
  | "lead"
  | "pricebook"
  | "quote"
  | "proposal"
  | "esign"
  | "payment"
  | "ai"
  | "notification";

/** RFC-4122 UUID (branded for clarity; still a string at runtime). */
export type UUID = string;
/** ISO-8601 timestamp, always UTC, e.g. "2026-07-23T12:34:56.000Z". */
export type ISODateTime = string;
/** ISO-4217 currency code, e.g. "USD", "CAD", "GBP", "AUD", "NZD". */
export type CurrencyCode = "USD" | "CAD" | "GBP" | "AUD" | "NZD";

/** Money as integer minor units (cents) + currency. Never use floats for money. */
export interface Money {
  amountMinor: number;
  currency: CurrencyCode;
}

// ─────────────────────────────────────────────────────────────────────────────
// Envelope
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Every domain event on the bus is wrapped in this envelope. The metadata is
 * mandatory and uniform so consumers, the outbox, tracing, and audit all work
 * the same way regardless of event type.
 */
export interface DomainEventEnvelope<TName extends string = string, TPayload = unknown> {
  /** Unique id for this event instance (dedupe / idempotency key). */
  eventId: UUID;
  /** Canonical event name — see naming convention above. */
  eventName: TName;
  /** Payload schema version for `eventName`. Starts at 1. */
  eventVersion: number;
  /** Multi-tenant scope. Consumers MUST filter by this. Never cross tenants. */
  tenantId: UUID;
  /** User who caused the event, or `null` for system/automation. */
  actorId: UUID | null;
  /** When the event actually happened (UTC). */
  occurredAt: ISODateTime;
  /** Correlates all events in one business transaction/request. */
  correlationId?: UUID;
  /** The event id that directly caused this one (causation chain). */
  causationId?: UUID;
  /** The typed business payload. */
  payload: TPayload;
}

// ─────────────────────────────────────────────────────────────────────────────
// Payloads (representative core set — extend per module as it is built)
// ─────────────────────────────────────────────────────────────────────────────

// auth
export interface TenantCreatedPayload {
  tenantId: UUID;
  name: string;
  plan: "starter" | "professional" | "business" | "enterprise";
}
export interface UserInvitedPayload {
  userId: UUID;
  email: string;
  role:
    | "owner"
    | "admin"
    | "estimator"
    | "technician"
    | "salesperson"
    | "office"
    | "accountant"
    | "viewer";
}

// customer
export interface CustomerCreatedPayload {
  customerId: UUID;
  displayName: string;
  primaryContactId: UUID | null;
}
export interface PropertyAddedPayload {
  customerId: UUID;
  propertyId: UUID;
  addressLine1: string;
  geo?: { lat: number; lng: number };
}

// lead
export interface LeadCapturedPayload {
  leadId: UUID;
  source: "website" | "phone" | "facebook" | "google" | "referral" | "other";
  score: number | null;
}

// pricebook
export interface PricebookItemUpsertedPayload {
  itemId: UUID;
  kind: "material" | "labor" | "equipment" | "consumable" | "rental" | "package";
  sku: string | null;
  unitCost: Money;
}

// quote
export interface QuoteCreatedPayload {
  quoteId: UUID;
  customerId: UUID;
  createdVia: "manual" | "voice" | "vision" | "ocr";
}
export interface QuoteLineItemsChangedPayload {
  quoteId: UUID;
  lineItemCount: number;
  subtotal: Money;
}
export interface QuoteSentPayload {
  quoteId: UUID;
  channel: "email" | "sms" | "whatsapp" | "link";
}
export interface QuoteAcceptedPayload {
  quoteId: UUID;
  total: Money;
  acceptedAt: ISODateTime;
}
export interface QuoteRejectedPayload {
  quoteId: UUID;
  reason: string | null;
}

// proposal
export interface ProposalGeneratedPayload {
  proposalId: UUID;
  quoteId: UUID;
  templateId: UUID;
}
export interface ProposalPdfRenderedPayload {
  proposalId: UUID;
  storageKey: string;
  bytes: number;
}

// esign
export interface DocumentSignedPayload {
  proposalId: UUID;
  signerId: UUID;
  signatureHash: string;
  ipAddress: string;
  signedAt: ISODateTime;
}

// payment
export interface DepositCapturedPayload {
  paymentId: UUID;
  quoteId: UUID;
  amount: Money;
  provider: "stripe" | "square" | "paypal" | "ach";
}
export interface InvoiceIssuedPayload {
  invoiceId: UUID;
  quoteId: UUID;
  total: Money;
  dueAt: ISODateTime;
}

// ai
export interface AiQuoteDraftedPayload {
  quoteId: UUID;
  modelId: string;
  inputKind: "voice" | "text" | "vision" | "ocr";
  tokensUsed: number;
}
export interface AiUsageRecordedPayload {
  feature: "copilot" | "voice" | "vision" | "ocr" | "sales_coach" | "scope_writer";
  modelId: string;
  tokensUsed: number;
  costMinor: number;
}

// notification
export interface NotificationSentPayload {
  notificationId: UUID;
  channel: "email" | "sms" | "whatsapp" | "push";
  template: string;
  toRedacted: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Typed event map + discriminated union
// ─────────────────────────────────────────────────────────────────────────────

/** Maps each canonical event name to its payload type. Extend as modules ship. */
export interface DomainEventPayloadMap {
  "auth.tenant.created": TenantCreatedPayload;
  "auth.user.invited": UserInvitedPayload;
  "customer.customer.created": CustomerCreatedPayload;
  "customer.property.added": PropertyAddedPayload;
  "lead.lead.captured": LeadCapturedPayload;
  "pricebook.item.upserted": PricebookItemUpsertedPayload;
  "quote.quote.created": QuoteCreatedPayload;
  "quote.quote.lineItemsChanged": QuoteLineItemsChangedPayload;
  "quote.quote.sent": QuoteSentPayload;
  "quote.estimate.accepted": QuoteAcceptedPayload;
  "quote.estimate.rejected": QuoteRejectedPayload;
  "proposal.document.generated": ProposalGeneratedPayload;
  "proposal.document.pdfRendered": ProposalPdfRenderedPayload;
  "esign.document.signed": DocumentSignedPayload;
  "payment.deposit.captured": DepositCapturedPayload;
  "payment.invoice.issued": InvoiceIssuedPayload;
  "ai.quote.drafted": AiQuoteDraftedPayload;
  "ai.usage.recorded": AiUsageRecordedPayload;
  "notification.message.sent": NotificationSentPayload;
}

/** All valid event names. */
export type DomainEventName = keyof DomainEventPayloadMap;

/** A fully-typed event for a specific name. */
export type DomainEvent<TName extends DomainEventName = DomainEventName> = {
  [K in TName]: DomainEventEnvelope<K, DomainEventPayloadMap[K]>;
}[TName];

/** The discriminated union of every event in the system. */
export type TradeQuoteEvent = DomainEvent;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const EVENT_NAME_RE = /^[a-z]+\.[a-zA-Z]+\.[a-zA-Z]+$/;

/** Validates the `<context>.<aggregate>.<verb>` shape at runtime. */
export function isValidEventName(name: string): name is DomainEventName {
  return EVENT_NAME_RE.test(name);
}

/** Extracts the bounded context from an event name. */
export function contextOf(name: DomainEventName): BoundedContext {
  return name.split(".")[0] as BoundedContext;
}

/**
 * Type-safe event factory. Fills the envelope; caller supplies identity + payload.
 * Producers should persist the returned envelope via the transactional outbox.
 */
export function createEvent<TName extends DomainEventName>(
  eventName: TName,
  args: {
    eventId: UUID;
    tenantId: UUID;
    actorId: UUID | null;
    payload: DomainEventPayloadMap[TName];
    occurredAt?: ISODateTime;
    eventVersion?: number;
    correlationId?: UUID;
    causationId?: UUID;
  },
): DomainEventEnvelope<TName, DomainEventPayloadMap[TName]> {
  return {
    eventId: args.eventId,
    eventName,
    eventVersion: args.eventVersion ?? 1,
    tenantId: args.tenantId,
    actorId: args.actorId,
    occurredAt: args.occurredAt ?? new Date().toISOString(),
    correlationId: args.correlationId,
    causationId: args.causationId,
    payload: args.payload,
  };
}
