# T204 — M10 E-Signature + Audit Trail · Design Spec

| Field            | Value                                                         |
| ---------------- | ------------------------------------------------------------- |
| **Task**         | `T204`                                                        |
| **Module**       | M10 — E-Signature + audit trail (IP, timestamp, hash chain)   |
| **Owner agent**  | Agent 1 (CTO) — built at founder direction; board lane was A4 |
| **Phase**        | Phase 2 — AI + Delivery                                       |
| **Dependencies** | `T203` Proposal Builder ✅ (CTO-signed-off 2026-07-28)        |
| **Date**         | 2026-07-28                                                    |
| **Bounded ctx**  | `services/esign-service` (new) — `esign` per `packages/types` |

---

## 1. Problem

T203 ships proposals a customer can open at a public link (`GET /v1/proposals/{id}/view`) and read as
a PDF. Nothing lets them **agree** to it. There is no signature capture, no record of who agreed to
what, and no tamper-evident evidence trail — which is the part that actually matters, because a
signed trade quote is the contract the job runs on and the document a payment dispute turns on.

An e-signature feature that stores "signed: true" is worse than none: it creates the appearance of
enforceability without the evidence to support it.

## 2. Decisions

### D1 — New `services/esign-service`, not an extension of `proposal-service`

`packages/types/src/events.ts` already declares `esign` as a distinct `BoundedContext` and defines
`esign.document.signed` with a `DocumentSignedPayload`. Conventions §4 forbids inventing event
shapes locally; the canonical registry has already modelled this as its own context.

**Rejected alternatives:**

- _Fold signing into `proposal-service`_ — fewer moving parts, and the two are closely related in
  the user's mental model. But it contradicts the canonical registry, and it mixes a document
  **rendering/delivery** concern with a **legal evidence** concern that has very different
  retention, immutability, and audit requirements. Signature evidence should not be casually
  editable by the same code path that regenerates a PDF.
- _A generic "audit-service"_ — over-general for one consumer; no second consumer exists yet.

**Why D1 wins:** matches the declared contract, and keeps the immutable evidence store isolated
from mutable document state. Cross-context reference to `proposal_id` is a plain indexed UUID with
no FK — exactly how `proposal.quote_id` already references quote-service (0006 migration, line 37).

### D2 — The signing link is an opaque high-entropy token, not the proposal/request id

`GET /v1/proposals/{id}/view` uses the raw proposal UUID as its capability. That is acceptable for
_viewing_ a document. It is **not** acceptable for a legally binding act: a UUID leaks through
referrers, logs, and browser history, and cannot be revoked without destroying the proposal.

Signing links carry `secrets.token_urlsafe(32)` (~256 bits). This also makes the link independently
**voidable** and **expirable** without touching the proposal.

### D3 — The audit trail is a hash chain, and it is the feature

Every state change on a signature request appends an immutable `signature_audit_event`:

```
hash_n = sha256(canonical_json({
  request_id, sequence, event_type, payload, occurred_at, prev_hash: hash_{n-1}
}))
```

`hash_0`'s `prev_hash` is a genesis constant (64 zeros). Because each link commits to the one before
it, any mutation, deletion, reordering, or insertion breaks verification **from that point forward**
and `verify_chain()` reports the exact sequence number where it broke.

`request_id` is inside the hashed payload specifically so a valid run of events cannot be spliced
from one signature request into another.

This is pure, dependency-free domain logic (`app/domain/hash_chain.py`) — fully unit-testable with
no database, which is the point: the guarantee is verifiable in CI, not asserted in a README.

### D4 — The signature is bound to the exact document bytes

`document_sha256` (the SHA-256 of the rendered PDF) is captured when the request is created and
**re-asserted by the client at signing time**. A mismatch is rejected outright.

This is the ESIGN Act / UETA "association with the record" requirement in mechanical form: it makes
"they signed a different version of the quote" a detectable condition rather than an argument.

### D5 — Consent and intent are explicit, required, and recorded

