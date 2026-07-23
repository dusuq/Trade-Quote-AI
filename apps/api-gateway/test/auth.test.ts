import { describe, expect, it } from "vitest";
import jwt from "jsonwebtoken";
import { verifyBearerToken, MissingTokenError, InvalidTokenError } from "../src/auth.js";

const SECRET = "test-secret-at-least-32-bytes-long!!";

function sign(payload: object, opts: jwt.SignOptions = {}): string {
  return jwt.sign(payload, SECRET, { algorithm: "HS256", ...opts });
}

describe("verifyBearerToken", () => {
  it("accepts a valid bearer token and returns claims", () => {
    const token = sign({ sub: "user-1", tid: "tenant-1", roles: ["owner"], typ: "access" });
    const claims = verifyBearerToken(`Bearer ${token}`, SECRET);
    expect(claims.sub).toBe("user-1");
    expect(claims.tid).toBe("tenant-1");
    expect(claims.roles).toEqual(["owner"]);
  });

  it("is case-insensitive on the 'Bearer' scheme", () => {
    const token = sign({ sub: "u", tid: "t", roles: [] });
    expect(() => verifyBearerToken(`bearer ${token}`, SECRET)).not.toThrow();
  });

  it("rejects a missing header", () => {
    expect(() => verifyBearerToken(undefined, SECRET)).toThrow(MissingTokenError);
  });

  it("rejects a header without the Bearer scheme", () => {
    const token = sign({ sub: "u", tid: "t", roles: [] });
    expect(() => verifyBearerToken(token, SECRET)).toThrow(MissingTokenError);
  });

  it("rejects an empty bearer token", () => {
    expect(() => verifyBearerToken("Bearer ", SECRET)).toThrow(MissingTokenError);
  });

  it("rejects a token signed with the wrong secret", () => {
    const token = sign({ sub: "u", tid: "t", roles: [] });
    expect(() => verifyBearerToken(`Bearer ${token}`, "a-completely-different-secret")).toThrow(
      InvalidTokenError,
    );
  });

  it("rejects an expired token", () => {
    const token = sign({ sub: "u", tid: "t", roles: [] }, { expiresIn: -10 });
    expect(() => verifyBearerToken(`Bearer ${token}`, SECRET)).toThrow(InvalidTokenError);
  });

  it("rejects a malformed token string", () => {
    expect(() => verifyBearerToken("Bearer not-a-real-jwt", SECRET)).toThrow(InvalidTokenError);
  });
});
