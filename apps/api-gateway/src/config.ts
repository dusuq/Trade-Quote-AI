/** Runtime configuration, validated from environment (12-factor). */
import { z } from "zod";

const EnvSchema = z.object({
  NODE_ENV: z.string().default("local"),
  PORT: z.coerce.number().int().positive().default(8000),

  // Must match the auth-service's JWT_SECRET — same trust domain.
  JWT_SECRET: z.string().min(1).default("local-dev-only-change-me-32byte-minimum-secret"),

  // Upstream service base URLs. Add one per service as it comes online.
  AUTH_SERVICE_URL: z.string().url().default("http://localhost:8001"),
  CUSTOMER_SERVICE_URL: z.string().url().default("http://localhost:8002"),
  PRICEBOOK_SERVICE_URL: z.string().url().default("http://localhost:8003"),
  QUOTE_SERVICE_URL: z.string().url().default("http://localhost:8004"),
  PROPOSAL_SERVICE_URL: z.string().url().default("http://localhost:8005"),

  RATE_LIMIT_MAX: z.coerce.number().int().positive().default(100),
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().positive().default(60_000),
});

export type Config = {
  nodeEnv: string;
  port: number;
  jwtSecret: string;
  authServiceUrl: string;
  customerServiceUrl: string;
  pricebookServiceUrl: string;
  quoteServiceUrl: string;
  proposalServiceUrl: string;
  rateLimitMax: number;
  rateLimitWindowMs: number;
};

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const parsed = EnvSchema.parse(env);
  return {
    nodeEnv: parsed.NODE_ENV,
    port: parsed.PORT,
    jwtSecret: parsed.JWT_SECRET,
    authServiceUrl: parsed.AUTH_SERVICE_URL,
    customerServiceUrl: parsed.CUSTOMER_SERVICE_URL,
    pricebookServiceUrl: parsed.PRICEBOOK_SERVICE_URL,
    quoteServiceUrl: parsed.QUOTE_SERVICE_URL,
    proposalServiceUrl: parsed.PROPOSAL_SERVICE_URL,
    rateLimitMax: parsed.RATE_LIMIT_MAX,
    rateLimitWindowMs: parsed.RATE_LIMIT_WINDOW_MS,
  };
}

export const config = loadConfig();