UETA/ESIGN enforceability rests on the signer's **intent to sign** and **consent to transact
electronically**. Both are required booleans on the sign request; the use case rejects the signature
if either is false. They are recorded in the audit payload, not just implied by the act.

### D6 — Repository `Protocol` style (conventions §3)

New services "should default to the Protocol style." All use cases depend on
`SignatureRequestRepository` / `SignatureRepository` / `AuditTrailRepository` protocols and are
tested against in-memory fakes with no database at all.

## 3. Data model (`0008_esign.sql`)

> Migration number: `0007` is reserved for T307b (analytics) — already communicated to Agent 3 in
> `docs/handoffs/T307b-T311-antigravity-handoff.md` — so e-sign takes `0008`.

| Table                   | Purpose                                                               |
| ----------------------- | --------------------------------------------------------------------- |
| `signature_request`     | One signing ask: proposal ref, signer identity, token, status, expiry |
| `signature`             | The captured signature + evidence (IP, UA, method, hashes, consent)   |
| `signature_audit_event` | Append-only hash chain; `UNIQUE (request_id, sequence)`               |

All three are `tenant_id`-scoped with RLS policies mirroring 0006. `resolve_signature_request_tenant(text)`
is a `SECURITY DEFINER` function resolving tenant from a token for the public routes — same narrow,
single-column pattern as `resolve_proposal_tenant`, hardened with `SET search_path = public`.

Statuses: `pending → signed | declined | voided | expired`.

## 4. HTTP surface

**Authenticated** (gateway supplies `x-tenant-id`):

| Method | Path                                | Purpose                                   |
| ------ | ----------------------------------- | ----------------------------------------- |
| POST   | `/v1/signature-requests`            | Create a signing request → returns token  |
| GET    | `/v1/signature-requests`            | List (filter by `proposal_id`, `status`)  |
| GET    | `/v1/signature-requests/{id}`       | Detail incl. signature if present         |
| GET    | `/v1/signature-requests/{id}/audit` | Hash chain **+ live verification result** |
| POST   | `/v1/signature-requests/{id}/void`  | Void a pending request                    |

**Public — no auth at all** (the customer has no account):

| Method | Path                       | Purpose                                        |
| ------ | -------------------------- | ---------------------------------------------- |
| GET    | `/v1/sign/{token}`         | What am I signing? (records `document.opened`) |
| POST   | `/v1/sign/{token}`         | Apply signature                                |
| POST   | `/v1/sign/{token}/decline` | Decline to sign                                |

`/v1/sign/*` is a deliberate second exception to "everything is authenticated," alongside
`/v1/proposals/{id}/view`. It is added to the gateway's `PUBLIC_PATH_PATTERNS` with a **narrowly
anchored** regex, per the warning already in `apps/api-gateway/src/plugins/auth.ts`.

The public GET deliberately returns **only** what a signer needs (proposal id, signer name, document
hash, status, expiry) — never the tenant id, internal ids, or the audit trail.

## 5. Out of scope (tracked, not silently dropped)

- **Web UI** — no `apps/web` surface. Tracked as **T204b**, applying the same standard this fleet
  applied to T307b: a backend nothing can drive is only half a feature.
- Email/SMS delivery of the signing link → that's T205 (Notifications).
- Countersigning / multi-party sequential signing → single signer only for MVP.
- Certificate-of-completion PDF generation → natural follow-up once T205 lands.

## 6. Definition of Done

- [x] Clean Architecture layering; use cases depend only on Protocols
- [x] Hash chain implemented + tamper-evidence proven by tests (mutation, deletion, reorder, splice)
- [x] Consent + intent enforced; document-hash mismatch rejected
- [x] Tenant isolation test (conventions §2)
- [x] Gateway wiring incl. narrowly-scoped public route pattern + gateway regression test
- [x] Migration with RLS on all three tables
- [x] `ruff` / `mypy` / `pytest` clean; `check_conventions.py` OK
