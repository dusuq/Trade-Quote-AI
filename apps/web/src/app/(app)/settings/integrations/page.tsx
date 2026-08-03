"use client";

import { Suspense } from "react";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { IntegrationsManager } from "@/components/settings/integrations-manager";

export default function IntegrationsSettingsPage() {
  const token = useAuthGuard();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Integrations</h1>
        <p className="text-muted-foreground">
          Connect QuickBooks, Xero, or Zapier to sync quotes and invoices, and review sync history.
        </p>
      </div>

      {/* useSearchParams requires a Suspense boundary in the app router —
          this page is also the OAuth callback's redirect target, so the
          query string (?provider=&connected=) is read on first render. */}
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
        {token && <IntegrationsManager token={token} />}
      </Suspense>
    </div>
  );
}
