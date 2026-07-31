"use client";

import * as React from "react";
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
import {
  getSignatureRequest,
  listSignatureRequests,
  statusBadgeVariantForEsign,
  voidSignatureRequest,
} from "@/lib/esign";
import { RequestSignatureDialog } from "@/components/esign/request-signature-dialog";
import { SignatureAuditDialog } from "@/components/esign/signature-audit-dialog";

export default function ProposalDetailPage() {
  const token = useAuthGuard();
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [requestDialogOpen, setRequestDialogOpen] = React.useState(false);
  const [auditRequestId, setAuditRequestId] = React.useState<string | null>(null);
  const [copiedRequestId, setCopiedRequestId] = React.useState<string | null>(null);
  const [signatureActionError, setSignatureActionError] = React.useState<string | null>(null);

  const {
    data: proposal,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["proposals", params.id],
    queryFn: () => getProposal(token as string, params.id),
    enabled: !!token,
  });

  const {
    data: signatureRequests,
    isLoading: signatureRequestsLoading,
    isError: signatureRequestsError,
  } = useQuery({
    queryKey: ["signature-requests", { proposal_id: params.id }],
    queryFn: () => listSignatureRequests(token as string, { proposal_id: params.id }),
    enabled: !!token,
  });

  function invalidateSignatureRequests() {
    queryClient.invalidateQueries({ queryKey: ["signature-requests", { proposal_id: params.id }] });
  }

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
      window.open(url, "_blank", "noopener,noreferrer");
    },
  });

  const voidMutation = useMutation({
    mutationFn: (requestId: string) => voidSignatureRequest(token as string, requestId),
    onSuccess: () => {
      invalidateSignatureRequests();
      setSignatureActionError(null);
    },
    onError: (err) => {
      setSignatureActionError(err instanceof ApiError ? err.message : "Something went wrong.");
    },
  });

  const copyLinkMutation = useMutation({
    mutationFn: async (requestId: string) => {
      const detail = await getSignatureRequest(token as string, requestId);
      const url = `${window.location.origin}/sign/${detail.token}`;
      await navigator.clipboard.writeText(url);
      return requestId;
    },
    onSuccess: (requestId) => {
      setCopiedRequestId(requestId);
      setTimeout(
        () => setCopiedRequestId((current) => (current === requestId ? null : current)),
        2000,
      );
      setSignatureActionError(null);
    },
    onError: (err) => {
      setSignatureActionError(err instanceof ApiError ? err.message : "Something went wrong.");
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
        <div className="flex gap-2">
          {proposal.status !== "draft" && (
            <Button variant="outline" onClick={() => setRequestDialogOpen(true)}>
              Request E-Signature
            </Button>
          )}
          {proposal.status === "draft" && (
            <Button onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              {sendMutation.isPending ? "Sending…" : "Send"}
            </Button>
          )}
        </div>
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
            <code className="block break-all rounded bg-muted px-2 py-1 text-xs">{publicViewUrl}</code>
          </div>
          {proposal.sent_at && (
            <p className="text-muted-foreground">
              Sent {new Date(proposal.sent_at).toLocaleString()}
            </p>
          )}
          {proposal.viewed_at && (
            <p className="text-muted-foreground">
              Viewed {new Date(proposal.viewed_at).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Signature Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {signatureRequestsLoading && (
            <p className="text-sm text-muted-foreground">Loading signature requests…</p>
          )}
          {signatureRequestsError && (
            <p className="text-sm text-destructive">Couldn&apos;t load signature requests.</p>
          )}
          {signatureRequests && signatureRequests.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No signature requests yet. Click &quot;Request E-Signature&quot; to send one.
            </p>
          )}
          {signatureRequests && signatureRequests.length > 0 && (
            <ul className="space-y-2">
              {signatureRequests.map((request) => (
                <li key={request.id} className="rounded-md border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{request.signer_name}</p>
                      <p className="text-muted-foreground">{request.signer_email}</p>
                    </div>
                    <Badge variant={statusBadgeVariantForEsign(request.status)} className="capitalize">
                      {request.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-muted-foreground">
                    Expires {new Date(request.expires_at).toLocaleDateString()}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => copyLinkMutation.mutate(request.id)}
                      disabled={copyLinkMutation.isPending}
                    >
                      {copiedRequestId === request.id ? "Copied!" : "Copy Link"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setAuditRequestId(request.id)}
                    >
                      View Audit
                    </Button>
                    {request.status === "pending" && (
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        onClick={() => {
                          if (window.confirm("Void this signature request? This cannot be undone.")) {
                            voidMutation.mutate(request.id);
                          }
                        }}
                        disabled={voidMutation.isPending}
                      >
                        Void
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {signatureActionError && (
            <p className="mt-2 text-sm text-destructive">{signatureActionError}</p>
          )}
        </CardContent>
      </Card>

      <RequestSignatureDialog
        open={requestDialogOpen}
        onClose={() => setRequestDialogOpen(false)}
        token={token as string}
        proposalId={proposal.id}
        onCreated={invalidateSignatureRequests}
      />
      {auditRequestId && (
        <SignatureAuditDialog
          open={!!auditRequestId}
          onClose={() => setAuditRequestId(null)}
          token={token as string}
          requestId={auditRequestId}
        />
      )}
    </div>
  );
}
