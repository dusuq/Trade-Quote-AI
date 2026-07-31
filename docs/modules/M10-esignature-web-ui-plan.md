# T204b — M10 E-Signature Web-UI · Implementation Plan

| Field            | Value                                                          |
| ---------------- | -------------------------------------------------------------- |
| **Task**         | `T204b`                                                        |
| **Module**       | M10 — E-Signature Web-UI (Request action, List/Detail, Audit Trail, Public Sign Page) |
| **Owner agent**  | Agent 2 (Sonnet 5)                                             |
| **Phase**        | Phase 2 — AI + Delivery                                        |
| **Dependencies** | `T204` ✅ (Backend `services/esign-service` port 8007 complete) |
| **Date**         | 2026-07-31                                                     |
| **Bounded ctx**  | `apps/web` (Next.js 15, React 19, `@tanstack/react-query`, Tailwind) |

---

## 1. Overview & Problem Statement

`T204` delivered `services/esign-service` (port 8007) with full tamper-evident audit logging (hash chain), document SHA-256 binding, ESIGN/UETA legal consent & intent enforcement, and opaque capability tokens (`secrets.token_urlsafe(32)`).

Currently, there is no UI in `apps/web` to drive this feature:
1. **Contractor Request Flow**: Contractors cannot create an e-signature request for a proposal or compute the proposal document's SHA-256 hash.
2. **Contractor Audit & Tracking**: Contractors cannot view active/signed signature requests or inspect live cryptographic audit chain verification results.
3. **Public Signer Flow**: End customers visiting `/sign/{token}` have no customer-facing signing experience to view the proposal PDF, sign (typed or drawn), affirm consent & intent, or decline.

`T204b` delivers the complete Web UI in `apps/web` for both contractor and public customer surfaces.

---

## 2. Architecture & Component Layout

```
apps/web/src/
├── lib/
│   ├── esign.ts               # DTO types, API client (gateway proxy & public), SHA-256 helper, badge variants
│   └── esign.test.ts          # Vitest suite for API wrappers, crypto hashing, public route logic
├── components/
│   └── esign/
│       ├── signature-pad.tsx            # Canvas drawing component for drawn signatures
│       ├── request-signature-dialog.tsx # Modal to request signature on proposal (auto SHA-256 computation)
│       └── signature-audit-dialog.tsx   # Modal/drawer showing live tamper verification & hash chain timeline
└── app/
    ├── (app)/proposals/
    │   ├── [id]/page.tsx      # Extended proposal detail page with Request Signature button & requests card
    │   └── signatures/page.tsx# Contractor overview of all signature requests with status filters
    └── sign/[token]/page.tsx  # Unauthenticated public customer signing page (PDF viewer, canvas/typed, consent, submit)
```

---

## 3. Detailed Component Specifications

### 3.1 `src/lib/esign.ts` & `src/lib/esign.test.ts`
- **Crypto Helper**:
  ```ts
  export async function computeSha256(buffer: ArrayBuffer): Promise<string> {
    const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  ```
- **Authenticated Contractor API Wrappers**:
  - `createSignatureRequest(token, input)` -> `POST /v1/signature-requests`
  - `listSignatureRequests(token, { proposal_id?, status? })` -> `GET /v1/signature-requests`
  - `getSignatureRequest(token, requestId)` -> `GET /v1/signature-requests/{id}`
  - `getSignatureAuditTrail(token, requestId)` -> `GET /v1/signature-requests/{id}/audit`
  - `voidSignatureRequest(token, requestId, reason?)` -> `POST /v1/signature-requests/{id}/void`
- **Public Signer API Wrappers**:
  - `getPublicSigningContext(token)` -> `GET /v1/sign/{token}`
  - `applyPublicSignature(token, payload)` -> `POST /v1/sign/{token}`
  - `declinePublicSignature(token, reason?)` -> `POST /v1/sign/{token}/decline`
- **Badge Variant Helper**:
  - `statusBadgeVariantForEsign(status: SignatureRequestStatus)`: maps `pending` (warning), `signed` (success/default), `declined` (destructive), `voided` (outline), `expired` (secondary).

### 3.2 Contractor Components
1. **`RequestSignatureDialog`**:
   - Inputs: Signer Name, Signer Email, Expiration Days (default 30).
   - Fetches proposal PDF buffer via `fetchProposalPdfBlob(token, proposalId)`.
   - Computes `document_sha256` using `computeSha256`.
   - Calls `createSignatureRequest`.
2. **`SignatureAuditDialog`**:
   - Calls `getSignatureAuditTrail(token, requestId)`.
   - Prominently displays:
     - 🛡️ **Chain Verified (Valid)** when `verification.is_valid === true` (green badge + entry count).
     - ⚠️ **Tamper Detected (Invalid)** when `verification.is_valid === false` (red badge + sequence number + reason).
   - Lists captured signature metadata (signer name, IP, timestamp, method, consent/intent flags).
   - Sequence timeline of audit events (`event_type`, `occurred_at`, `entry_hash`, `prev_hash`).
3. **`SignaturePad`**:
   - Canvas-based component supporting touch & mouse drawing.
   - Outputs base64 data URL string (`image_data`). Clear/Redraw buttons.

### 3.3 Contractor Pages
1. **`app/(app)/proposals/[id]/page.tsx` (Update)**:
   - Adds "Request E-Signature" primary action button.
   - Renders "Signature Requests" card listing requests for this proposal.
   - Shows badge status, expiration, share link copy button (`/sign/${token}`), audit modal trigger, void trigger.
2. **`app/(app)/proposals/signatures/page.tsx` (New)**:
   - Contractor overview dashboard of all signature requests.
   - Filter tabs: `All`, `Pending`, `Signed`, `Declined`, `Voided`, `Expired`.

### 3.4 Public Customer Page (`app/sign/[token]/page.tsx`)
- **Unauthenticated** (No `useAuthGuard()`).
- Fetches `PublicSigningContext` from `GET /v1/sign/{token}`.
- Shows PDF view/download button.
- Document SHA-256 verification indicator.
- Tabs for **Typed Signature** (live cursive font preview) and **Drawn Signature** (`SignaturePad`).
- Legal compliance checkboxes:
  - ☑️ "I consent to conduct business electronically" (`consented_to_electronic_business`)
  - ☑️ "I affirm my intent to adopt this signature as my legally binding signature" (`intent_affirmed`)
- Actions:
  - "Sign Proposal" -> `POST /v1/sign/{token}`
  - "Decline to Sign" -> modal -> `POST /v1/sign/{token}/decline`
- Success receipt view displaying transaction ID, signature hash, and signed timestamp.

---

## 4. Definition of Done

- [ ] `src/lib/esign.ts` DTOs and fetch client implemented.
- [ ] `src/lib/esign.test.ts` vitest unit tests 100% green.
- [ ] Contractor components (`RequestSignatureDialog`, `SignatureAuditDialog`, `SignaturePad`) built.
- [ ] Proposal Detail page updated with signature request card and trigger button.
- [ ] Contractor Signature Overview page (`/proposals/signatures`) created with status filtering.
- [ ] Public customer signing page (`/sign/[token]`) implemented and tested with no auth requirement.
- [ ] `pnpm --filter @tradequote/web typecheck` clean.
- [ ] `pnpm --filter @tradequote/web test` clean.
- [ ] `pnpm --filter @tradequote/web build` green.
