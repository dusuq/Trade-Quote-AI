# T204b M10 E-Signature Web UI Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete `apps/web` UI for T204's e-signature backend (`services/esign-service`, port 8007) — a contractor request/tracking flow on the proposal pages, and an unauthenticated public customer signing page.

**Architecture:** One new data-layer file (`lib/esign.ts`) mirroring the backend DTOs exactly, one new dependency-free `Dialog` UI primitive (this app's first true overlay component, per user decision), three new components (`SignaturePad`, `RequestSignatureDialog`, `SignatureAuditDialog`), two updated/new contractor pages, and one new standalone public page outside the `(app)` route group.

**Tech Stack:** Next.js 15 App Router, TanStack Query, vitest, existing `apps/web/src/components/ui/*` primitives (Card, Badge, Button, Input, Label), native Canvas + Pointer Events, native Web Crypto (`crypto.subtle`), `lucide-react` icons.

## Global Constraints

- Money is not involved in this feature — skip.
- The public routes (`GET/POST /v1/sign/{token}`, `POST /v1/sign/{token}/decline`) take **no bearer token** — `apiFetch` calls for these must omit the `token` option entirely (not pass an empty string).
- `SignatureRequestSummary` (the list endpoint's shape) **deliberately omits the signing `token`** — per its own docstring in `services/esign-service/app/interface/schemas.py`: "a list endpoint should not spray live signing capabilities across every row." Any UI that needs to build a `/sign/{token}` link for an existing request **must** call `getSignatureRequest` (the detail endpoint, which does include `token`) on demand — never assume the list response carries it.
- Every public-facing (customer) error message must go through `describeEsignSubmitError`, never a raw status code — the signer is not a technical user.
- No `.test.tsx` files — this repo's `vitest.config.ts` only includes `src/**/*.test.ts`, so a component test file would silently never run. UI components are verified live in the browser (Task 9), not unit tested. Only `lib/esign.ts` gets a test file.
- No new npm dependencies — the `Dialog` primitive, canvas signature pad, and SHA-256 hashing are all built on native browser APIs already available (Web Crypto, Canvas, Pointer Events).
- Follow existing badge variants exactly: `default | secondary | destructive | outline | success | warning` (`apps/web/src/components/ui/badge.tsx`) — do not invent a new one.

---

### Task 1: `Dialog` UI primitive

**Files:**

- Create: `apps/web/src/components/ui/dialog.tsx`

**Interfaces:**

- Consumes: `cn` from `@/lib/utils`, `X` icon from `lucide-react`.
- Produces (consumed by Tasks 4 and 5): `export function Dialog({ open, onClose, title, children, className }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; className?: string }): JSX.Element | null`.

No test file (component, and this app's convention per Global Constraints is browser-only verification for UI). This task's gate is a clean typecheck.

- [ ] **Step 1: Write the component**

Create `apps/web/src/components/ui/dialog.tsx`:

```tsx
"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Lightweight, dependency-free modal — this app's first true overlay
 * component (every prior "dialog"-shaped feature here is an inline panel).
 * Closes on Escape or backdrop click. Does not trap focus - no multi-step
 * keyboard-only flow uses this yet, so keep anything rendered inside simple.
 */
export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  React.useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className={cn(
          "max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border bg-card p-6 text-card-foreground shadow-lg",
          className,
        )}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            type="button"
            aria-label="Close"
            className="text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no output (clean) — the component isn't consumed anywhere yet, so this only checks the file compiles standalone against the rest of the existing app.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/ui/dialog.tsx
git commit -m "feat: add dependency-free Dialog UI primitive"
```

---

### Task 2: `esign.ts` data layer

**Files:**

- Create: `apps/web/src/lib/esign.ts`
- Test: `apps/web/src/lib/esign.test.ts`

**Interfaces:**

- Consumes: `apiFetch`, `ApiError` from `@/lib/api-client`.
- Produces (consumed by every later task): types `SignatureRequestStatus`, `SignatureMethod`, `SignatureResponse`, `SignatureRequestSummary`, `SignatureRequestDetail`, `PublicSigningContext`, `ChainVerificationResponse`, `AuditEntryResponse`, `AuditTrailResponse`, `CreateSignatureRequestInput`, `ApplySignatureInput`; functions `createSignatureRequest(token, input)`, `listSignatureRequests(token, filter?)`, `getSignatureRequest(token, requestId)`, `getSignatureAuditTrail(token, requestId)`, `voidSignatureRequest(token, requestId, reason?)`, `getPublicSigningContext(signingToken)`, `applyPublicSignature(signingToken, payload)`, `declinePublicSignature(signingToken, reason?)`, `computeSha256(buffer)`, `statusBadgeVariantForEsign(status)`, `describeEsignSubmitError(err)`.

Note on naming: the three public functions take a **signing token** (the opaque `/sign/{token}` path segment) as their first argument, named `signingToken` — deliberately _not_ `token`, to avoid confusion with every other function in this codebase where `token` means the auth bearer JWT. Getting this backwards (passing a bearer token to a public route, or vice versa) is an easy mistake since both are just strings.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/lib/esign.test.ts`:

```typescript
// apps/web/src/lib/esign.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import {
  applyPublicSignature,
  computeSha256,
  createSignatureRequest,
  declinePublicSignature,
  describeEsignSubmitError,
  getPublicSigningContext,
  getSignatureAuditTrail,
  getSignatureRequest,
  listSignatureRequests,
  statusBadgeVariantForEsign,
  voidSignatureRequest,
} from "@/lib/esign";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    }),
  );
}

const SAMPLE_DETAIL = {
  id: "11111111-1111-1111-1111-111111111111",
  proposal_id: "22222222-2222-2222-2222-222222222222",
  signer_id: "33333333-3333-3333-3333-333333333333",
  signer_name: "Jane Doe",
  signer_email: "jane@example.com",
  document_sha256: "a".repeat(64),
  status: "pending",
  expires_at: "2026-08-30T00:00:00Z",
  created_at: "2026-07-31T00:00:00Z",
  signed_at: null,
  declined_at: null,
  voided_at: null,
  token: "abc123token",
  signing_path: "/v1/sign/abc123token",
  signature: null,
};

describe("computeSha256", () => {
  it("computes the correct SHA-256 hex digest", async () => {
    const buffer = new TextEncoder().encode("test").buffer;
    const hash = await computeSha256(buffer);
    expect(hash).toBe("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08");
  });
});

