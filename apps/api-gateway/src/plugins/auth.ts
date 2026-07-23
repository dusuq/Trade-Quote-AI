/** Fastify plugin: verifies JWTs on every request except the public allowlist. */
import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { verifyBearerToken } from "../auth.js";

/**
 * Exact paths that never require a token — registration/login happen before
 * the client has one, and /health is a liveness probe.
 */
const PUBLIC_PATHS = new Set<string>(["/health", "/v1/auth/register", "/v1/auth/login"]);

function isPublic(url: string): boolean {
  const path = url.split("?")[0] ?? url;
  return PUBLIC_PATHS.has(path);
}

export interface AuthPluginOptions {
  jwtSecret: string;
}

export default fp(
  async function authPlugin(app: FastifyInstance, opts: AuthPluginOptions) {
    app.decorateRequest("auth", undefined);

    app.addHook("onRequest", async (request, reply) => {
      if (isPublic(request.url)) return;

      try {
        request.auth = verifyBearerToken(request.headers.authorization, opts.jwtSecret);
      } catch (err) {
        const message = err instanceof Error ? err.message : "invalid token";
        await reply.code(401).send({ error: "unauthorized", message });
      }
    });
  },
  { name: "auth-plugin" },
);
