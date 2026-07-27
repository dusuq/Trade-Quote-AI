"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { listProposals, statusBadgeVariantForProposal } from "@/lib/proposals";

export default function ProposalsPage() {
  const token = useAuthGuard();

  const {
    data: proposals,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["proposals"],
    queryFn: () => listProposals(token as string),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Proposals</h1>
        <p className="text-muted-foreground">Every branded proposal you&apos;ve sent, at every stage.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Proposals</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading proposals…</p>}
          {isError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load proposals. Is the API Gateway running?
            </p>
          )}
          {proposals && proposals.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No proposals yet. Create one from a quote to get started.
            </p>
          )}
          {proposals && proposals.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Number</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 font-medium">Sent</th>
                    <th className="py-2 pr-4 font-medium">Viewed</th>
                  </tr>
                </thead>
                <tbody>
                  {proposals.map((proposal) => (
                    <tr key={proposal.id} className="border-b last:border-0 hover:bg-accent/50">
                      <td className="py-3 pr-4">
                        <Link href={`/proposals/${proposal.id}`} className="font-medium hover:underline">
                          {proposal.number}
                        </Link>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={statusBadgeVariantForProposal(proposal.status)} className="capitalize">
                          {proposal.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4">{proposal.sent_at ? new Date(proposal.sent_at).toLocaleDateString() : "—"}</td>
                      <td className="py-3 pr-4">{proposal.viewed_at ? new Date(proposal.viewed_at).toLocaleDateString() : "—"}</td>
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
