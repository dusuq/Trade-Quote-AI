"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { getSignatureAuditTrail, getSignatureRequest } from "@/lib/esign";

interface SignatureAuditDialogProps {
  open: boolean;
  onClose: () => void;
  token: string;
  requestId: string;
}

export function SignatureAuditDialog({
  open,
  onClose,
  token,
  requestId,
}: SignatureAuditDialogProps) {
  const { data: detail } = useQuery({
    queryKey: ["signature-requests", requestId],
    queryFn: () => getSignatureRequest(token, requestId),
    enabled: open,
  });

  const {
    data: trail,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["signature-requests", requestId, "audit"],
    queryFn: () => getSignatureAuditTrail(token, requestId),
    enabled: open,
  });

  return (
    <Dialog open={open} onClose={onClose} title="Signature Audit Trail" className="max-w-2xl">
      {isLoading && <p className="text-sm text-muted-foreground">Loading audit trail…</p>}
      {isError && <p className="text-sm text-destructive">Couldn&apos;t load the audit trail.</p>}

      {trail && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {trail.verification.is_valid ? (
              <Badge variant="success">🛡️ Chain Verified (Valid)</Badge>
            ) : (
              <Badge variant="destructive">⚠️ Tamper Detected (Invalid)</Badge>
            )}
            <span className="text-sm text-muted-foreground">
              {trail.verification.entry_count}{" "}
              {trail.verification.entry_count === 1 ? "entry" : "entries"}
            </span>
          </div>
          {!trail.verification.is_valid && (
            <p className="text-sm text-destructive">
              Broken at sequence {trail.verification.broken_at_sequence}
              {trail.verification.reason ? `: ${trail.verification.reason}` : ""}
            </p>
          )}

          {detail?.signature && (
            <div className="space-y-1 rounded-md border p-2 text-sm">
              <p className="font-medium">
                {detail.signature.signer_name} ({detail.signature.method})
              </p>
              <p className="text-muted-foreground">IP: {detail.signature.ip_address}</p>
              <p className="text-muted-foreground">
                Signed: {new Date(detail.signature.signed_at).toLocaleString()}
              </p>
              <p className="text-muted-foreground">
                Consent: {detail.signature.consented_to_electronic_business ? "Yes" : "No"} ·
                Intent: {detail.signature.intent_affirmed ? "Yes" : "No"}
              </p>
            </div>
          )}

          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Timeline</h3>
            <ul className="space-y-2">
              {trail.entries.map((entry) => (
                <li key={entry.sequence} className="rounded-md border p-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">
                      #{entry.sequence} {entry.event_type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(entry.occurred_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="break-all text-xs text-muted-foreground">
                    hash: {entry.entry_hash.slice(0, 16)}… (prev: {entry.prev_hash.slice(0, 16)}…)
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Dialog>
  );
}
