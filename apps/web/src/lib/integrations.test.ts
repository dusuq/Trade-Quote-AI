import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import {
  connectZapier,
  createConnection,
  describeConnectionError,
  listConnections,
  listSyncLogs,
  pushInvoiceSync,
  PROVIDER_LABELS,
  revokeConnection,
  startOAuth,
  statusBadgeVariantForConnection,
  statusBadgeVariantForSync,
} from "@/lib/integrations";

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

const SAMPLE_CONNECTION = {
  id: "11111111-1111-1111-1111-111111111111",
  provider: "quickbooks",
  status: "pending",
  external_account_id: null,
  display_name: "QuickBooks Integration",
  scopes: null,
  token_expires_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  created_by: null,
};

describe("listConnections", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("unwraps the items array from the paginated response", async () => {
    mockFetchOnce(200, { items: [SAMPLE_CONNECTION], total: 1 });
    const result = await listConnections("tok");
    expect(result).toEqual([SAMPLE_CONNECTION]);
  });
});

describe("createConnection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the provider to /v1/integrations/connections", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      text: async () => JSON.stringify(SAMPLE_CONNECTION),
    });
    vi.stubGlobal("fetch", fetchMock);

    await createConnection("tok", { provider: "quickbooks" });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/v1/integrations/connections");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ provider: "quickbooks" });
  });
});

describe("startOAuth", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to the connection's oauth/start endpoint and returns the authorize_url", async () => {
    mockFetchOnce(200, {
      connection: SAMPLE_CONNECTION,
      authorize_url: "https://provider.test/authorize",
    });
    const result = await startOAuth("tok", SAMPLE_CONNECTION.id);
    expect(result.authorize_url).toBe("https://provider.test/authorize");
  });
});

describe("connectZapier", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the one-time api_key", async () => {
    mockFetchOnce(200, {
      connection: { ...SAMPLE_CONNECTION, provider: "zapier", status: "active" },
      api_key: "zap-secret-123",
    });
    const result = await connectZapier("tok", SAMPLE_CONNECTION.id);
    expect(result.api_key).toBe("zap-secret-123");
  });
});

describe("revokeConnection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to the connection's revoke endpoint", async () => {
    mockFetchOnce(200, { ...SAMPLE_CONNECTION, status: "revoked" });
    const result = await revokeConnection("tok", SAMPLE_CONNECTION.id);
    expect(result.status).toBe("revoked");
  });
});

describe("listSyncLogs", () => {
  afterEach(() => vi.unstubAllGlobals());

  const SAMPLE_LOG = {
    id: "22222222-2222-2222-2222-222222222222",
    connection_id: SAMPLE_CONNECTION.id,
    direction: "push",
    entity_type: "invoice",
    entity_id: null,
    status: "success",
    external_id: "qb-inv-1",
    error_message: null,
    started_at: "2026-08-01T00:00:00Z",
    completed_at: "2026-08-01T00:00:01Z",
  };

  it("unwraps the items array and includes the limit query param", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ items: [SAMPLE_LOG], total: 1 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await listSyncLogs("tok", SAMPLE_CONNECTION.id, 10);

    expect(result).toEqual([SAMPLE_LOG]);
    expect(fetchMock.mock.calls[0][0]).toContain("limit=10");
  });
});

describe("pushInvoiceSync", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the payload to the connection's sync/push endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      text: async () =>
        JSON.stringify({
          id: "3",
          connection_id: SAMPLE_CONNECTION.id,
          direction: "push",
          entity_type: "invoice",
          entity_id: null,
          status: "success",
          external_id: "qb-inv-2",
          error_message: null,
          started_at: "2026-08-01T00:00:00Z",
          completed_at: "2026-08-01T00:00:01Z",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await pushInvoiceSync("tok", SAMPLE_CONNECTION.id, {
      entity_type: "invoice",
      payload: { Line: [] },
    });

    expect(result.status).toBe("success");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/sync/push");
    expect(JSON.parse(options.body)).toEqual({ entity_type: "invoice", payload: { Line: [] } });
  });
});

describe("statusBadgeVariantForConnection", () => {
  it.each([
    ["active", "success"],
    ["pending", "warning"],
    ["expired", "warning"],
    ["revoked", "outline"],
    ["error", "destructive"],
  ] as const)("maps %s to %s", (status, expected) => {
    expect(statusBadgeVariantForConnection(status)).toBe(expected);
  });
});

describe("statusBadgeVariantForSync", () => {
  it.each([
    ["success", "success"],
    ["running", "warning"],
    ["pending", "warning"],
    ["failed", "destructive"],
  ] as const)("maps %s to %s", (status, expected) => {
    expect(statusBadgeVariantForSync(status)).toBe(expected);
  });
});

describe("PROVIDER_LABELS", () => {
  it("has a human label for every provider", () => {
    expect(PROVIDER_LABELS.quickbooks).toBe("QuickBooks Online");
    expect(PROVIDER_LABELS.xero).toBe("Xero");
    expect(PROVIDER_LABELS.zapier).toBe("Zapier");
  });
});

describe("describeConnectionError", () => {
  it("maps a 404 to a specific message", () => {
    expect(describeConnectionError(new ApiError(404, "not found"))).toBe(
      "That connection no longer exists.",
    );
  });

  it("falls back to the server message for a 409", () => {
    expect(describeConnectionError(new ApiError(409, "connection is revoked, not pending"))).toBe(
      "connection is revoked, not pending",
    );
  });

  it("falls back to a generic message for a non-ApiError", () => {
    expect(describeConnectionError(new Error("boom"))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});
