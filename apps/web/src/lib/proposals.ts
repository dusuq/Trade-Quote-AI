import { apiFetch, ApiError } from "@/lib/api-client";
import { config } from "@/config";

export interface Proposal {
  id: string;
  tenant_id: string;
  quote_id: string;
  template_id: string;
  number: string;
  status: "draft" | "sent" | "viewed";
  current_version: number;
  storage_key: string | null;
  sent_at: string | null;
  viewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProposalVersion {
  id: string;
  version: number;
  snapshot: Record<string, unknown>;
  created_at: string;
}

interface MoneyInput {
  amount_minor: number;
  currency?: string;
}

interface LineItemInput {
  description: string;
  quantity: number;
  unit: string;
  unit_price: MoneyInput;
  line_total: MoneyInput;
}

export interface CreateProposalInput {
  quote_id: string;
  template_id: string;
  branding: {
    company_name: string;
    logo_path?: string | null;
    primary_color?: string;
    phone?: string | null;
    email?: string | null;
    website?: string | null;
  };
  customer: {
    display_name: string;
    email?: string | null;
    phone?: string | null;
    property_address?: string | null;
  };
  line_items: LineItemInput[];
  subtotal_minor: number;
  tax_minor: number;
  total_minor: number;
  currency: string;
  scope_of_work: string;
  warranty_text?: string | null;
  terms_text?: string | null;
  valid_until?: string | null;
  qr_payload_url?: string | null;
}

/** Maps the web's human-readable input shape to the wire DTO the backend expects. */
function toCreatePayload(input: CreateProposalInput) {
  return {
    quote_id: input.quote_id,
    template_id: input.template_id,
    branding: input.branding,
    customer: input.customer,
    line_items: input.line_items,
    subtotal: { amount_minor: input.subtotal_minor, currency: input.currency },
    tax: { amount_minor: input.tax_minor, currency: input.currency },
    total: { amount_minor: input.total_minor, currency: input.currency },
    scope_of_work: input.scope_of_work,
    warranty_text: input.warranty_text ?? null,
    terms_text: input.terms_text ?? null,
    valid_until: input.valid_until ?? null,
    qr_payload_url: input.qr_payload_url ?? null,
  };
}

export function createProposal(token: string, input: CreateProposalInput): Promise<Proposal> {
  return apiFetch<Proposal>("/v1/proposals", {
    method: "POST",
    token,
    body: toCreatePayload(input),
  });
}

export function listProposals(token: string, quoteId?: string): Promise<Proposal[]> {
  const qs = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : "";
  return apiFetch<Proposal[]>(`/v1/proposals${qs}`, { token });
}

export function getProposal(token: string, proposalId: string): Promise<Proposal> {
  return apiFetch<Proposal>(`/v1/proposals/${proposalId}`, { token });
}

export function sendProposal(token: string, proposalId: string, channel = "email"): Promise<Proposal> {
  return apiFetch<Proposal>(`/v1/proposals/${proposalId}/send`, {
    method: "POST",
    token,
    body: { channel },
  });
}

/**
 * Fetches the proposal's PDF via the authenticated GET /v1/proposals/{id}/pdf
 * route (T107) — NOT the public /view route. /view is customer-facing: it
 * 404s on a DRAFT proposal (blocking any preview before send) and, on a SENT
 * proposal, flips it to VIEWED and stamps viewed_at — the exact signal this
 * feature exists to capture from the *customer*, not the contractor's own
 * preview click. `apiFetch` always JSON-parses the body, so this uses a plain
 * authenticated fetch and returns the raw Blob for the caller to open via
 * `URL.createObjectURL`.
 */
export async function fetchProposalPdfBlob(token: string, proposalId: string): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(`${config.apiUrl}/v1/proposals/${proposalId}/pdf`, {
      headers: { authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError(0, "Network error — is the API Gateway running?");
  }
  if (!res.ok) {
    throw new ApiError(res.status, `Failed to load the PDF (status ${res.status}).`);
  }
  return res.blob();
}

/**
 * Unauthenticated GET /v1/proposals/{id}/view — the public, customer-facing
 * PDF view (T204b's public signing page). This is the SAME route the
 * proposal detail page already displays as the shareable link (see
 * `publicViewUrl` there); calling it here marks the proposal VIEWED and
 * stamps viewed_at server-side, same as a customer opening that link
 * directly. Do not call this from any contractor-facing surface — use
 * `fetchProposalPdfBlob` for that.
 */
export async function fetchPublicProposalPdfBlob(proposalId: string): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(`${config.apiUrl}/v1/proposals/${proposalId}/view`);
  } catch {
    throw new ApiError(0, "Network error — is the API Gateway running?");
  }
  if (!res.ok) {
    throw new ApiError(res.status, `Failed to load the document (status ${res.status}).`);
  }
  return res.blob();
}

/** Maps a proposal status to a Badge variant — pure, unit-tested. */
export function statusBadgeVariantForProposal(
  status: Proposal["status"],
): "default" | "warning" {
  return status === "draft" ? "warning" : "default";
}
