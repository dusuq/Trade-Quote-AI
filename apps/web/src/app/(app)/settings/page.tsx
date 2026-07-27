"use client";

import { useAuthGuard } from "@/lib/use-auth-guard";
import { TemplateManager } from "@/components/settings/template-manager";

export default function SettingsPage() {
  const token = useAuthGuard();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Branding and proposal templates that feed the PDF engine when you create a proposal.
        </p>
      </div>

      {token && <TemplateManager token={token} />}
    </div>
  );
}