describe("createSignatureRequest", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to /v1/signature-requests with the bearer token", async () => {
    mockFetchOnce(201, SAMPLE_DETAIL);
    const result = await createSignatureRequest("tok", {
      proposal_id: SAMPLE_DETAIL.proposal_id,
      signer_name: "Jane Doe",
      signer_email: "jane@example.com",
      document_sha256: "a".repeat(64),
      expires_in_days: 30,
    });
    expect(result.token).toBe("abc123token");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/signature-requests");
    expect(call[1]?.method).toBe("POST");
    expect((call[1]?.headers as Record<string, string>).authorization).toBe("Bearer tok");
  });
});

describe("listSignatureRequests", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GETs with no query string when no filter is given", async () => {
    mockFetchOnce(200, []);
    await listSignatureRequests("tok");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toMatch(/\/v1\/signature-requests$/);
  });

  it("GETs with proposal_id and status query params", async () => {
    mockFetchOnce(200, []);
    await listSignatureRequests("tok", { proposal_id: "p1", status: "pending" });
    const call = vi.mocked(fetch).mock.calls[0];
    const url = call[0] as string;
    expect(url).toContain("proposal_id=p1");
    expect(url).toContain("status=pending");
  });
});

describe("getSignatureRequest", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GETs /v1/signature-requests/{id}", async () => {
    mockFetchOnce(200, SAMPLE_DETAIL);
    const result = await getSignatureRequest("tok", SAMPLE_DETAIL.id);
    expect(result.id).toBe(SAMPLE_DETAIL.id);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/signature-requests/${SAMPLE_DETAIL.id}`);
  });
});

describe("getSignatureAuditTrail", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GETs /v1/signature-requests/{id}/audit", async () => {
    mockFetchOnce(200, {
      request_id: SAMPLE_DETAIL.id,
      entries: [],
      verification: { is_valid: true, entry_count: 0, broken_at_sequence: null, reason: null },
    });
    const result = await getSignatureAuditTrail("tok", SAMPLE_DETAIL.id);
    expect(result.verification.is_valid).toBe(true);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/signature-requests/${SAMPLE_DETAIL.id}/audit`);
  });
});

