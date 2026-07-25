import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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

/**
 * Placeholder KPI shell — wires to services/analytics-service (M21/T307) once
 * it ships. Static values here establish the layout other agents build against.
 */
export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Your quoting activity at a glance.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Quotes Today" value="—" hint="Awaiting live data" />
        <KpiCard label="Pending" value="—" hint="Awaiting live data" />
        <KpiCard label="Accepted" value="—" hint="Awaiting live data" />
        <KpiCard label="Revenue (MTD)" value="—" hint="Awaiting live data" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Quotes</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No quotes yet. Once quote-service is wired up, recent activity appears here.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
