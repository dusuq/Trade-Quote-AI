"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, TrendingUp, Users, DollarSign } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { formatMoney } from "@/lib/money";
import { fetchAnalyticsOverview, fetchCustomerLTV, fetchTradeBreakdowns } from "@/lib/analytics";

interface MetricCardProps {
  title: string;
  value: React.ReactNode;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
}

function MetricCard({ title, value, hint, icon: Icon }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const token = useAuthGuard();

  const {
    data: overview,
    isLoading: overviewLoading,
    isError: overviewError,
  } = useQuery({
    queryKey: ["analytics", "overview"],
    queryFn: () => fetchAnalyticsOverview(token as string),
    enabled: !!token,
  });

  const {
    data: trades,
    isLoading: tradesLoading,
    isError: tradesError,
  } = useQuery({
    queryKey: ["analytics", "trades"],
    queryFn: () => fetchTradeBreakdowns(token as string),
    enabled: !!token,
  });

  const {
    data: ltvList,
    isLoading: ltvLoading,
    isError: ltvError,
  } = useQuery({
    queryKey: ["analytics", "customers"],
    queryFn: () => fetchCustomerLTV(token as string, 10),
    enabled: !!token,
  });

  const currency = overview?.currency || "USD";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">
          Performance metrics, trade breakdowns, and customer LTV leaderboards.
        </p>
      </div>

      {(overviewError || tradesError || ltvError) && (
        <p className="text-sm text-destructive">
          Couldn&apos;t load analytics data. Is the API Gateway and Analytics Service running?
        </p>
      )}

      {/* KPI Overview Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Total Pipeline Value"
          value={
            overviewLoading
              ? "…"
              : overview
                ? formatMoney(overview.total_pipeline_value_minor, currency)
                : "—"
          }
          hint={overview ? `${overview.total_quotes_count} quotes in pipeline` : undefined}
          icon={DollarSign}
        />
        <MetricCard
          title="Accepted Revenue"
          value={
            overviewLoading
              ? "…"
              : overview
                ? formatMoney(overview.total_accepted_value_minor, currency)
                : "—"
          }
          hint={overview ? `${overview.accepted_count} accepted quotes` : undefined}
          icon={TrendingUp}
        />
        <MetricCard
          title="Conversion Rate"
          value={
            overviewLoading
              ? "…"
              : overview
                ? `${(overview.conversion_rate_bps / 100).toFixed(1)}%`
                : "—"
          }
          hint={
            overview
              ? `Avg Ticket: ${formatMoney(overview.average_ticket_minor, currency)}`
              : undefined
          }
          icon={BarChart3}
        />
        <MetricCard
          title="Projected Monthly"
          value={
            overviewLoading
              ? "…"
              : overview
                ? formatMoney(overview.projected_monthly_revenue_minor, currency)
                : "—"
          }
          hint="Forecast based on historical conversion"
          icon={Users}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Trade Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Trade Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            {tradesLoading && <p className="text-sm text-muted-foreground">Loading trades…</p>}
            {trades && trades.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No trade activity recorded yet. Create quotes to see metrics by trade.
              </p>
            )}
            {trades && trades.length > 0 && (
              <div className="space-y-4">
                {trades.map((item) => (
                  <div
                    key={item.trade}
                    className="flex items-center justify-between border-b pb-3 last:border-0 last:pb-0"
                  >
                    <div>
                      <p className="font-medium capitalize">{item.trade}</p>
                      <p className="text-xs text-muted-foreground">
                        {item.quotes_count} quotes ({item.accepted_count} accepted)
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">
                        {formatMoney(item.total_revenue_minor, currency)}
                      </p>
                      <Badge variant="outline" className="text-xs">
                        {(item.conversion_rate_bps / 100).toFixed(1)}% conv
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Customer LTV Leaderboard */}
        <Card>
          <CardHeader>
            <CardTitle>Customer LTV Leaderboard</CardTitle>
          </CardHeader>
          <CardContent>
            {ltvLoading && <p className="text-sm text-muted-foreground">Loading customers…</p>}
            {ltvList && ltvList.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No customer lifetime data available yet.
              </p>
            )}
            {ltvList && ltvList.length > 0 && (
              <div className="space-y-4">
                {ltvList.map((cust) => (
                  <div
                    key={cust.customer_id}
                    className="flex items-center justify-between border-b pb-3 last:border-0 last:pb-0"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium">
                          {cust.customer_name?.trim()
                            ? cust.customer_name
                            : `Customer #${cust.customer_id.slice(0, 8)}`}
                        </p>
                        {cust.is_repeat_customer && (
                          <Badge variant="secondary" className="text-[10px] py-0 px-1">
                            Repeat
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {cust.total_quotes_count} total quotes · {cust.accepted_quotes_count}{" "}
                        accepted
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="font-semibold text-primary">
                        {formatMoney(cust.lifetime_value_minor, currency)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