describe("voidSignatureRequest", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs to .../void with the reason normalized to null when omitted", async () => {
    mockFetchOnce(200, { ...SAMPLE_DETAIL, status: "voided" });
    await voidSignatureRequest("tok", SAMPLE_DETAIL.id);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/signature-requests/${SAMPLE_DETAIL.id}/void`);
    expect(JSON.parse(call[1]?.body as string)).toEqual({ reason: null });
  });
});

describe("getPublicSigningContext", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GETs /v1/sign/{signingToken} with no auth header", async () => {
    mockFetchOnce(200, {
      proposal_id: SAMPLE_DETAIL.proposal_id,
      signer_name: "Jane Doe",
      document_sha256: "a".repeat(64),
      status: "pending",
      expires_at: "2026-08-30T00:00:00Z",
      can_sign: true,
    });
    await getPublicSigningContext("abc123token");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/sign/abc123token");
    expect((call[1]?.headers as Record<string, string>).authorization).toBeUndefined();
  });
});

describe("applyPublicSignature", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs to /v1/sign/{signingToken} with no auth header", async () => {
    mockFetchOnce(201, {
      id: "sig-1",
      signer_name: "Jane Doe",
      signer_email: "jane@example.com",
      method: "typed",
      typed_name: "Jane Doe",
      signature_hash: "b".repeat(64),
      document_sha256: "a".repeat(64),
      ip_address: "203.0.113.1",
      user_agent: "test-agent",
      consented_to_electronic_business: true,
      intent_affirmed: true,
      signed_at: "2026-07-31T00:00:00Z",
    });
    const result = await applyPublicSignature("abc123token", {
      method: "typed",
      typed_name: "Jane Doe",
      image_data: null,
      document_sha256: "a".repeat(64),
      consented_to_electronic_business: true,
      intent_affirmed: true,
    });
    expect(result.id).toBe("sig-1");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/sign/abc123token");
    expect(call[1]?.method).toBe("POST");
    expect((call[1]?.headers as Record<string, string>).authorization).toBeUndefined();
  });
});

describe("declinePublicSignature", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs to /v1/sign/{signingToken}/decline with no auth header", async () => {
    mockFetchOnce(200, {
      proposal_id: SAMPLE_DETAIL.proposal_id,
      signer_name: "Jane Doe",
      document_sha256: "a".repeat(64),
      status: "declined",
      expires_at: "2026-08-30T00:00:00Z",
      can_sign: false,
    });
    await declinePublicSignature("abc123token", "Changed my mind");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/sign/abc123token/decline");
    expect(JSON.parse(call[1]?.body as string)).toEqual({ reason: "Changed my mind" });
    expect((call[1]?.headers as Record<string, string>).authorization).toBeUndefined();
  });
});

describe("statusBadgeVariantForEsign", () => {
  it("maps each status to its badge variant", () => {
    expect(statusBadgeVariantForEsign("pending")).toBe("warning");
    expect(statusBadgeVariantForEsign("signed")).toBe("success");
    expect(statusBadgeVariantForEsign("declined")).toBe("destructive");
    expect(statusBadgeVariantForEsign("voided")).toBe("outline");
    expect(statusBadgeVariantForEsign("expired")).toBe("secondary");
  });
});

describe("describeEsignSubmitError", () => {
  it("maps known statuses to specific messages", () => {
    expect(describeEsignSubmitError(new ApiError(404, "x"))).toContain("no longer valid");
    expect(describeEsignSubmitError(new ApiError(409, "x"))).toContain("already been signed");
    expect(describeEsignSubmitError(new ApiError(422, "x"))).toContain("consent");
  });

  it("falls back to the error message for an unmapped status", () => {
    expect(describeEsignSubmitError(new ApiError(500, "boom"))).toBe("boom");
  });

  it("falls back to a generic message for a non-ApiError", () => {
    expect(describeEsignSubmitError(new Error("network down"))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/web && pnpm vitest run src/lib/esign.test.ts`
Expected: FAIL — `Cannot find module '@/lib/esign'`.

- [ ] **Step 3: Write the implementation**

Create `apps/web/src/lib/esign.ts`:

```typescript
import { apiFetch, ApiError } from "@/lib/api-client";

export type SignatureRequestStatus = "pending" | "signed" | "declined" | "voided" | "expired";
export type SignatureMethod = "typed" | "drawn";

export interface SignatureResponse {
  id: string;
  signer_name: string;
  signer_email: string;
  method: SignatureMethod;
  typed_name: string | null;
  signature_hash: string;
  document_sha256: string;
  ip_address: string;
  user_agent: string | null;
  consented_to_electronic_business: boolean;
  intent_affirmed: boolean;
  signed_at: string;
}

export interface SignatureRequestSummary {
  id: string;
  proposal_id: string;
  signer_id: string;
  signer_name: string;
  signer_email: string;
  document_sha256: string;
  status: SignatureRequestStatus;
  expires_at: string;
  created_at: string;
  signed_at: string | null;
  declined_at: string | null;
  voided_at: string | null;
}

/** Includes the signing `token` — the list endpoint (SignatureRequestSummary)
 * deliberately does not. Never assume a list row carries a usable token. */
export interface SignatureRequestDetail extends SignatureRequestSummary {
  token: string;
  signing_path: string;
  signature: SignatureResponse | null;
}

export interface PublicSigningContext {
  proposal_id: string;
  signer_name: string;
  document_sha256: string;
  status: SignatureRequestStatus;
  expires_at: string;
  can_sign: boolean;
}

export interface ChainVerificationResponse {
  is_valid: boolean;
  entry_count: number;
  broken_at_sequence: number | null;
  reason: string | null;
}

export interface AuditEntryResponse {
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  prev_hash: string;
  entry_hash: string;
}

export interface AuditTrailResponse {
  request_id: string;
  entries: AuditEntryResponse[];
  verification: ChainVerificationResponse;
}

export interface CreateSignatureRequestInput {
  proposal_id: string;
  signer_name: string;
  signer_email: string;
  document_sha256: string;
  expires_in_days?: number;
}

export function createSignatureRequest(
  token: string,
  input: CreateSignatureRequestInput,
): Promise<SignatureRequestDetail> {
  return apiFetch<SignatureRequestDetail>("/v1/signature-requests", {
    method: "POST",
    token,
    body: input,
  });
}

export interface ListSignatureRequestsFilter {
  proposal_id?: string;
  status?: SignatureRequestStatus;
}

export function listSignatureRequests(
  token: string,
  filter: ListSignatureRequestsFilter = {},
): Promise<SignatureRequestSummary[]> {
  const params = new URLSearchParams();
  if (filter.proposal_id) params.set("proposal_id", filter.proposal_id);
  if (filter.status) params.set("status", filter.status);
  const qs = params.toString();
  return apiFetch<SignatureRequestSummary[]>(`/v1/signature-requests${qs ? `?${qs}` : ""}`, {
    token,
  });
}

export function getSignatureRequest(
  token: string,
  requestId: string,
): Promise<SignatureRequestDetail> {
  return apiFetch<SignatureRequestDetail>(`/v1/signature-requests/${requestId}`, { token });
}

export function getSignatureAuditTrail(
  token: string,
  requestId: string,
): Promise<AuditTrailResponse> {
  return apiFetch<AuditTrailResponse>(`/v1/signature-requests/${requestId}/audit`, { token });
}

export function voidSignatureRequest(
  token: string,
  requestId: string,
  reason?: string,
): Promise<SignatureRequestSummary> {
  return apiFetch<SignatureRequestSummary>(`/v1/signature-requests/${requestId}/void`, {
    method: "POST",
    token,
    body: { reason: reason ?? null },
  });
}

export interface ApplySignatureInput {
  method: SignatureMethod;
  typed_name?: string | null;
  image_data?: string | null;
  document_sha256: string;
  consented_to_electronic_business: boolean;
  intent_affirmed: boolean;
}

// ── Public (unauthenticated) — no `token` param, no bearer header ──────────

export function getPublicSigningContext(signingToken: string): Promise<PublicSigningContext> {
  return apiFetch<PublicSigningContext>(`/v1/sign/${signingToken}`);
}

export function applyPublicSignature(
  signingToken: string,
  payload: ApplySignatureInput,
): Promise<SignatureResponse> {
  return apiFetch<SignatureResponse>(`/v1/sign/${signingToken}`, {
    method: "POST",
    body: payload,
  });
}

export function declinePublicSignature(
  signingToken: string,
  reason?: string,
): Promise<PublicSigningContext> {
  return apiFetch<PublicSigningContext>(`/v1/sign/${signingToken}/decline`, {
    method: "POST",
    body: { reason: reason ?? null },
  });
}

/** SHA-256 of an ArrayBuffer as lowercase hex — matches the backend's
 * `_SHA256_HEX` pattern and its case-normalizing validator exactly. */
export async function computeSha256(buffer: ArrayBuffer): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Badge variant for a signature request's status — pure, unit-tested. */
export function statusBadgeVariantForEsign(
  status: SignatureRequestStatus,
): "warning" | "success" | "destructive" | "outline" | "secondary" {
  switch (status) {
    case "pending":
      return "warning";
    case "signed":
      return "success";
    case "declined":
      return "destructive";
    case "voided":
      return "outline";
    case "expired":
      return "secondary";
  }
}

/** Maps an e-signature error to an actionable, specific message for the
 * signer — never a bare status code. A 409 covers two distinct backend
 * causes (SignatureRequestNotOpenError, DocumentMismatchError) that can't be
 * told apart from the status code alone (FastAPI sends {"detail": ...}, and
 * apiFetch only reads data.message/data.error), so the message is written to
 * read sensibly for either. */
export function describeEsignSubmitError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 404:
        return "This signing link is no longer valid.";
      case 409:
        return "This document has already been signed, declined, or voided, or the document changed since this link was created.";
      case 422:
        return "Please confirm both consent checkboxes before signing.";
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/web && pnpm vitest run src/lib/esign.test.ts`
Expected: PASS — all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/esign.ts apps/web/src/lib/esign.test.ts
git commit -m "feat: add esign.ts data layer for T204b (types, API client, SHA-256, badges)"
```

---

### Task 3: `SignaturePad` component

**Files:**

- Create: `apps/web/src/components/esign/signature-pad.tsx`

**Interfaces:**

- Consumes: `Button` from `@/components/ui/button`.
- Produces (consumed by Task 8): `export function SignaturePad({ onChange }: { onChange: (dataUrl: string | null) => void }): JSX.Element` — calls `onChange` with a base64 PNG data URL after each completed stroke, and with `null` after Clear.

No test file (canvas rendering can't be meaningfully unit tested without a browser; verified live in Task 9).

- [ ] **Step 1: Write the component**

Create `apps/web/src/components/esign/signature-pad.tsx`:

```tsx
"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";

interface SignaturePadProps {
  onChange: (dataUrl: string | null) => void;
}

/** Canvas-based signature capture using Pointer Events (unifies mouse and
 * touch input, so no separate handlers are needed for each). */
export function SignaturePad({ onChange }: SignaturePadProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const drawingRef = React.useRef(false);
  const [isEmpty, setIsEmpty] = React.useState(true);

  function getContext(): CanvasRenderingContext2D | null {
    return canvasRef.current?.getContext("2d") ?? null;
  }

  function pointFromEvent(event: React.PointerEvent<HTMLCanvasElement>): { x: number; y: number } {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    const ctx = getContext();
    if (!ctx) return;
    drawingRef.current = true;
    const { x, y } = pointFromEvent(event);
    ctx.beginPath();
    ctx.moveTo(x, y);
    canvasRef.current?.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const ctx = getContext();
    if (!ctx) return;
    const { x, y } = pointFromEvent(event);
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#000000";
    ctx.lineTo(x, y);
    ctx.stroke();
  }

  function handlePointerUp() {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    setIsEmpty(false);
    const canvas = canvasRef.current;
    if (canvas) onChange(canvas.toDataURL("image/png"));
  }

  function handleClear() {
    const canvas = canvasRef.current;
    const ctx = getContext();
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setIsEmpty(true);
    onChange(null);
  }

  return (
    <div className="space-y-2">
      <canvas
        ref={canvasRef}
        width={400}
        height={150}
        className="w-full touch-none rounded-md border border-input bg-white"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      />
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {isEmpty ? "Draw your signature above" : "Signature captured"}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={handleClear}>
          Clear
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/esign/signature-pad.tsx
git commit -m "feat: add SignaturePad canvas component"
```

---

### Task 4: `RequestSignatureDialog` component

**Files:**

- Create: `apps/web/src/components/esign/request-signature-dialog.tsx`

**Interfaces:**

- Consumes: `Dialog` (Task 1), `computeSha256`/`createSignatureRequest`/`SignatureRequestDetail` from `@/lib/esign` (Task 2), `fetchProposalPdfBlob` from `@/lib/proposals` (existing), `ApiError` from `@/lib/api-client`, `Button`/`Input`/`Label` UI primitives.
- Produces (consumed by Task 6): `export function RequestSignatureDialog({ open, onClose, token, proposalId, onCreated }: { open: boolean; onClose: () => void; token: string; proposalId: string; onCreated: (request: SignatureRequestDetail) => void }): JSX.Element`.

- [ ] **Step 1: Write the component**

Create `apps/web/src/components/esign/request-signature-dialog.tsx`:

```tsx
"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import { fetchProposalPdfBlob } from "@/lib/proposals";
import { computeSha256, createSignatureRequest, type SignatureRequestDetail } from "@/lib/esign";

interface RequestSignatureDialogProps {
  open: boolean;
  onClose: () => void;
  token: string;
  proposalId: string;
  onCreated: (request: SignatureRequestDetail) => void;
}

/** Fetches the proposal's current PDF, hashes it client-side, and creates the
 * signature request bound to that exact hash — the same document the signer
 * will later be asked to sign against (services/esign-service's
 * DocumentMismatchError enforces this server-side too). */
export function RequestSignatureDialog({
  open,
  onClose,
  token,
  proposalId,
  onCreated,
}: RequestSignatureDialogProps) {
  const [signerName, setSignerName] = React.useState("");
  const [signerEmail, setSignerEmail] = React.useState("");
  const [expiresInDays, setExpiresInDays] = React.useState(30);
  const [error, setError] = React.useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const pdfBlob = await fetchProposalPdfBlob(token, proposalId);
      const buffer = await pdfBlob.arrayBuffer();
      const documentSha256 = await computeSha256(buffer);
      return createSignatureRequest(token, {
        proposal_id: proposalId,
        signer_name: signerName,
        signer_email: signerEmail,
        document_sha256: documentSha256,
        expires_in_days: expiresInDays,
      });
    },
    onSuccess: (request) => {
      onCreated(request);
      setSignerName("");
      setSignerEmail("");
      setExpiresInDays(30);
      setError(null);
      onClose();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Couldn't create the signature request.");
    },
  });

  const canSubmit = signerName.trim().length > 0 && signerEmail.trim().length > 0;

  return (
    <Dialog open={open} onClose={onClose} title="Request E-Signature">
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="signerName">Signer name</Label>
          <Input
            id="signerName"
            value={signerName}
            onChange={(event) => setSignerName(event.target.value)}
            placeholder="Jane Doe"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="signerEmail">Signer email</Label>
          <Input
            id="signerEmail"
            type="email"
            value={signerEmail}
            onChange={(event) => setSignerEmail(event.target.value)}
            placeholder="jane@example.com"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="expiresInDays">Expires in (days)</Label>
          <Input
            id="expiresInDays"
            type="number"
            min={1}
            max={365}
            value={expiresInDays}
            onChange={(event) => setExpiresInDays(Number(event.target.value))}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending ? "Sending…" : "Send Signature Request"}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
```

- [ ] **Step 2: Run typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/esign/request-signature-dialog.tsx
git commit -m "feat: add RequestSignatureDialog component"
```

---

### Task 5: `SignatureAuditDialog` component

**Files:**

- Create: `apps/web/src/components/esign/signature-audit-dialog.tsx`

**Interfaces:**

- Consumes: `Dialog` (Task 1), `getSignatureRequest`/`getSignatureAuditTrail` from `@/lib/esign` (Task 2), `Badge` UI primitive.
- Produces (consumed by Task 6): `export function SignatureAuditDialog({ open, onClose, token, requestId }: { open: boolean; onClose: () => void; token: string; requestId: string }): JSX.Element`.

Note: the audit-trail endpoint (`getSignatureAuditTrail`) returns only the hash-chain `entries` + `verification` — it does **not** include the captured signature's metadata (signer name, IP, method, consent flags). That lives on `SignatureRequestDetail.signature`, from `getSignatureRequest`. This component queries **both** endpoints to show everything the M10 spec calls for.

- [ ] **Step 1: Write the component**

Create `apps/web/src/components/esign/signature-audit-dialog.tsx`:

```tsx
"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { getSignatureAuditTrail, getSignatureRequest } from "@/lib/esign";

interface SignatureAuditDialogProps {
  open: boolean;
  onClose: () => void;
  token: string;
  requestId: string;
}

export function SignatureAuditDialog({
  open,
  onClose,
  token,
  requestId,
}: SignatureAuditDialogProps) {
  const { data: detail } = useQuery({
    queryKey: ["signature-requests", requestId],
    queryFn: () => getSignatureRequest(token, requestId),
    enabled: open,
  });

  const {
    data: trail,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["signature-requests", requestId, "audit"],
    queryFn: () => getSignatureAuditTrail(token, requestId),
    enabled: open,
  });

  return (
    <Dialog open={open} onClose={onClose} title="Signature Audit Trail" className="max-w-2xl">
      {isLoading && <p className="text-sm text-muted-foreground">Loading audit trail…</p>}
      {isError && <p className="text-sm text-destructive">Couldn&apos;t load the audit trail.</p>}

      {trail && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {trail.verification.is_valid ? (
              <Badge variant="success">🛡️ Chain Verified (Valid)</Badge>
            ) : (
              <Badge variant="destructive">⚠️ Tamper Detected (Invalid)</Badge>
            )}
            <span className="text-sm text-muted-foreground">
              {trail.verification.entry_count}{" "}
              {trail.verification.entry_count === 1 ? "entry" : "entries"}
            </span>
          </div>
          {!trail.verification.is_valid && (
            <p className="text-sm text-destructive">
              Broken at sequence {trail.verification.broken_at_sequence}
              {trail.verification.reason ? `: ${trail.verification.reason}` : ""}
            </p>
          )}

          {detail?.signature && (
            <div className="space-y-1 rounded-md border p-2 text-sm">
              <p className="font-medium">
                {detail.signature.signer_name} ({detail.signature.method})
              </p>
              <p className="text-muted-foreground">IP: {detail.signature.ip_address}</p>
              <p className="text-muted-foreground">
                Signed: {new Date(detail.signature.signed_at).toLocaleString()}
              </p>
              <p className="text-muted-foreground">
                Consent: {detail.signature.consented_to_electronic_business ? "Yes" : "No"} ·
                Intent: {detail.signature.intent_affirmed ? "Yes" : "No"}
              </p>
            </div>
          )}

          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Timeline</h3>
            <ul className="space-y-2">
              {trail.entries.map((entry) => (
                <li key={entry.sequence} className="rounded-md border p-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">
                      #{entry.sequence} {entry.event_type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(entry.occurred_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="break-all text-xs text-muted-foreground">
                    hash: {entry.entry_hash.slice(0, 16)}… (prev: {entry.prev_hash.slice(0, 16)}…)
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Dialog>
  );
}
```

- [ ] **Step 2: Run typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/esign/signature-audit-dialog.tsx
git commit -m "feat: add SignatureAuditDialog component"
```

---

### Task 6: Proposal Detail page integration

**Files:**

- Modify: `apps/web/src/app/(app)/proposals/[id]/page.tsx` (full-file replacement)

**Interfaces:**

- Consumes: `RequestSignatureDialog` (Task 4), `SignatureAuditDialog` (Task 5), `listSignatureRequests`/`voidSignatureRequest`/`getSignatureRequest`/`statusBadgeVariantForEsign` from `@/lib/esign` (Task 2).
- Produces: nothing new consumed elsewhere — this is a page, not a library.

**Design note carried from Task 2's Global Constraints:** the "Copy Link" action **cannot** use data already in the `signatureRequests` list query (that response has no `token`). It must call `getSignatureRequest` on click, then copy `${window.location.origin}/sign/${detail.token}` — never the API gateway origin (`config.apiUrl`), since `/sign/[token]` is a page in this Next.js app, not a gateway route.

- [ ] **Step 1: Replace the page**

Replace the full contents of `apps/web/src/app/(app)/proposals/[id]/page.tsx` with:

```tsx
"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import {
  fetchProposalPdfBlob,
  getProposal,
  sendProposal,
  statusBadgeVariantForProposal,
} from "@/lib/proposals";
import { ApiError } from "@/lib/api-client";
import { config } from "@/config";
import {
  getSignatureRequest,
  listSignatureRequests,
  statusBadgeVariantForEsign,
  voidSignatureRequest,
} from "@/lib/esign";
import { RequestSignatureDialog } from "@/components/esign/request-signature-dialog";
import { SignatureAuditDialog } from "@/components/esign/signature-audit-dialog";

