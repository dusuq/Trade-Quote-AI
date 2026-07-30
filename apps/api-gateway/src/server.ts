import Fastify, { type FastifyInstance } from "fastify";
import rateLimit from "@fastify/rate-limit";
import { randomUUID } from "node:crypto";
import { config as defaultConfig, type Config } from "./config.js";
import authPlugin from "./plugins/auth.js";
import { registerServiceProxy } from "./plugins/proxy.js";
import healthRoutes from "./routes/health.js";

/**
 * Config is passed explicitly (defaulting to the process-env singleton)
 * rather than imported deep in each plugin — keeps the gateway composable
 * and lets tests inject a fully isolated config without env/import races.
 */
export function buildServer(overrides: Partial<Config> = {}): FastifyInstance {
  const cfg: Config = { ...defaultConfig, ...overrides };

  const app = Fastify({
    logger: cfg.nodeEnv !== "test",
    genReqId: () => randomUUID(),
  });

  // Auth must be registered before rate-limit: Fastify runs onRequest hooks
  // in registration order, and the rate-limit key generator below reads
  // `request.auth`, which the auth hook is what sets it.
  // Fastify has no built-in parser for multipart/form-data (or any other
  // non-JSON/text content type), so without this a multipart POST - e.g.
  // T201b's voice-to-quote audio upload - 415s (FST_ERR_CTP_INVALID_MEDIA_TYPE)
  // before the route handler ever runs. This catch-all captures anything
  // without an existing parser as a raw Buffer so the proxy can forward it
  // unchanged; it does not affect application/json or text/plain, which
  // already have built-in parsers and take precedence over this wildcard.
  //
  // bodyLimit is explicit because Fastify's own default (1 MiB) is well
  // below what a real recording needs - ai-service accepts audio up to
  // 10 MiB (max_audio_size_bytes, app/config.py) - and the parser silently
  // inheriting the 1 MiB default would 413 any voice upload over about a
  // minute, at the gateway, before ai-service's own limit is ever checked.
  app.addContentTypeParser("*", { parseAs: "buffer", bodyLimit: 12 * 1024 * 1024 }, (_req, body, done) => {
    done(null, body);
  });

  app.register(authPlugin, { jwtSecret: cfg.jwtSecret });
  app.register(rateLimit, {
    global: true,
    max: cfg.rateLimitMax,
    timeWindow: cfg.rateLimitWindowMs,
    keyGenerator: (request) => request.auth?.tid ?? request.ip,
  });

  app.register(healthRoutes);

  // One line per backend service as it ships.
  registerServiceProxy(app, { prefix: "/v1/auth", upstream: cfg.authServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/customers", upstream: cfg.customerServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/pricebook", upstream: cfg.pricebookServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/quotes", upstream: cfg.quoteServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/proposals", upstream: cfg.proposalServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/proposal-templates", upstream: cfg.proposalServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/analytics", upstream: cfg.analyticsServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/signature-requests", upstream: cfg.esignServiceUrl });
  // Public customer-facing signing links — see PUBLIC_PATH_PATTERNS in plugins/auth.ts.
  registerServiceProxy(app, { prefix: "/v1/sign", upstream: cfg.esignServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/ai", upstream: cfg.aiServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/notifications", upstream: cfg.notificationServiceUrl });

  return app;
}
