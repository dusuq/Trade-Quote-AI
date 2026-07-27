"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import {
  fetchProposalPdfBlob,
  getProposal,
  sendProposal,
  statusBadgeVariantForProposal,
} from "@/lib/proposals";
import { ApiError } from "@/lib/api-client";
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

  const previewMutation = useMutation({
    mutationFn: async () => {
      const blob = await fetchProposalPdfBlob(token as string, params.id);
      const url = URL.createObjectURL(blob);
      // Opened in a new tab rather than the current one so the object URL's
      // lifetime is independent of this page's — the browser tears it down
      // when that tab is closed, and we don't need to track it here.
      window.open(url, "_blank", "noopener,noreferrer");
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

  const publicViewUrl = `${config.apiUrl}/v1/proposals/${proposal.id}/view`;

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
        <CardContent className="space-y-3 text-sm">
          <p>Version {proposal.current_version}</p>
          <div className="space-y-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => previewMutation.mutate()}
              disabled={previewMutation.isPending}
            >
              {previewMutation.isPending ? "Opening…" : "Preview / download PDF"}
            </Button>
            {previewMutation.isError && (
              <p className="text-sm text-destructive">
                {previewMutation.error instanceof ApiError
                  ? previewMutation.error.message
                  : "Couldn't load the PDF."}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <p className="text-muted-foreground">Link to send the customer:</p>
            {/* Deliberately not a clickable link: the contractor clicking their
                own copy of this link would flip the proposal to VIEWED and
                stamp viewed_at, destroying the one signal this feature exists
                to capture — did the *customer* open it. */}
            <code className="block break-all rounded bg-muted px-2 py-1 text-xs">{publicViewUrl}</code>
          </div>
          {proposal.sent_at && <p className="text-muted-foreground">Sent {new Date(proposal.sent_at).toLocaleString()}</p>}
          {proposal.viewed_at && <p className="text-muted-foreground">Viewed {new Date(proposal.viewed_at).toLocaleString()}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
