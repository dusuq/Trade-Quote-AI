import { apiFetch } from "@/lib/api-client";

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
  const qs = quoteId ? `?quote_id=${quoteId}` : "";
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

/** Maps a proposal status to a Badge variant — pure, unit-tested. */
export function statusBadgeVariantForProposal(
  status: Proposal["status"],
): "default" | "warning" {
  return status === "draft" ? "warning" : "default";
}
