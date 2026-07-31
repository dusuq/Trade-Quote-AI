"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import { fetchProposalPdfBlob } from "@/lib/proposals";
import { computeSha256, createSignatureRequest, type SignatureRequestDetail } from "@/lib/esign";

interface RequestSignatureDialogProps {
  open: boolean;
  onClose: () => void;
  token: string;
  proposalId: string;
  onCreated: (request: SignatureRequestDetail) => void;
}

/** Fetches the proposal's current PDF, hashes it client-side, and creates the
 * signature request bound to that exact hash — the same document the signer
 * will later be asked to sign against (services/esign-service's
 * DocumentMismatchError enforces this server-side too). */
export function RequestSignatureDialog({
  open,
  onClose,
  token,
  proposalId,
  onCreated,
}: RequestSignatureDialogProps) {
  const [signerName, setSignerName] = React.useState("");
  const [signerEmail, setSignerEmail] = React.useState("");
  const [expiresInDays, setExpiresInDays] = React.useState(30);
  const [error, setError] = React.useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const pdfBlob = await fetchProposalPdfBlob(token, proposalId);
      const buffer = await pdfBlob.arrayBuffer();
      const documentSha256 = await computeSha256(buffer);
      return createSignatureRequest(token, {
        proposal_id: proposalId,
        signer_name: signerName,
        signer_email: signerEmail,
        document_sha256: documentSha256,
        expires_in_days: expiresInDays,
      });
    },
    onSuccess: (request) => {
      onCreated(request);
      handleClose();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Couldn't create the signature request.");
    },
  });

  function handleClose() {
    setSignerName("");
    setSignerEmail("");
    setExpiresInDays(30);
    setError(null);
    onClose();
  }

  const canSubmit = signerName.trim().length > 0 && signerEmail.trim().length > 0;

  return (
    <Dialog open={open} onClose={handleClose} title="Request E-Signature">
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="signerName">Signer name</Label>
          <Input
            id="signerName"
            value={signerName}
            onChange={(event) => setSignerName(event.target.value)}
            placeholder="Jane Doe"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="signerEmail">Signer email</Label>
          <Input
            id="signerEmail"
            type="email"
            value={signerEmail}
            onChange={(event) => setSignerEmail(event.target.value)}
            placeholder="jane@example.com"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="expiresInDays">Expires in (days)</Label>
          <Input
            id="expiresInDays"
            type="number"
            min={1}
            max={365}
            value={expiresInDays}
            onChange={(event) => setExpiresInDays(Number(event.target.value))}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending ? "Sending…" : "Send Signature Request"}
          </Button>
          <Button type="button" variant="outline" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
