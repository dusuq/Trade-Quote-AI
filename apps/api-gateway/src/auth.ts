/**
 * JWT verification core — pure, framework-free, directly unit-testable.
 * Verifies the same HS256 tokens issued by services/auth-service (T101).
 */
import jwt from "jsonwebtoken";
import type { AuthClaims } from "./types.js";

/**
 * Why a request failed authentication (T310b / M27).
 *
 * This is a *metric label*, so the set is closed and deliberately small — an
 * unbounded label explodes Prometheus cardinality, and raw `jsonwebtoken`
 * messages are attacker-influenced text. The distinction that matters
 * operationally is the last three: a missing or expired token is ordinary
 * traffic (a logged-out tab, a stale session), while a *wrong signature* or a
 * *wrong algorithm* is nobody's accident — it is someone trying to mint a
 * token. Collapsing those into one "invalid" bucket is what made a forgery
 * attempt invisible before T310b, so they stay separate.
 */
export type AuthFailureReason =
  | "missing_token"
  | "malformed_token"
  | "expired_token"
  | "not_yet_valid_token"
  | "invalid_signature"
  | "invalid_algorithm"
  | "invalid_token";

export class MissingTokenError extends Error {
  readonly reason: AuthFailureReason = "missing_token";
}

export class InvalidTokenError extends Error {
  readonly reason: AuthFailureReason;

  constructor(message: string, reason: AuthFailureReason = "invalid_token") {
    super(message);
    this.reason = reason;
  }
}

/** Narrow a thrown auth error to its metric label; anything else is unknown. */
export function authFailureReason(err: unknown): AuthFailureReason {
  if (err instanceof MissingTokenError || err instanceof InvalidTokenError) return err.reason;
  return "invalid_token";
}

/**
 * Map a `jsonwebtoken` failure onto the closed reason set above.
 *
 * Matches on the error's `name` first (a stable public part of the library's
 * API) and only falls back to message text for the cases `JsonWebTokenError`
 * does not subclass — `verify` reports "invalid signature", "jwt malformed"
 * and "invalid algorithm" all as the same class, and those three are exactly
 * the ones worth telling apart.
 */
function classifyJwtError(err: unknown): AuthFailureReason {
  if (!(err instanceof Error)) return "invalid_token";
  if (err.name === "TokenExpiredError") return "expired_token";
  if (err.name === "NotBeforeError") return "not_yet_valid_token";

  const message = err.message.toLowerCase();
  // "jwt signature is required" is what `verify` reports for an `alg: none`
  // token with an empty signature segment — the textbook forgery. It belongs
  // with invalid_signature, not in the generic bucket: in both cases the
  // signature did not validate, and both are things no honest client sends.
  // (A `none` token that carries junk in the signature segment reports
  // "invalid algorithm" instead, hence both branches.)
  if (message.includes("invalid signature") || message.includes("signature is required")) {
    return "invalid_signature";
  }
  if (message.includes("invalid algorithm")) return "invalid_algorithm";
  if (message.includes("malformed") || message.includes("jwt must be provided")) {
    return "malformed_token";
  }
  return "invalid_token";
}

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
      throw new InvalidTokenError("unexpected token payload shape", "malformed_token");
    }
    return decoded as unknown as AuthClaims;
  } catch (err) {
    if (err instanceof MissingTokenError || err instanceof InvalidTokenError) throw err;
    const message = err instanceof Error ? err.message : "invalid token";
    throw new InvalidTokenError(message, classifyJwtError(err));
  }
}
