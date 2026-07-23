/**
 * JWT verification core — pure, framework-free, directly unit-testable.
 * Verifies the same HS256 tokens issued by services/auth-service (T101).
 */
import jwt from "jsonwebtoken";
import type { AuthClaims } from "./types.js";

export class MissingTokenError extends Error {}
export class InvalidTokenError extends Error {}

const BEARER_PREFIX = "bearer ";

export function verifyBearerToken(
  authorizationHeader: string | undefined,
  secret: string,
): AuthClaims {
  if (!authorizationHeader || !authorizationHeader.toLowerCase().startsWith(BEARER_PREFIX)) {
    throw new MissingTokenError("missing bearer token");
  }
  const token = authorizationHeader.slice(BEARER_PREFIX.length).trim();
  if (!token) {
    throw new MissingTokenError("empty bearer token");
  }

  try {
    const decoded = jwt.verify(token, secret, { algorithms: ["HS256"] });
    if (typeof decoded === "string" || !decoded) {
      throw new InvalidTokenError("unexpected token payload shape");
    }
    return decoded as unknown as AuthClaims;
  } catch (err) {
    if (err instanceof MissingTokenError || err instanceof InvalidTokenError) throw err;
    const message = err instanceof Error ? err.message : "invalid token";
    throw new InvalidTokenError(message);
  }
}
