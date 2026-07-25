import { z } from "zod";
import { apiFetch } from "@/lib/api-client";

/** Validation schemas — pure, unit-tested (see src/lib/auth.test.ts). */
export const loginSchema = z.object({
  slug: z
    .string()
    .min(2, "Workspace is required")
    .regex(/^[a-z0-9-]+$/, "Lowercase letters, numbers, and hyphens only"),
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
  totpCode: z.string().optional(),
});

export const registerSchema = z.object({
  tenantName: z.string().min(2, "Company name is required").max(120),
  slug: z
    .string()
    .min(2, "Workspace URL is required")
    .max(60)
    .regex(/^[a-z0-9-]+$/, "Lowercase letters, numbers, and hyphens only"),
  ownerEmail: z.string().email("Enter a valid email"),
  ownerPassword: z.string().min(8, "At least 8 characters"),
  ownerName: z.string().optional(),
});

export type LoginInput = z.infer<typeof loginSchema>;
export type RegisterInput = z.infer<typeof registerSchema>;

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export function login(input: LoginInput): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/v1/auth/login", {
    method: "POST",
    body: {
      slug: input.slug,
      email: input.email,
      password: input.password,
      totp_code: input.totpCode || null,
    },
  });
}

export function register(input: RegisterInput): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/v1/auth/register", {
    method: "POST",
    body: {
      tenant_name: input.tenantName,
      slug: input.slug,
      owner_email: input.ownerEmail,
      owner_password: input.ownerPassword,
      owner_name: input.ownerName || null,
    },
  });
}
