"use client";

import { AppShell } from "@/components/app-shell/shell";
import { useAuthGuard } from "@/lib/use-auth-guard";

export default function AppGroupLayout({ children }: { children: React.ReactNode }) {
  const token = useAuthGuard(); // redirects to /login when no token is present

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
