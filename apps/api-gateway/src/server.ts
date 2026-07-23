import Fastify, { type FastifyInstance } from "fastify";
import rateLimit from "@fastify/rate-limit";
import { randomUUID } from "node:crypto";
import { config } from "./config.js";
import authPlugin from "./plugins/auth.js";
import { registerServiceProxy } from "./plugins/proxy.js";
import healthRoutes from "./routes/health.js";

export function buildServer(): FastifyInstance {
  const app = Fastify({
    logger: config.nodeEnv !== "test",
    genReqId: () => randomUUID(),
  });

  // Auth must be registered before rate-limit: Fastify runs onRequest hooks
  // in registration order, and the rate-limit key generator below reads
  // `request.auth`, which the auth hook is what sets it.
  app.register(authPlugin);
  app.register(rateLimit, {
    global: true,
    max: config.rateLimitMax,
    timeWindow: config.rateLimitWindowMs,
    keyGenerator: (request) => request.auth?.tid ?? request.ip,
  });

  app.register(healthRoutes);

  // One line per backend service as it ships. Only auth-service exists today.
  registerServiceProxy(app, { prefix: "/v1/auth", upstream: config.authServiceUrl });

  return app;
}
