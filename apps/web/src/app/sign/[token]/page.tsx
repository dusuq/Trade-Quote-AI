"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SignaturePad } from "@/components/esign/signature-pad";
import { fetchPublicProposalPdfBlob } from "@/lib/proposals";
import {
  applyPublicSignature,
  computeSha256,
  declinePublicSignature,
  describeEsignSubmitError,
  getPublicSigningContext,
  type SignatureMethod,
  type SignatureResponse,
} from "@/lib/esign";

export default function PublicSignPage() {
  const params = useParams<{ token: string }>();
  const signingToken = params.token;

  const [method, setMethod] = React.useState<SignatureMethod>("typed");
  const [typedName, setTypedName] = React.useState("");
  const [drawnImageData, setDrawnImageData] = React.useState<string | null>(null);
  const [consented, setConsented] = React.useState(false);
  const [intentAffirmed, setIntentAffirmed] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [signature, setSignature] = React.useState<SignatureResponse | null>(null);
  const [declined, setDeclined] = React.useState(false);
  const [pdfUrl, setPdfUrl] = React.useState<string | null>(null);
  const [documentVerified, setDocumentVerified] = React.useState<boolean | null>(null);
  const [computedDocumentSha256, setComputedDocumentSha256] = React.useState<string | null>(null);

  const {
    data: context,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["sign", signingToken],
    queryFn: () => getPublicSigningContext(signingToken),
    enabled: !!signingToken,
    retry: false,
  });

  React.useEffect(() => {
    if (!context) return;
    let objectUrl: string | null = null;
    fetchPublicProposalPdfBlob(context.proposal_id)
      .then(async (blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
        const hash = await computeSha256(await blob.arrayBuffer());
        setComputedDocumentSha256(hash);
        setDocumentVerified(hash === context.document_sha256);
      })
      .catch(() => {
        setComputedDocumentSha256(null);
        setDocumentVerified(false);
      });
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [context]);

  const signMutation = useMutation({
    mutationFn: () => {
      if (!context) throw new Error("Signing context not loaded");
      if (!computedDocumentSha256) throw new Error("Document not yet loaded");
      return applyPublicSignature(signingToken, {
        method,
        typed_name: method === "typed" ? typedName.trim() : null,
        image_data: method === "drawn" ? drawnImageData : null,
        document_sha256: computedDocumentSha256,
        consented_to_electronic_business: consented,
        intent_affirmed: intentAffirmed,
      });
    },
    onSuccess: (result) => {
      setSignature(result);
      setError(null);
    },
    onError: (err) => setError(describeEsignSubmitError(err)),
  });

  const declineMutation = useMutation({
    mutationFn: () => declinePublicSignature(signingToken),
    onSuccess: () => {
      setDeclined(true);
      setError(null);
    },
    onError: (err) => setError(describeEsignSubmitError(err)),
  });

  const canSign =
    consented &&
    intentAffirmed &&
    computedDocumentSha256 !== null &&
    (method === "typed" ? typedName.trim().length > 0 : !!drawnImageData);

  if (isLoading) {
    return <p className="p-6 text-sm text-muted-foreground">Loading document…</p>;
  }

  if (isError || !context) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Card>
          <CardContent className="pt-6 text-sm text-destructive">
            This signing link is no longer valid.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (signature) {
    return (
      <div className="mx-auto max-w-lg space-y-4 p-6">
        <Card>
          <CardHeader>
            <CardTitle>Signed successfully</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Thank you, {signature.signer_name} — your signature has been recorded.</p>
            <p className="text-muted-foreground">Transaction ID: {signature.id}</p>
            <p className="break-all text-muted-foreground">
              Signature hash: {signature.signature_hash}
            </p>
            <p className="text-muted-foreground">
              Signed at: {new Date(signature.signed_at).toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (declined) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Card>
          <CardContent className="pt-6 text-sm">
            You&apos;ve declined to sign this document.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Review &amp; Sign</h1>
        <p className="text-muted-foreground">
          Hello, {context.signer_name} — please review the document below.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Document</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline"
            >
              View / download PDF
            </a>
          )}
          {documentVerified !== null && (
            <p className={documentVerified ? "text-emerald-700" : "text-destructive"}>
              {documentVerified
                ? "✅ Document integrity verified."
                : "⚠️ Couldn't verify document integrity."}
            </p>
          )}
        </CardContent>
      </Card>

      {!context.can_sign ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            This document is no longer available for signing (status: {context.status}).
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Your Signature</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant={method === "typed" ? "default" : "outline"}
                onClick={() => {
                  setMethod("typed");
                  setDrawnImageData(null);
                }}
              >
                Type
              </Button>
              <Button
                type="button"
                size="sm"
                variant={method === "drawn" ? "default" : "outline"}
                onClick={() => {
                  setMethod("drawn");
                  setTypedName("");
                }}
              >
                Draw
              </Button>
            </div>

            {method === "typed" ? (
              <div className="space-y-2">
                <Label htmlFor="typedName">Type your full name</Label>
                <Input
                  id="typedName"
                  value={typedName}
                  onChange={(event) => setTypedName(event.target.value)}
                  placeholder="Jane Doe"
                />
                {typedName && (
                  <p className="text-3xl" style={{ fontFamily: "'Brush Script MT', cursive" }}>
                    {typedName}
                  </p>
                )}
              </div>
            ) : (
              <SignaturePad onChange={setDrawnImageData} />
            )}

            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={consented}
                  onChange={(event) => setConsented(event.target.checked)}
                />
                I consent to conduct business electronically.
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={intentAffirmed}
                  onChange={(event) => setIntentAffirmed(event.target.checked)}
                />
                I affirm my intent to adopt this signature as my legally binding signature.
              </label>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex gap-2">
              <Button
                type="button"
                onClick={() => signMutation.mutate()}
                disabled={!canSign || signMutation.isPending || declineMutation.isPending}
              >
                {signMutation.isPending ? "Signing…" : "Sign Proposal"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (window.confirm("Decline to sign this document? This cannot be undone.")) {
                    declineMutation.mutate();
                  }
                }}
                disabled={declineMutation.isPending || signMutation.isPending}
              >
                {declineMutation.isPending ? "Declining…" : "Decline to Sign"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
