"use client";

import Link from "next/link";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { TemplateManager } from "@/components/settings/template-manager";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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

      <Card>
        <CardHeader>
          <CardTitle>Integrations</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">
            Connect QuickBooks, Xero, or Zapier to sync quotes and invoices.
          </p>
          <Link href="/settings/integrations" className={cn(buttonVariants({ size: "sm" }))}>
            Manage integrations
          </Link>
        </CardContent>
      </Card>

      {token && <TemplateManager token={token} />}
    </div>
  );
}
