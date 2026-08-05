/** Runtime configuration, validated from environment (12-factor). */
import { z } from "zod";

/**
 * The committed dev-only JWT secret (T310).
 *
 * This value lives in a public repository. Anyone can read it, mint an HS256
 * token with any `tid` and `roles`, and the gateway would accept it — the
 * proxy then injects that forged tenant id downstream as a *trusted*
 * `x-tenant-id` header. That is full cross-tenant compromise plus privilege
 * escalation, from a single unset environment variable.
 *
 * It stays as a default so `docker compose up` works with no setup, but
 * `assertProductionSecrets` below makes a non-local environment refuse to
 * boot with it. Failing closed at startup is the entire point: the previous
 * behaviour failed OPEN — silently, and indistinguishably from a correctly
 * configured deployment.
 */
export const DEV_ONLY_JWT_SECRET = "local-dev-only-change-me-32byte-minimum-secret";

/** Environments that must never run on development defaults. */
const NON_LOCAL_ENVS = new Set(["production", "prod", "staging", "preprod"]);

export function isNonLocalEnv(nodeEnv: string): boolean {
  return NON_LOCAL_ENVS.has(nodeEnv.trim().toLowerCase());
}

/**
 * Minimum entropy for an HS256 signing key. A key shorter than the 256-bit
 * hash output weakens the construction, and a short human-chosen secret is
 * brute-forceable offline from any single captured token.
 */
const MIN_PRODUCTION_SECRET_LENGTH = 32;

const EnvSchema = z.object({
  NODE_ENV: z.string().default("local"),
  PORT: z.coerce.number().int().positive().default(8000),

  // Must match the auth-service's JWT_SECRET — same trust domain.
  JWT_SECRET: z.string().min(1).default(DEV_ONLY_JWT_SECRET),

  // Upstream service base URLs. Add one per service as it comes online.
  AUTH_SERVICE_URL: z.string().url().default("http://localhost:8001"),
  CUSTOMER_SERVICE_URL: z.string().url().default("http://localhost:8002"),
  PRICEBOOK_SERVICE_URL: z.string().url().default("http://localhost:8003"),
  QUOTE_SERVICE_URL: z.string().url().default("http://localhost:8004"),
  PROPOSAL_SERVICE_URL: z.string().url().default("http://localhost:8005"),
  ANALYTICS_SERVICE_URL: z.string().url().default("http://localhost:8006"),
  ESIGN_SERVICE_URL: z.string().url().default("http://localhost:8007"),
  AI_SERVICE_URL: z.string().url().default("http://localhost:8008"),
  NOTIFICATION_SERVICE_URL: z.string().url().default("http://localhost:8009"),
  PAYMENT_SERVICE_URL: z.string().url().default("http://localhost:8010"),
  INTEGRATION_SERVICE_URL: z.string().url().default("http://localhost:8011"),

  RATE_LIMIT_MAX: z.coerce.number().int().positive().default(100),
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().positive().default(60_000),

  // Observability (T309b). Empty by default so every piece is opt-in — see
  // plugins/observability.ts.
  SENTRY_DSN: z.string().default(""),
  OTEL_EXPORTER_OTLP_ENDPOINT: z.string().default(""),
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
  analyticsServiceUrl: string;
  esignServiceUrl: string;
  aiServiceUrl: string;
  notificationServiceUrl: string;
  paymentServiceUrl: string;
  integrationServiceUrl: string;
  rateLimitMax: number;
  rateLimitWindowMs: number;
  sentryDsn: string;
  otelExporterOtlpEndpoint: string;
};

/**
 * Refuse to run a non-local environment on development defaults (T310).
 *
 * Throws rather than warns, deliberately. A warning in a log nobody reads is
 * how the fail-open state survives to production; a process that won't start
 * gets noticed during the deploy, which is the cheapest possible moment.
 */
export function assertProductionSecrets(cfg: Pick<Config, "nodeEnv" | "jwtSecret">): void {
  if (!isNonLocalEnv(cfg.nodeEnv)) return;

  const problems: string[] = [];

  if (cfg.jwtSecret === DEV_ONLY_JWT_SECRET) {
    problems.push(
      "JWT_SECRET is still the committed dev default. It is public in this repo, so " +
        "anyone could forge a token for any tenant with any role. Set a unique, random " +
        "secret (e.g. `openssl rand -base64 48`) that matches auth-service's JWT_SECRET.",
    );
  } else if (cfg.jwtSecret.length < MIN_PRODUCTION_SECRET_LENGTH) {
    problems.push(
      `JWT_SECRET is only ${cfg.jwtSecret.length} characters; HS256 signing keys must be at ` +
        `least ${MIN_PRODUCTION_SECRET_LENGTH}. Short secrets are brute-forceable offline ` +
        "from a single captured token.",
    );
  }

  if (problems.length > 0) {
    throw new Error(
      `Refusing to start in NODE_ENV="${cfg.nodeEnv}" with insecure configuration:\n` +
        problems.map((p) => `  - ${p}`).join("\n"),
    );
  }
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const parsed = EnvSchema.parse(env);
  const cfg: Config = {
    nodeEnv: parsed.NODE_ENV,
    port: parsed.PORT,
    jwtSecret: parsed.JWT_SECRET,
    authServiceUrl: parsed.AUTH_SERVICE_URL,
    customerServiceUrl: parsed.CUSTOMER_SERVICE_URL,
    pricebookServiceUrl: parsed.PRICEBOOK_SERVICE_URL,
    quoteServiceUrl: parsed.QUOTE_SERVICE_URL,
    proposalServiceUrl: parsed.PROPOSAL_SERVICE_URL,
    analyticsServiceUrl: parsed.ANALYTICS_SERVICE_URL,
    esignServiceUrl: parsed.ESIGN_SERVICE_URL,
    aiServiceUrl: parsed.AI_SERVICE_URL,
    notificationServiceUrl: parsed.NOTIFICATION_SERVICE_URL,
    paymentServiceUrl: parsed.PAYMENT_SERVICE_URL,
    integrationServiceUrl: parsed.INTEGRATION_SERVICE_URL,
    rateLimitMax: parsed.RATE_LIMIT_MAX,
    rateLimitWindowMs: parsed.RATE_LIMIT_WINDOW_MS,
    sentryDsn: parsed.SENTRY_DSN,
    otelExporterOtlpEndpoint: parsed.OTEL_EXPORTER_OTLP_ENDPOINT,
  };

  assertProductionSecrets(cfg);
  return cfg;
}

export const config = loadConfig();
