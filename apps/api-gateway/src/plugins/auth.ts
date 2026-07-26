/** Fastify plugin: verifies JWTs on every request except the public allowlist. */
import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { verifyBearerToken } from "../auth.js";

/**
 * Exact paths that never require a token — registration/login happen before
 * the client has one, and /health is a liveness probe.
 */
const PUBLIC_PATHS = new Set<string>(["/health", "/v1/auth/register", "/v1/auth/login"]);

/**
 * Path *patterns* that never require a token, for routes with a dynamic
 * segment. Keep this list short and each entry narrowly scoped — a public
 * route is a route with no tenant check at all downstream, so a pattern
 * that's too broad here is a real authorization bypass, not just a bug.
 */
const PUBLIC_PATH_PATTERNS: RegExp[] = [
  // Customer-facing proposal view link — proposal-service resolves its own
  // tenant from the id; see services/proposal-service's TenantResolver.
  /^\/v1\/proposals\/[0-9a-fA-F-]+\/view$/,
];

function isPublic(url: string): boolean {
  const path = url.split("?")[0] ?? url;
  if (PUBLIC_PATHS.has(path)) return true;
  return PUBLIC_PATH_PATTERNS.some((pattern) => pattern.test(path));
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
