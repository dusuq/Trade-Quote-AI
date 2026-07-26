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

  return app;
}
