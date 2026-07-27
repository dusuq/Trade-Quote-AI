"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { getProposal, sendProposal, statusBadgeVariantForProposal } from "@/lib/proposals";
import { config } from "@/config";

export default function ProposalDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const {
    data: proposal,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["proposals", params.id],
    queryFn: () => getProposal(token as string, params.id),
    enabled: !!token,
  });

  const sendMutation = useMutation({
    mutationFn: () => sendProposal(token as string, params.id, "email"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", params.id] });
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading proposal…</p>;
  if (isError || !proposal) {
    return (
      <p className="text-sm text-destructive">
        Couldn&apos;t load this proposal. Is the API Gateway running?
      </p>
    );
  }

  const viewUrl = `${config.apiUrl}/v1/proposals/${proposal.id}/view`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{proposal.number}</h1>
          <Badge variant={statusBadgeVariantForProposal(proposal.status)} className="mt-1 capitalize">
            {proposal.status}
          </Badge>
        </div>
        {proposal.status === "draft" && (
          <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
            {sendMutation.isPending ? "Sending…" : "Send"}
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Document</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>Version {proposal.current_version}</p>
          <p>
            <a href={viewUrl} target="_blank" rel="noreferrer" className="text-primary hover:underline">
              View / download PDF
            </a>{" "}
            <span className="text-muted-foreground">— this is the same link the customer receives.</span>
          </p>
          {proposal.sent_at && <p className="text-muted-foreground">Sent {new Date(proposal.sent_at).toLocaleString()}</p>}
          {proposal.viewed_at && <p className="text-muted-foreground">Viewed {new Date(proposal.viewed_at).toLocaleString()}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
