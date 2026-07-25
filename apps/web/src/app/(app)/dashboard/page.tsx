"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuthGuard } from "@/lib/use-auth-guard";
import {
  fetchQuoteSummary,
  formatConversion,
  pickPrimaryTotal,
  resolveBrowserTimezone,
} from "@/lib/dashboard";
import { listQuotes, statusBadgeVariant } from "@/lib/quotes";
import { formatMoney } from "@/lib/money";

interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
}

function KpiCard({ label, value, hint }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const token = useAuthGuard();
  const timezone = resolveBrowserTimezone();

  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
  } = useQuery({
    queryKey: ["quotes-summary", timezone],
    queryFn: () => fetchQuoteSummary(token as string, timezone, "mtd"),
    enabled: !!token,
  });

  const {
    data: recentQuotes,
    isLoading: recentLoading,
    isError: recentError,
  } = useQuery({
    queryKey: ["quotes", "recent"],
    queryFn: () => listQuotes(token as string, 5),
    enabled: !!token,
  });

  const primaryTotal = summary ? pickPrimaryTotal(summary.totals) : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Your quoting activity at a glance.</p>
      </div>

      {summaryError && (
        <p className="text-sm text-destructive">
          Couldn&apos;t load your quoting activity. Is the API Gateway running?
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Quotes Today"
          value={summaryLoading ? "…" : String(summary?.quotes_today ?? "—")}
        />
        <KpiCard
          label="Pending"
          value={summaryLoading ? "…" : String(summary?.pending_count ?? "—")}
          hint="Sent or viewed, awaiting a decision"
        />
        <KpiCard
          label="Accepted"
          value={summaryLoading ? "…" : String(summary?.accepted_count ?? "—")}
          hint="This month"
        />
        <KpiCard
          label="Accepted Value (MTD)"
          value={
            summaryLoading
              ? "…"
              : !summary
                ? "—"
                : primaryTotal
                  ? formatMoney(primaryTotal.accepted_value_minor, primaryTotal.currency)
                  : formatMoney(0)
          }
          hint={
            summary
              ? `Conversion: ${formatConversion(summary.conversion_bps, summary.decided_count)}`
              : undefined
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Quotes</CardTitle>
        </CardHeader>
        <CardContent>
          {recentLoading && <p className="text-sm text-muted-foreground">Loading recent quotes…</p>}
          {recentError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load recent quotes. Is the API Gateway running?
            </p>
          )}
          {recentQuotes && recentQuotes.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No quotes yet. Once you create one, recent activity appears here.
            </p>
          )}
          {recentQuotes && recentQuotes.length > 0 && (
            <ul className="divide-y">
              {recentQuotes.map((quote) => (
                <li key={quote.id} className="flex items-center justify-between py-3">
                  <div>
                    <Link href={`/quotes/${quote.id}`} className="font-medium hover:underline">
                      {quote.number}
                    </Link>
                    <p className="text-sm text-muted-foreground">{quote.title ?? "—"}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={statusBadgeVariant(quote.status)} className="capitalize">
                      {quote.status}
                    </Badge>
                    <span className="font-medium">
                      {formatMoney(quote.total_minor, quote.currency)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
