"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { getQuote } from "@/lib/quotes";
import { getCustomer } from "@/lib/customers";
import { listTemplates } from "@/lib/proposal-templates";
import { CreateProposalForm } from "@/components/proposals/create-proposal-form";

export default function NewProposalPage() {
  const token = useAuthGuard();
  const searchParams = useSearchParams();
  const quoteId = searchParams.get("quote_id") ?? "";

  const quoteQuery = useQuery({
    queryKey: ["quotes", quoteId],
    queryFn: () => getQuote(token as string, quoteId),
    enabled: !!token && !!quoteId,
  });

  const templatesQuery = useQuery({
    queryKey: ["proposal-templates"],
    queryFn: () => listTemplates(token as string),
    enabled: !!token,
  });

  const customerId = quoteQuery.data?.customer_id;
  const customerQuery = useQuery({
    queryKey: ["customers", customerId],
    queryFn: () => getCustomer(token as string, customerId as string),
    enabled: !!token && !!customerId,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Create Proposal</h1>
        <p className="text-muted-foreground">Turn this quote into a branded, sendable proposal.</p>
      </div>

      {renderBody()}
    </div>
  );

  function renderBody() {
    if (!quoteId) {
      return (
        <p className="text-sm text-destructive">
          Missing quote — start this flow from a quote&apos;s detail page.
        </p>
      );
    }

    if (quoteQuery.isError) {
      return (
        <p className="text-sm text-destructive">
          Couldn&apos;t load this quote. Is the API Gateway running?
        </p>
      );
    }

    if (templatesQuery.isError) {
      return (
        <p className="text-sm text-destructive">
          Couldn&apos;t load proposal templates. Is the API Gateway running?
        </p>
      );
    }

    if (customerQuery.isError) {
      return (
        <p className="text-sm text-destructive">
          Couldn&apos;t load the customer for this quote. Is the API Gateway running?
        </p>
      );
    }

    const isLoading =
      quoteQuery.isLoading ||
      templatesQuery.isLoading ||
      (!!customerId && customerQuery.isLoading) ||
      (!quoteQuery.data && !!token);

    if (isLoading) {
      return (
        <Card>
          <CardHeader>
            <CardTitle>Template</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Label htmlFor="templateId-loading">Proposal template</Label>
            <Select id="templateId-loading" disabled defaultValue="">
              <option value="">Loading templates…</option>
            </Select>
          </CardContent>
        </Card>
      );
    }

    if (!templatesQuery.data || templatesQuery.data.length === 0) {
      return (
        <Card>
          <CardContent className="space-y-3 pt-6 text-sm">
            <p>You need a proposal template before you can send a proposal.</p>
            <Link href="/settings" className={buttonVariants({ variant: "default", size: "sm" })}>
              Go to Settings
            </Link>
          </CardContent>
        </Card>
      );
    }

    if (!quoteQuery.data || !customerQuery.data) {
      return (
        <p className="text-sm text-destructive">
          Couldn&apos;t load this quote. Is the API Gateway running?
        </p>
      );
    }

    return (
      <CreateProposalForm
        token={token as string}
        quote={quoteQuery.data}
        customer={customerQuery.data}
        templates={templatesQuery.data}
      />
    );
  }
}
