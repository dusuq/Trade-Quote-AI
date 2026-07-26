import { apiFetch } from "@/lib/api-client";

export interface ProposalTemplate {
  id: string;
  tenant_id: string;
  name: string;
  company_name: string;
  logo_url: string | null;
  primary_color: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  default_terms_text: string | null;
  default_warranty_text: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateInput {
  name: string;
  company_name: string;
  logo_url?: string | null;
  primary_color?: string;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  default_terms_text?: string | null;
  default_warranty_text?: string | null;
  is_default?: boolean;
}

export function listTemplates(token: string): Promise<ProposalTemplate[]> {
  return apiFetch<ProposalTemplate[]>("/v1/proposal-templates", { token });
}

export function createTemplate(token: string, input: TemplateInput): Promise<ProposalTemplate> {
  return apiFetch<ProposalTemplate>("/v1/proposal-templates", {
    method: "POST",
    token,
    body: input,
  });
}

export function updateTemplate(
  token: string,
  templateId: string,
  input: Partial<TemplateInput>,
): Promise<ProposalTemplate> {
  return apiFetch<ProposalTemplate>(`/v1/proposal-templates/${templateId}`, {
    method: "PUT",
    token,
    body: input,
  });
}
