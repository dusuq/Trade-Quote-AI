import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createProposal,
  getProposal,
  listProposals,
  sendProposal,
  statusBadgeVariantForProposal,
  type CreateProposalInput,
} from "@/lib/proposals";

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

const SAMPLE_PROPOSAL = {
  id: "22222222-2222-2222-2222-222222222222",
  tenant_id: "11111111-1111-1111-1111-111111111111",
  quote_id: "33333333-3333-3333-3333-333333333333",
  template_id: "44444444-4444-4444-4444-444444444444",
  number: "P-2026-000001",
  status: "draft",
  current_version: 1,
  storage_key: "proposals/22222222.pdf",
  sent_at: null,
  viewed_at: null,
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
};

describe("proposals API calls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("createProposal posts to /v1/proposals", async () => {
    mockFetchOnce(201, SAMPLE_PROPOSAL);
    const input: CreateProposalInput = {
      quote_id: "33333333-3333-3333-3333-333333333333",
      template_id: "44444444-4444-4444-4444-444444444444",
      branding: { company_name: "Bright Sparks Electric" },
      customer: { display_name: "Jordan Rivera" },
      line_items: [],
      subtotal_minor: 0,
      tax_minor: 0,
      total_minor: 0,
      currency: "USD",
      scope_of_work: "Test scope",
    };
    const result = await createProposal("tok", input);
    expect(result.number).toBe("P-2026-000001");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain("/v1/proposals");
    expect(call[1]?.method).toBe("POST");
  });

  it("listProposals gets /v1/proposals", async () => {
    mockFetchOnce(200, [SAMPLE_PROPOSAL]);
    const result = await listProposals("tok");
    expect(result).toHaveLength(1);
  });

  it("getProposal gets /v1/proposals/:id", async () => {
    mockFetchOnce(200, SAMPLE_PROPOSAL);
    const result = await getProposal("tok", SAMPLE_PROPOSAL.id);
    expect(result.id).toBe(SAMPLE_PROPOSAL.id);
  });

  it("sendProposal posts to /v1/proposals/:id/send", async () => {
    mockFetchOnce(200, { ...SAMPLE_PROPOSAL, status: "sent" });
    const result = await sendProposal("tok", SAMPLE_PROPOSAL.id, "email");
    expect(result.status).toBe("sent");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/proposals/${SAMPLE_PROPOSAL.id}/send`);
  });
});

describe("statusBadgeVariantForProposal", () => {
  it("maps viewed to default", () => {
    expect(statusBadgeVariantForProposal("viewed")).toBe("default");
  });
  it("maps sent to default", () => {
    expect(statusBadgeVariantForProposal("sent")).toBe("default");
  });
  it("maps draft to warning", () => {
    expect(statusBadgeVariantForProposal("draft")).toBe("warning");
  });
});
