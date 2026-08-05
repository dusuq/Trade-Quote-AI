import Fastify, { type FastifyInstance } from "fastify";
import rateLimit from "@fastify/rate-limit";
import { randomUUID } from "node:crypto";
import { config as defaultConfig, type Config } from "./config.js";
import authPlugin from "./plugins/auth.js";
import observabilityPlugin from "./plugins/observability.js";
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

  // Registered first so its onResponse hook (request count/latency) times the
  // full request lifecycle, including auth rejections and rate-limit 429s —
  // not just what happens after those checks pass.
  app.register(observabilityPlugin, {
    serviceName: "api-gateway",
    serviceEnv: cfg.nodeEnv,
    sentryDsn: cfg.sentryDsn,
    otelEndpoint: cfg.otelExporterOtlpEndpoint,
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
  // It carries NO bodyLimit of its own (T201c). It used to pin 12 MiB here,
  // which applied to every route in the gateway - including the public,
  // unauthenticated ones (GET /v1/proposals/{id}/view, /v1/sign/*,
  // /v1/payments/webhooks/*), letting an anonymous caller make the gateway
  // buffer 12 MiB of arbitrary bytes per request before anything rejected
  // it. Authenticated routes were never exposed: auth is an onRequest hook,
  // so it 401s before the body is read.
  //
  // Omitting it here means every route falls back to Fastify's documented
  // 1 MiB default, and the prefixes that genuinely receive uploads opt
  // upward explicitly via registerServiceProxy's `bodyLimit` below. Keeping
  // the parser itself global is deliberate: this is a generic reverse proxy,
  // and restricting *which* content types it can forward would turn the
  // gateway into an allowlist that has to be kept in lockstep with every
  // service - the same coupling that produced the T203 bare-prefix 404.
  // The bytes are what needed bounding, not the content types.
  app.addContentTypeParser("*", { parseAs: "buffer" }, (_req, body, done) => {
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

  // One line per backend service as it ships. Anything without an explicit
  // bodyLimit inherits Fastify's 1 MiB default — see the parser note above.
  registerServiceProxy(app, { prefix: "/v1/auth", upstream: cfg.authServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/customers", upstream: cfg.customerServiceUrl });
  // Upload prefix: POST /v1/pricebook/import takes a multipart CSV
  // (pricebook-service routes.py `import_csv`). 8 MiB is roughly 40k-70k
  // catalog rows, comfortably above any real trade pricebook. Note this
  // gateway limit is currently the *only* cap on that import —
  // pricebook-service itself reads the upload with no size check of its own.
  registerServiceProxy(app, {
    prefix: "/v1/pricebook",
    upstream: cfg.pricebookServiceUrl,
    bodyLimit: 8 * 1024 * 1024,
  });
  registerServiceProxy(app, { prefix: "/v1/quotes", upstream: cfg.quoteServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/proposals", upstream: cfg.proposalServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/proposal-templates", upstream: cfg.proposalServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/analytics", upstream: cfg.analyticsServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/signature-requests", upstream: cfg.esignServiceUrl });
  // Public customer-facing signing links — see PUBLIC_PATH_PATTERNS in plugins/auth.ts.
  registerServiceProxy(app, { prefix: "/v1/sign", upstream: cfg.esignServiceUrl });
  // Upload prefix: voice-to-quote (audio), vision/detect-equipment +
  // vision-to-quote (photo), and ocr/extract + ocr-to-quote (document photo)
  // are all multipart. 12 MiB covers ai-service's own largest input cap —
  // 10 MiB max_audio_size_bytes (app/config.py) — plus multipart overhead,
  // so the gateway never 413s an upload the service itself would have
  // accepted. Every route here is authenticated.
  registerServiceProxy(app, {
    prefix: "/v1/ai",
    upstream: cfg.aiServiceUrl,
    bodyLimit: 12 * 1024 * 1024,
  });
  registerServiceProxy(app, { prefix: "/v1/notifications", upstream: cfg.notificationServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/payments", upstream: cfg.paymentServiceUrl });
  registerServiceProxy(app, { prefix: "/v1/integrations", upstream: cfg.integrationServiceUrl });

  return app;
}
