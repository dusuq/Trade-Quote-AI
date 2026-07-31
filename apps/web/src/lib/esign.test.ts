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
