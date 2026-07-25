"use client";

const ACCESS_TOKEN_KEY = "tradequote.access_token";
const REFRESH_TOKEN_KEY = "tradequote.refresh_token";

/**
 * Minimal client-side token persistence. Deliberately not a full state
 * library — auth state here is just "do we have a token", which every
 * protected page/query checks via getAccessToken().
 */
export const authStore = {
  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};
