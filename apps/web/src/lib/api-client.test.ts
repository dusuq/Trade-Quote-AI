import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiError } from "@/lib/api-client";

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

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on success", async () => {
    mockFetchOnce(200, { hello: "world" });
    const result = await apiFetch<{ hello: string }>("/v1/ping");
    expect(result).toEqual({ hello: "world" });
  });

  it("throws ApiError with the status code on failure", async () => {
    mockFetchOnce(401, { message: "invalid credentials" });
    await expect(apiFetch("/v1/auth/login")).rejects.toMatchObject({
      status: 401,
      message: "invalid credentials",
    });
  });

  it("throws ApiError as instanceof ApiError", async () => {
    mockFetchOnce(500, { error: "boom" });
    await expect(apiFetch("/v1/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("attaches the bearer token when provided", async () => {
    mockFetchOnce(200, { ok: true });
    await apiFetch("/v1/protected", { token: "abc123" });
    const call = vi.mocked(fetch).mock.calls[0];
    const headers = call[1]?.headers as Record<string, string>;
    expect(headers.authorization).toBe("Bearer abc123");
  });

  it("sends a JSON body on POST", async () => {
    mockFetchOnce(201, { id: 1 });
    await apiFetch("/v1/things", { method: "POST", body: { name: "widget" } });
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[1]?.method).toBe("POST");
    expect(call[1]?.body).toBe(JSON.stringify({ name: "widget" }));
  });

  it("passes an AbortSignal so a hung request cannot stall forever", async () => {
    mockFetchOnce(200, { ok: true });
    await apiFetch("/v1/things");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("wraps a network-level rejection (e.g. connection refused) as an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiFetch("/v1/quotes")).rejects.toMatchObject({ status: 0 });
    await expect(apiFetch("/v1/quotes")).rejects.toBeInstanceOf(ApiError);
  });

  it("wraps an abort timeout as an ApiError with a clear message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("The operation was aborted.", "TimeoutError")),
    );
    await expect(apiFetch("/v1/quotes")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("timed out"),
    });
  });
});
