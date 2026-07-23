/** Shared types + Fastify request augmentation. */
import "fastify";

export interface AuthClaims {
  sub: string; // user id
  tid: string; // tenant id
  roles: string[];
  iat: number;
  exp: number;
  typ: string;
}

declare module "fastify" {
  interface FastifyRequest {
    auth?: AuthClaims;
  }
}
