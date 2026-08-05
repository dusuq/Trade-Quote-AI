import { afterEach, describe, expect, it, vi } from "vitest";
import { createTemplate, listTemplates, updateTemplate } from "@/lib/proposal-templates";

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

const SAMPLE_TEMPLATE = {
  id: "55555555-5555-5555-5555-555555555555",
  tenant_id: "11111111-1111-1111-1111-111111111111",
  name: "Standard",
  company_name: "Bright Sparks Electric",
  logo_url: null,
  primary_color: "#111827",
  phone: null,
  email: null,
  website: null,
  default_terms_text: null,
  default_warranty_text: null,
  is_default: true,
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
};

describe("proposal-templates API calls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listTemplates gets /v1/proposal-templates", async () => {
    mockFetchOnce(200, [SAMPLE_TEMPLATE]);
    const result = await listTemplates("tok");
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Standard");
  });

  it("createTemplate posts to /v1/proposal-templates", async () => {
    mockFetchOnce(201, SAMPLE_TEMPLATE);
    const result = await createTemplate("tok", {
      name: "Standard",
      company_name: "Bright Sparks Electric",
    });
    expect(result.id).toBe(SAMPLE_TEMPLATE.id);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[1]?.method).toBe("POST");
  });

  it("updateTemplate puts to /v1/proposal-templates/:id", async () => {
    mockFetchOnce(200, { ...SAMPLE_TEMPLATE, primary_color: "#000000" });
    const result = await updateTemplate("tok", SAMPLE_TEMPLATE.id, { primary_color: "#000000" });
    expect(result.primary_color).toBe("#000000");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toContain(`/v1/proposal-templates/${SAMPLE_TEMPLATE.id}`);
    expect(call[1]?.method).toBe("PUT");
  });
});
