# 🚀 T204b — E-Signature Web-UI: Agent 2 (Sonnet 5) Implementation Prompt

> **How to use:** Paste this entire document into a **new Claude Code session** for **Agent 2** (`claude-sonnet-5`).
> It is self-contained — read it fully, then begin implementation.

---

## Your Identity & Context

You are **Agent 2 (Full-Stack Lead)** for TradeQuote AI.
You are about to implement **T204b: E-Signature Web-UI** in `apps/web`.

- **Task ID:** `T204b`
- **Module:** M10 (E-Signature Web-UI)
- **Your Model:** `claude-sonnet-5`
- **Dependency:** T204 ✅ (`services/esign-service` port 8007 complete and gateway-reachable)
- **Bounded Context:** `apps/web` (Next.js 15, React 19, `@tanstack/react-query`, Tailwind CSS, Lucide icons, Vitest)

---

## Step 1 — Read the Module Plan

An architecture-level implementation plan has been prepared and is waiting at:

```
docs/modules/M10-esignature-web-ui-plan.md
```

**Read it now.** It contains:
- Complete component layout and file structure.
- Crypto SHA-256 helper specification using standard Web Crypto (`crypto.subtle.digest("SHA-256", arrayBuffer)`).
- Contractor API wrappers & public API wrappers for `/v1/signature-requests` and `/v1/sign/{token}`.
- Dialog and UI component specs (`RequestSignatureDialog`, `SignatureAuditDialog`, `SignaturePad`).
- Integration specs for Proposal Detail (`/proposals/[id]`) and Contractor Overview (`/proposals/signatures`).
- Public customer signing page (`/sign/[token]`) with typed/drawn canvas signature and ESIGN/UETA legal consent & intent checkboxes.

Also review backend spec:
```
docs/modules/M10-esignature.md
```

---

## Step 2 — Read Service Conventions

Ensure your implementation complies with:
```
docs/07-SERVICE-CONVENTIONS.md
```

Key rules:
1. **Public vs Authenticated routes**: `/sign/[token]` has no login/session requirements. Do NOT add `useAuthGuard()` to public routes.
2. **API Client**: Use `apiFetch` from `src/lib/api-client.ts` for fetch calls.
3. **Design Tokens**: Use CSS variable colors and existing UI primitives from `src/components/ui/` (`Card`, `Button`, `Badge`, `Input`, `Label`, `Select`).

---

## Step 3 — Implementation Order

1. **API Client Layer**: Create `src/lib/esign.ts` with TypeScript DTOs, API methods, `computeSha256` helper, and badge variant helpers.
2. **Unit Tests**: Create `src/lib/esign.test.ts` to test API client wrappers, public endpoints, hash calculations, and badge variants.
3. **Signature Pad Component**: Create `src/components/esign/signature-pad.tsx` for HTML5 canvas drawing.
4. **Contractor Request Dialog**: Create `src/components/esign/request-signature-dialog.tsx` (fetches PDF, computes SHA-256, submits request).
5. **Audit Trail Dialog**: Create `src/components/esign/signature-audit-dialog.tsx` displaying live verification badge, signature details, and audit timeline.
6. **Proposal Detail Integration**: Update `src/app/(app)/proposals/[id]/page.tsx` with signature request trigger button and requests list card.
7. **Signatures Overview Page**: Create `src/app/(app)/proposals/signatures/page.tsx` with status filter tabs (`All`, `Pending`, `Signed`, `Declined`, `Voided`, `Expired`).
8. **Public Customer Signing Page**: Create `src/app/sign/[token]/page.tsx` (unauthenticated, PDF preview, document SHA-256 check, typed/drawn signature canvas, legal checkboxes, sign/decline handlers).

---

## Step 4 — Verification

Run local checks in `apps/web`:
```bash
pnpm --filter @tradequote/web typecheck
pnpm --filter @tradequote/web test
pnpm --filter @tradequote/web build
```

All three must be 100% green before completing the task.

---

## Step 5 — Update Tracker

When done:
1. Check the box in `TASKS.md`: `- [x] T204b ...`
2. Update `tracking/PROGRESS-TRACKER.csv`: status → `DONE`, fill end date.

---

**Begin now. Read `docs/modules/M10-esignature-web-ui-plan.md` first, then start coding.**
