import { apiFetch, ApiError } from "@/lib/api-client";

export type SignatureRequestStatus = "pending" | "signed" | "declined" | "voided" | "expired";
export type SignatureMethod = "typed" | "drawn";

export interface SignatureResponse {
  id: string;
  signer_name: string;
  signer_email: string;
  method: SignatureMethod;
  typed_name: string | null;
  signature_hash: string;
  document_sha256: string;
  ip_address: string;
  user_agent: string | null;
  consented_to_electronic_business: boolean;
  intent_affirmed: boolean;
  signed_at: string;
}

export interface SignatureRequestSummary {
  id: string;
  proposal_id: string;
  signer_id: string;
  signer_name: string;
  signer_email: string;
  document_sha256: string;
  status: SignatureRequestStatus;
  expires_at: string;
  created_at: string;
  signed_at: string | null;
  declined_at: string | null;
  voided_at: string | null;
}

/** Includes the signing `token` — the list endpoint (SignatureRequestSummary)
 * deliberately does not. Never assume a list row carries a usable token. */
export interface SignatureRequestDetail extends SignatureRequestSummary {
  token: string;
  signing_path: string;
  signature: SignatureResponse | null;
}

export interface PublicSigningContext {
  proposal_id: string;
  signer_name: string;
  document_sha256: string;
  status: SignatureRequestStatus;
  expires_at: string;
  can_sign: boolean;
}

export interface ChainVerificationResponse {
  is_valid: boolean;
  entry_count: number;
  broken_at_sequence: number | null;
  reason: string | null;
}

export interface AuditEntryResponse {
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  prev_hash: string;
  entry_hash: string;
}

export interface AuditTrailResponse {
  request_id: string;
  entries: AuditEntryResponse[];
  verification: ChainVerificationResponse;
}

export interface CreateSignatureRequestInput {
  proposal_id: string;
  signer_name: string;
  signer_email: string;
  document_sha256: string;
  expires_in_days?: number;
}

export function createSignatureRequest(
  token: string,
  input: CreateSignatureRequestInput,
): Promise<SignatureRequestDetail> {
  return apiFetch<SignatureRequestDetail>("/v1/signature-requests", {
    method: "POST",
    token,
    body: input,
  });
}

export interface ListSignatureRequestsFilter {
  proposal_id?: string;
  status?: SignatureRequestStatus;
}

export function listSignatureRequests(
  token: string,
  filter: ListSignatureRequestsFilter = {},
): Promise<SignatureRequestSummary[]> {
  const params = new URLSearchParams();
  if (filter.proposal_id) params.set("proposal_id", filter.proposal_id);
  if (filter.status) params.set("status", filter.status);
  const qs = params.toString();
  return apiFetch<SignatureRequestSummary[]>(
    `/v1/signature-requests${qs ? `?${qs}` : ""}`,
    { token },
  );
}

export function getSignatureRequest(
  token: string,
  requestId: string,
): Promise<SignatureRequestDetail> {
  return apiFetch<SignatureRequestDetail>(`/v1/signature-requests/${requestId}`, { token });
}

export function getSignatureAuditTrail(
  token: string,
  requestId: string,
): Promise<AuditTrailResponse> {
  return apiFetch<AuditTrailResponse>(`/v1/signature-requests/${requestId}/audit`, { token });
}

export function voidSignatureRequest(
  token: string,
  requestId: string,
  reason?: string,
): Promise<SignatureRequestSummary> {
  return apiFetch<SignatureRequestSummary>(`/v1/signature-requests/${requestId}/void`, {
    method: "POST",
    token,
    body: { reason: reason ?? null },
  });
}

export interface ApplySignatureInput {
  method: SignatureMethod;
  typed_name?: string | null;
  image_data?: string | null;
  document_sha256: string;
  consented_to_electronic_business: boolean;
  intent_affirmed: boolean;
}

// ── Public (unauthenticated) — no `token` param, no bearer header ──────────

export function getPublicSigningContext(signingToken: string): Promise<PublicSigningContext> {
  return apiFetch<PublicSigningContext>(`/v1/sign/${signingToken}`);
}

export function applyPublicSignature(
  signingToken: string,
  payload: ApplySignatureInput,
): Promise<SignatureResponse> {
  return apiFetch<SignatureResponse>(`/v1/sign/${signingToken}`, {
    method: "POST",
    body: payload,
  });
}

export function declinePublicSignature(
  signingToken: string,
  reason?: string,
): Promise<PublicSigningContext> {
  return apiFetch<PublicSigningContext>(`/v1/sign/${signingToken}/decline`, {
    method: "POST",
    body: { reason: reason ?? null },
  });
}

/** SHA-256 of an ArrayBuffer as lowercase hex — matches the backend's
 * `_SHA256_HEX` pattern and its case-normalizing validator exactly. */
export async function computeSha256(buffer: ArrayBuffer): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Badge variant for a signature request's status — pure, unit-tested. */
export function statusBadgeVariantForEsign(
  status: SignatureRequestStatus,
): "warning" | "success" | "destructive" | "outline" | "secondary" {
  switch (status) {
    case "pending":
      return "warning";
    case "signed":
      return "success";
    case "declined":
      return "destructive";
    case "voided":
      return "outline";
    case "expired":
      return "secondary";
  }
}

/** Maps an e-signature error to an actionable, specific message for the
 * signer — never a bare status code. A 409 covers two distinct backend
 * causes (SignatureRequestNotOpenError, DocumentMismatchError) that can't be
 * told apart from the status code alone (FastAPI sends {"detail": ...}, and
 * apiFetch only reads data.message/data.error), so the message is written to
 * read sensibly for either. */
export function describeEsignSubmitError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 404:
        return "This signing link is no longer valid.";
      case 409:
        return "This document has already been signed, declined, or voided, or the document changed since this link was created.";
      case 422:
        return "Please confirm both consent checkboxes before signing.";
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}
