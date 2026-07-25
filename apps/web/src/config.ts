/**
 * Client-side runtime config. NEXT_PUBLIC_* vars are inlined into the browser
 * bundle at build time. The API base points at the API Gateway (apps/api-gateway).
 */
export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
} as const;
