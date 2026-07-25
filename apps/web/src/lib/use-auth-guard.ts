"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { authStore } from "@/lib/auth-store";

/**
 * Redirects to /login when no access token is present; otherwise returns it.
 * Every page under (app) that calls a backend service needs this — the
 * gateway requires a bearer token on every route except /v1/auth/*.
 */
export function useAuthGuard(): string | null {
  const router = useRouter();
  const [token, setToken] = React.useState<string | null>(null);

  React.useEffect(() => {
    const existing = authStore.getAccessToken();
    if (!existing) {
      router.replace("/login");
      return;
    }
    setToken(existing);
  }, [router]);

  return token;
}
