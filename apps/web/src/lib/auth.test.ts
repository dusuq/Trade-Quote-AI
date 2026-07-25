import { describe, expect, it } from "vitest";
import { loginSchema, registerSchema } from "@/lib/auth";

describe("loginSchema", () => {
  const valid = { slug: "acme-electric", email: "a@b.com", password: "secret123" };

  it("accepts a valid payload", () => {
    expect(loginSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects an uppercase or spaced slug", () => {
    expect(loginSchema.safeParse({ ...valid, slug: "Acme Electric" }).success).toBe(false);
  });

  it("rejects a malformed email", () => {
    expect(loginSchema.safeParse({ ...valid, email: "not-an-email" }).success).toBe(false);
  });

  it("rejects an empty password", () => {
    expect(loginSchema.safeParse({ ...valid, password: "" }).success).toBe(false);
  });

  it("allows an optional totpCode", () => {
    expect(loginSchema.safeParse({ ...valid, totpCode: "123456" }).success).toBe(true);
  });
});

describe("registerSchema", () => {
  const valid = {
    tenantName: "Acme Electric",
    slug: "acme-electric",
    ownerEmail: "owner@acme.com",
    ownerPassword: "supersecret",
  };

  it("accepts a valid payload", () => {
    expect(registerSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects a password under 8 characters", () => {
    expect(registerSchema.safeParse({ ...valid, ownerPassword: "short" }).success).toBe(false);
  });

  it("rejects a slug with uppercase or special characters", () => {
    expect(registerSchema.safeParse({ ...valid, slug: "Acme_Electric!" }).success).toBe(false);
  });

  it("rejects a company name under 2 characters", () => {
    expect(registerSchema.safeParse({ ...valid, tenantName: "A" }).success).toBe(false);
  });

  it("ownerName is optional", () => {
    const result = registerSchema.safeParse(valid);
    expect(result.success).toBe(true);
  });
});