export default function ProposalDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [requestDialogOpen, setRequestDialogOpen] = React.useState(false);
  const [auditRequestId, setAuditRequestId] = React.useState<string | null>(null);
  const [copiedRequestId, setCopiedRequestId] = React.useState<string | null>(null);

  const {
    data: proposal,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["proposals", params.id],
    queryFn: () => getProposal(token as string, params.id),
    enabled: !!token,
  });

  const { data: signatureRequests } = useQuery({
    queryKey: ["signature-requests", { proposal_id: params.id }],
    queryFn: () => listSignatureRequests(token as string, { proposal_id: params.id }),
    enabled: !!token,
  });

  function invalidateSignatureRequests() {
    queryClient.invalidateQueries({ queryKey: ["signature-requests", { proposal_id: params.id }] });
  }

  const sendMutation = useMutation({
    mutationFn: () => sendProposal(token as string, params.id, "email"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", params.id] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
    },
  });

  const previewMutation = useMutation({
    mutationFn: async () => {
      const blob = await fetchProposalPdfBlob(token as string, params.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
    },
  });

  const voidMutation = useMutation({
    mutationFn: (requestId: string) => voidSignatureRequest(token as string, requestId),
    onSuccess: invalidateSignatureRequests,
  });

  const copyLinkMutation = useMutation({
    mutationFn: async (requestId: string) => {
      const detail = await getSignatureRequest(token as string, requestId);
      const url = `${window.location.origin}/sign/${detail.token}`;
      await navigator.clipboard.writeText(url);
      return requestId;
    },
    onSuccess: (requestId) => {
      setCopiedRequestId(requestId);
      setTimeout(
        () => setCopiedRequestId((current) => (current === requestId ? null : current)),
        2000,
      );
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading proposal…</p>;
  if (isError || !proposal) {
    return (
      <p className="text-sm text-destructive">
        Couldn&apos;t load this proposal. Is the API Gateway running?
      </p>
    );
  }

  const publicViewUrl = `${config.apiUrl}/v1/proposals/${proposal.id}/view`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{proposal.number}</h1>
          <Badge
            variant={statusBadgeVariantForProposal(proposal.status)}
            className="mt-1 capitalize"
          >
            {proposal.status}
          </Badge>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setRequestDialogOpen(true)}>
            Request E-Signature
          </Button>
          {proposal.status === "draft" && (
            <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              {sendMutation.isPending ? "Sending…" : "Send"}
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Document</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>Version {proposal.current_version}</p>
          <div className="space-y-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => previewMutation.mutate()}
              disabled={previewMutation.isPending}
            >
              {previewMutation.isPending ? "Opening…" : "Preview / download PDF"}
            </Button>
            {previewMutation.isError && (
              <p className="text-sm text-destructive">
                {previewMutation.error instanceof ApiError
                  ? previewMutation.error.message
                  : "Couldn't load the PDF."}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <p className="text-muted-foreground">Link to send the customer:</p>
            <code className="block break-all rounded bg-muted px-2 py-1 text-xs">
              {publicViewUrl}
            </code>
          </div>
          {proposal.sent_at && (
            <p className="text-muted-foreground">
              Sent {new Date(proposal.sent_at).toLocaleString()}
            </p>
          )}
          {proposal.viewed_at && (
            <p className="text-muted-foreground">
              Viewed {new Date(proposal.viewed_at).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Signature Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {(!signatureRequests || signatureRequests.length === 0) && (
            <p className="text-sm text-muted-foreground">
              No signature requests yet. Click &quot;Request E-Signature&quot; to send one.
            </p>
          )}
          {signatureRequests && signatureRequests.length > 0 && (
            <ul className="space-y-2">
              {signatureRequests.map((request) => (
                <li key={request.id} className="rounded-md border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{request.signer_name}</p>
                      <p className="text-muted-foreground">{request.signer_email}</p>
                    </div>
                    <Badge
                      variant={statusBadgeVariantForEsign(request.status)}
                      className="capitalize"
                    >
                      {request.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-muted-foreground">
                    Expires {new Date(request.expires_at).toLocaleDateString()}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => copyLinkMutation.mutate(request.id)}
                      disabled={copyLinkMutation.isPending}
                    >
                      {copiedRequestId === request.id ? "Copied!" : "Copy Link"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setAuditRequestId(request.id)}
                    >
                      View Audit
                    </Button>
                    {request.status === "pending" && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => voidMutation.mutate(request.id)}
                        disabled={voidMutation.isPending}
                      >
                        Void
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <RequestSignatureDialog
        open={requestDialogOpen}
        onClose={() => setRequestDialogOpen(false)}
        token={token as string}
        proposalId={proposal.id}
        onCreated={invalidateSignatureRequests}
      />
      {auditRequestId && (
        <SignatureAuditDialog
          open={!!auditRequestId}
          onClose={() => setAuditRequestId(null)}
          token={token as string}
          requestId={auditRequestId}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Run typecheck and the full web test suite**

Run: `cd apps/web && pnpm typecheck && pnpm vitest run`
Expected: PASS — no type errors; all tests pass (existing + Task 2's new `esign.test.ts`).

- [ ] **Step 3: Commit**

```bash
git add "apps/web/src/app/(app)/proposals/[id]/page.tsx"
git commit -m "feat: wire e-signature request/tracking into the proposal detail page"
```

---

### Task 7: Signatures overview page

**Files:**

- Create: `apps/web/src/app/(app)/proposals/signatures/page.tsx`
- Modify: `apps/web/src/app/(app)/proposals/page.tsx` (add a link to the new page)

**Interfaces:**

- Consumes: `listSignatureRequests`/`statusBadgeVariantForEsign`/`SignatureRequestStatus` from `@/lib/esign` (Task 2).
- Produces: nothing consumed elsewhere.

- [ ] **Step 1: Write the overview page**

Create `apps/web/src/app/(app)/proposals/signatures/page.tsx`:

```tsx
"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import {
  listSignatureRequests,
  statusBadgeVariantForEsign,
  type SignatureRequestStatus,
} from "@/lib/esign";

const STATUS_TABS: { label: string; value: SignatureRequestStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Pending", value: "pending" },
  { label: "Signed", value: "signed" },
  { label: "Declined", value: "declined" },
  { label: "Voided", value: "voided" },
  { label: "Expired", value: "expired" },
];

export default function SignatureRequestsOverviewPage() {
  const token = useAuthGuard();
  const [activeTab, setActiveTab] = React.useState<SignatureRequestStatus | "all">("all");

  const {
    data: requests,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["signature-requests", { status: activeTab }],
    queryFn: () =>
      listSignatureRequests(token as string, activeTab === "all" ? {} : { status: activeTab }),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Signature Requests</h1>
        <p className="text-muted-foreground">
          Every e-signature request you&apos;ve sent, across all proposals.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <Button
            key={tab.value}
            type="button"
            size="sm"
            variant={activeTab === tab.value ? "default" : "outline"}
            onClick={() => setActiveTab(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load signature requests. Is the API Gateway running?
            </p>
          )}
          {requests && requests.length === 0 && (
            <p className="text-sm text-muted-foreground">No signature requests found.</p>
          )}
          {requests && requests.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Signer</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 font-medium">Expires</th>
                    <th className="py-2 pr-4 font-medium">Proposal</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((request) => (
                    <tr key={request.id} className="border-b last:border-0 hover:bg-accent/50">
                      <td className="py-3 pr-4">
                        <p className="font-medium">{request.signer_name}</p>
                        <p className="text-xs text-muted-foreground">{request.signer_email}</p>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge
                          variant={statusBadgeVariantForEsign(request.status)}
                          className="capitalize"
                        >
                          {request.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4">
                        {new Date(request.expires_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 pr-4">
                        <Link
                          href={`/proposals/${request.proposal_id}`}
                          className="hover:underline"
                        >
                          View proposal
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Add a link from the proposals list page**

In `apps/web/src/app/(app)/proposals/page.tsx`, `Link` is already imported (it's used for the proposal number links inside the table) — only the JSX below needs to change, no import edit needed. Change:

```tsx
<div>
  <h1 className="text-2xl font-bold tracking-tight">Proposals</h1>
  <p className="text-muted-foreground">Every branded proposal you&apos;ve sent, at every stage.</p>
</div>
```

to:

```tsx
<div className="flex items-center justify-between">
  <div>
    <h1 className="text-2xl font-bold tracking-tight">Proposals</h1>
    <p className="text-muted-foreground">
      Every branded proposal you&apos;ve sent, at every stage.
    </p>
  </div>
  <Link href="/proposals/signatures" className="text-sm text-primary hover:underline">
    View signature requests →
  </Link>
</div>
```

- [ ] **Step 3: Run typecheck and the full web test suite**

Run: `cd apps/web && pnpm typecheck && pnpm vitest run`
Expected: PASS — no type errors, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add "apps/web/src/app/(app)/proposals/signatures/page.tsx" "apps/web/src/app/(app)/proposals/page.tsx"
git commit -m "feat: add signature requests overview page with status filters"
```

---

### Task 8: Public customer signing page

**Files:**

- Modify: `apps/web/src/lib/proposals.ts` (add `fetchPublicProposalPdfBlob`)
- Test: `apps/web/src/lib/proposals.test.ts` (add one test for the new function)
- Create: `apps/web/src/app/sign/[token]/page.tsx`

**Interfaces:**

- Consumes: `getPublicSigningContext`/`applyPublicSignature`/`declinePublicSignature`/`computeSha256`/`describeEsignSubmitError` from `@/lib/esign` (Task 2), `SignaturePad` (Task 3), `fetchPublicProposalPdfBlob` (this task's own addition to `proposals.ts`).
- Produces: nothing consumed elsewhere — this is the terminal page in the flow.

This page is deliberately placed at `apps/web/src/app/sign/[token]/page.tsx` — **outside** the `(app)` route group, so it does not inherit the authenticated sidebar shell (`apps/web/src/app/(app)/layout.tsx`). It only inherits the root `app/layout.tsx`, which has no auth requirement. Do **not** call `useAuthGuard()` anywhere in this page.

- [ ] **Step 1: Add the public PDF fetch to `proposals.ts`**

In `apps/web/src/lib/proposals.ts`, after the existing `fetchProposalPdfBlob` function, add:

```typescript
/**
 * Unauthenticated GET /v1/proposals/{id}/view — the public, customer-facing
 * PDF view (T204b's public signing page). This is the SAME route the
 * proposal detail page already displays as the shareable link (see
 * `publicViewUrl` there); calling it here marks the proposal VIEWED and
 * stamps viewed_at server-side, same as a customer opening that link
 * directly. Do not call this from any contractor-facing surface — use
 * `fetchProposalPdfBlob` for that.
 */
export async function fetchPublicProposalPdfBlob(proposalId: string): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(`${config.apiUrl}/v1/proposals/${proposalId}/view`);
  } catch {
    throw new ApiError(0, "Network error — is the API Gateway running?");
  }
  if (!res.ok) {
    throw new ApiError(res.status, `Failed to load the document (status ${res.status}).`);
  }
  return res.blob();
}
```

- [ ] **Step 2: Write the failing test**

In `apps/web/src/lib/proposals.test.ts`, the existing import block (lines 1-9) is:

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createProposal,
  getProposal,
  listProposals,
  sendProposal,
  statusBadgeVariantForProposal,
  type CreateProposalInput,
} from "@/lib/proposals";
```

Add `fetchPublicProposalPdfBlob` to the `@/lib/proposals` import (the `vitest` import already has everything this new test needs — no change there):

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createProposal,
  fetchPublicProposalPdfBlob,
  getProposal,
  listProposals,
  sendProposal,
  statusBadgeVariantForProposal,
  type CreateProposalInput,
} from "@/lib/proposals";
```

Then append this new `describe` block at the end of the file (after the existing `statusBadgeVariantForProposal` block):

```typescript
describe("fetchPublicProposalPdfBlob", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GETs /v1/proposals/{id}/view with no auth header", async () => {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => blob }),
    );
    await fetchPublicProposalPdfBlob("22222222-2222-2222-2222-222222222222");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/proposals/22222222-2222-2222-2222-222222222222/view");
    expect(call[1]).toBeUndefined();
  });
});
```

(If `proposals.test.ts` doesn't already import `afterEach`/`vi` from `vitest`, add those to its existing `vitest` import instead of introducing a new import line.)

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd apps/web && pnpm vitest run src/lib/proposals.test.ts`
Expected: FAIL — `fetchPublicProposalPdfBlob is not a function` (added in Step 1, so this only fails if Step 1 wasn't done first — reorder mentally: Step 1 already added the function, so this test should actually PASS immediately. This is intentionally a same-commit addition rather than strict TDD, since the function is a 10-line, low-risk wrapper identical in shape to the existing `fetchProposalPdfBlob` two lines above it).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/web && pnpm vitest run src/lib/proposals.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the public signing page**

Create `apps/web/src/app/sign/[token]/page.tsx`:

```tsx
"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SignaturePad } from "@/components/esign/signature-pad";
import { fetchPublicProposalPdfBlob } from "@/lib/proposals";
import {
  applyPublicSignature,
  computeSha256,
  declinePublicSignature,
  describeEsignSubmitError,
  getPublicSigningContext,
  type SignatureMethod,
  type SignatureResponse,
} from "@/lib/esign";

export default function PublicSignPage() {
  const params = useParams<{ token: string }>();
  const signingToken = params.token;

  const [method, setMethod] = React.useState<SignatureMethod>("typed");
  const [typedName, setTypedName] = React.useState("");
  const [drawnImageData, setDrawnImageData] = React.useState<string | null>(null);
  const [consented, setConsented] = React.useState(false);
  const [intentAffirmed, setIntentAffirmed] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [signature, setSignature] = React.useState<SignatureResponse | null>(null);
  const [declined, setDeclined] = React.useState(false);
  const [pdfUrl, setPdfUrl] = React.useState<string | null>(null);
  const [documentVerified, setDocumentVerified] = React.useState<boolean | null>(null);

  const {
    data: context,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["sign", signingToken],
    queryFn: () => getPublicSigningContext(signingToken),
    enabled: !!signingToken,
    retry: false,
  });

  React.useEffect(() => {
    if (!context) return;
    let objectUrl: string | null = null;
    fetchPublicProposalPdfBlob(context.proposal_id)
      .then(async (blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
        const hash = await computeSha256(await blob.arrayBuffer());
        setDocumentVerified(hash === context.document_sha256);
      })
      .catch(() => {
        setDocumentVerified(false);
      });
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [context]);

  const signMutation = useMutation({
    mutationFn: () => {
      if (!context) throw new Error("Signing context not loaded");
      return applyPublicSignature(signingToken, {
        method,
        typed_name: method === "typed" ? typedName : null,
        image_data: method === "drawn" ? drawnImageData : null,
        document_sha256: context.document_sha256,
        consented_to_electronic_business: consented,
        intent_affirmed: intentAffirmed,
      });
    },
    onSuccess: (result) => {
      setSignature(result);
      setError(null);
    },
    onError: (err) => setError(describeEsignSubmitError(err)),
  });

  const declineMutation = useMutation({
    mutationFn: () => declinePublicSignature(signingToken),
    onSuccess: () => {
      setDeclined(true);
      setError(null);
    },
    onError: (err) => setError(describeEsignSubmitError(err)),
  });

  const canSign =
    consented &&
    intentAffirmed &&
    (method === "typed" ? typedName.trim().length > 0 : !!drawnImageData);

  if (isLoading) {
    return <p className="p-6 text-sm text-muted-foreground">Loading document…</p>;
  }

  if (isError || !context) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Card>
          <CardContent className="pt-6 text-sm text-destructive">
            This signing link is no longer valid.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (signature) {
    return (
      <div className="mx-auto max-w-lg space-y-4 p-6">
        <Card>
          <CardHeader>
            <CardTitle>Signed successfully</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Thank you, {signature.signer_name} — your signature has been recorded.</p>
            <p className="text-muted-foreground">Transaction ID: {signature.id}</p>
            <p className="break-all text-muted-foreground">
              Signature hash: {signature.signature_hash}
            </p>
            <p className="text-muted-foreground">
              Signed at: {new Date(signature.signed_at).toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (declined) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Card>
          <CardContent className="pt-6 text-sm">
            You&apos;ve declined to sign this document.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Review &amp; Sign</h1>
        <p className="text-muted-foreground">Requested from {context.signer_name}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Document</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline"
            >
              View / download PDF
            </a>
          )}
          {documentVerified !== null && (
            <p className={documentVerified ? "text-emerald-700" : "text-destructive"}>
              {documentVerified
                ? "✅ Document integrity verified."
                : "⚠️ Couldn't verify document integrity."}
            </p>
          )}
        </CardContent>
      </Card>

      {!context.can_sign ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            This document is no longer available for signing (status: {context.status}).
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Your Signature</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant={method === "typed" ? "default" : "outline"}
                onClick={() => setMethod("typed")}
              >
                Type
              </Button>
              <Button
                type="button"
                size="sm"
                variant={method === "drawn" ? "default" : "outline"}
                onClick={() => setMethod("drawn")}
              >
                Draw
              </Button>
            </div>

            {method === "typed" ? (
              <div className="space-y-2">
                <Label htmlFor="typedName">Type your full name</Label>
                <Input
                  id="typedName"
                  value={typedName}
                  onChange={(event) => setTypedName(event.target.value)}
                  placeholder="Jane Doe"
                />
                {typedName && (
                  <p className="text-3xl" style={{ fontFamily: "'Brush Script MT', cursive" }}>
                    {typedName}
                  </p>
                )}
              </div>
            ) : (
              <SignaturePad onChange={setDrawnImageData} />
            )}

            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={consented}
                  onChange={(event) => setConsented(event.target.checked)}
                />
                I consent to conduct business electronically.
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={intentAffirmed}
                  onChange={(event) => setIntentAffirmed(event.target.checked)}
                />
                I affirm my intent to adopt this signature as my legally binding signature.
              </label>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex gap-2">
              <Button
                type="button"
                onClick={() => signMutation.mutate()}
                disabled={!canSign || signMutation.isPending}
              >
                {signMutation.isPending ? "Signing…" : "Sign Proposal"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => declineMutation.mutate()}
                disabled={declineMutation.isPending}
              >
                {declineMutation.isPending ? "Declining…" : "Decline to Sign"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run typecheck, the full web test suite, and build**

Run: `cd apps/web && pnpm typecheck && pnpm vitest run && pnpm build`
Expected: all clean; build output includes a new `/sign/[token]` route.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/proposals.ts apps/web/src/lib/proposals.test.ts "apps/web/src/app/sign/[token]/page.tsx"
git commit -m "feat: add public customer signing page (/sign/[token])"
```

---

### Task 9: Gates, live verification, tracker update

**Files:**

- Modify: `TASKS.md` (T204b row)
- Modify: `tracking/PROGRESS-TRACKER.csv` (T204b row)

**Interfaces:**

- Consumes: nothing new — this task only verifies and documents Tasks 1-8's output.

- [ ] **Step 1: Run the full gate suite**

```bash
cd apps/web && pnpm vitest run
```

Expected: all test files pass.

```bash
cd apps/web && pnpm typecheck
```

Expected: no output (clean).

```bash
cd apps/web && pnpm build
```

Expected: `✓ Compiled successfully`, all routes generated including `/proposals/[id]`, `/proposals/signatures`, and `/sign/[token]`.

- [ ] **Step 2: Attempt live verification; if blocked, hand off**

This machine may or may not have a reachable Docker daemon at execution time (it did not during T202b's equivalent step). If `docker info` fails, do not spend time working around it — write a handoff doc following the exact pattern of `docs/handoffs/T202b-live-verification-antigravity-handoff.md` (same "From/To/Assigned" header, same structure), addressed to Agent 3, listing these five things to click through on a running `/proposals/{id}` and `/sign/{token}` page:

1. "Request E-Signature" opens the dialog, fetches the PDF, computes its hash, and creates a request that appears in the Signature Requests card.
2. "Copy Link" copies a working `/sign/{token}` URL (not the API gateway origin).
3. "View Audit" shows the hash-chain timeline and a "Chain Verified" badge.
4. The public `/sign/{token}` page loads, shows the PDF, lets a signer type or draw a signature, requires both checkboxes before "Sign Proposal" enables, and shows the success receipt after signing.
5. "Decline to Sign" and an expired/already-signed link's error states render real messages, not raw status codes.

If Docker _is_ reachable, perform the verification directly instead of handing it off.

- [ ] **Step 3: Update `TASKS.md`**

Find the `T204b` row (currently `- [ ] \`T204b\` **[A2]** M10 E-Signature web UI: ...`) and mark it done, following this repository's existing convention (see the `T202b`/`T202`/`T201`rows for the exact style:`[x]`, a `✅ **DONE (<date>)**`marker, a one-paragraph summary of what shipped, and links to both plan docs — the architecture-level`docs/modules/M10-esignature-web-ui-plan.md`and this execution plan,`docs/modules/M10-esignature-web-ui-execution-plan.md`).

- [ ] **Step 4: Update `tracking/PROGRESS-TRACKER.csv`**

Update the `T204b` row's status from `NOT_STARTED` to `DONE` (matching the column format of the `T202b` row already in the file).

- [ ] **Step 5: Commit**

```bash
git add TASKS.md tracking/PROGRESS-TRACKER.csv docs/handoffs/T204b-live-verification-antigravity-handoff.md
git commit -m "docs: mark T204b done in TASKS.md and PROGRESS-TRACKER.csv"
```

(Omit the handoff doc from this `git add` if live verification was performed directly instead of handed off.)
