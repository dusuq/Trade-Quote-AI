"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { listQuotes, statusBadgeVariant } from "@/lib/quotes";
import { formatMoney } from "@/lib/money";

export default function QuotesPage() {
  const token = useAuthGuard();

  const {
    data: quotes,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["quotes"],
    queryFn: () => listQuotes(token as string),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Quotes</h1>
          <p className="text-muted-foreground">Every estimate you&apos;ve built, at every stage.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/quotes/new" className={buttonVariants({ variant: "outline" })}>
            Build Manually
          </Link>
          <Link href="/quotes/new-ai" className={buttonVariants({ variant: "default" })}>
            Describe the Job
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Quotes</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading quotes…</p>}
          {isError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load quotes. Is the API Gateway running?
            </p>
          )}
          {quotes && quotes.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No quotes yet. Create your first one to get started.
            </p>
          )}
          {quotes && quotes.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Number</th>
                    <th className="py-2 pr-4 font-medium">Title</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 text-right font-medium">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {quotes.map((quote) => (
                    <tr key={quote.id} className="border-b last:border-0 hover:bg-accent/50">
                      <td className="py-3 pr-4">
                        <Link href={`/quotes/${quote.id}`} className="font-medium hover:underline">
                          {quote.number}
                        </Link>
                      </td>
                      <td className="py-3 pr-4">{quote.title ?? "—"}</td>
                      <td className="py-3 pr-4">
                        <Badge variant={statusBadgeVariant(quote.status)} className="capitalize">
                          {quote.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-right font-medium">
                        {formatMoney(quote.total_minor, quote.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
