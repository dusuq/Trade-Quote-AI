"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { acceptQuote, getQuote, rejectQuote, sendQuote, statusBadgeVariant } from "@/lib/quotes";
import { formatMoney } from "@/lib/money";
import { ApiError } from "@/lib/api-client";

export default function QuoteDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = React.useState<string | null>(null);

  const {
    data: quote,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["quotes", params.id],
    queryFn: () => getQuote(token as string, params.id),
    enabled: !!token,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["quotes", params.id] });
    queryClient.invalidateQueries({ queryKey: ["quotes"] });
  }

  const sendMutation = useMutation({
    mutationFn: () => sendQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to send."),
  });
  const acceptMutation = useMutation({
    mutationFn: () => acceptQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to accept."),
  });
  const rejectMutation = useMutation({
    mutationFn: () => rejectQuote(token as string, params.id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof ApiError ? err.message : "Unable to reject."),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading quote…</p>;
  if (isError || !quote) return <p className="text-sm text-destructive">Quote not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{quote.number}</h1>
            <Badge variant={statusBadgeVariant(quote.status)} className="capitalize">
              {quote.status}
            </Badge>
          </div>
          <p className="text-muted-foreground">{quote.title ?? "Untitled quote"}</p>
        </div>
        <div className="flex gap-2">
          {(quote.status === "draft" ||
            quote.status === "sent" ||
            quote.status === "viewed" ||
            quote.status === "accepted") && (
            <Link
              href={`/proposals/new?quote_id=${quote.id}`}
              className={buttonVariants({ variant: "outline" })}
            >
              Create Proposal
            </Link>
          )}
          {quote.status === "draft" && (
            <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              {sendMutation.isPending ? "Sending…" : "Send"}
            </Button>
          )}
          {(quote.status === "sent" || quote.status === "viewed") && (
            <>
              <Button
                variant="outline"
                onClick={() => rejectMutation.mutate()}
                disabled={rejectMutation.isPending}
              >
                Mark Rejected
              </Button>
              <Button onClick={() => acceptMutation.mutate()} disabled={acceptMutation.isPending}>
                Mark Accepted
              </Button>
            </>
          )}
        </div>
      </div>

      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Line Items</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Description</th>
                  <th className="py-2 pr-4 text-right font-medium">Qty</th>
                  <th className="py-2 pr-4 font-medium">Unit</th>
                  <th className="py-2 pr-4 text-right font-medium">Unit Price</th>
                  <th className="py-2 pr-4 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {quote.line_items.map((item) => (
                  <tr key={item.id} className="border-b last:border-0">
                    <td className="py-3 pr-4">{item.description}</td>
                    <td className="py-3 pr-4 text-right">{item.quantity}</td>
                    <td className="py-3 pr-4">{item.unit}</td>
                    <td className="py-3 pr-4 text-right">
                      {formatMoney(item.unit_price_minor, quote.currency)}
                    </td>
                    <td className="py-3 pr-4 text-right font-medium">
                      {formatMoney(item.line_total_minor, quote.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex justify-end">
            <div className="w-56 space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>{formatMoney(quote.subtotal_minor, quote.currency)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tax</span>
                <span>{formatMoney(quote.tax_minor, quote.currency)}</span>
              </div>
              <div className="flex justify-between border-t pt-1 text-base font-semibold">
                <span>Total</span>
                <span>{formatMoney(quote.total_minor, quote.currency)}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
