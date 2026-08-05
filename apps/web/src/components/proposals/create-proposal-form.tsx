"use client";

import * as React from "react";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { WriteScopePanel } from "@/components/proposals/write-scope-panel";
import { createProposal, type CreateProposalInput } from "@/lib/proposals";
import type { ProposalTemplate } from "@/lib/proposal-templates";
import type { Quote } from "@/lib/quotes";
import type { Customer } from "@/lib/customers";
import { formatMoney } from "@/lib/money";
import { ApiError } from "@/lib/api-client";

const createProposalFormSchema = z.object({
  templateId: z.string().min(1, "Select a template"),
  scopeOfWork: z.string().trim().min(1, "Scope of work is required"),
  termsText: z.string().optional(),
  warrantyText: z.string().optional(),
});

type CreateProposalFormInput = z.infer<typeof createProposalFormSchema>;

/** Shared textarea styling — mirrors template-form.tsx's local `textareaClassName`. */
const textareaClassName =
  "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Builds a substantive, user-editable draft of the "Scope of Work" PDF section
 * from data already loaded on this screen: the quote's title (if any) plus its
 * line item descriptions. A quote's title is optional and its number is just an
 * identifier, so neither alone is acceptable filler for a customer-facing PDF.
 */
function buildDefaultScopeOfWork(quote: Quote): string {
  const title = quote.title?.trim();
  const itemDescriptions = quote.line_items.map((item) => item.description.trim()).filter(Boolean);
  const parts: string[] = [];
  if (title) parts.push(title);
  if (itemDescriptions.length > 0) parts.push(itemDescriptions.join("\n"));
  return parts.join("\n\n");
}

/** Maps the loaded quote + customer + chosen template into the API's wire shape. */
function buildCreateProposalInput(
  quote: Quote,
  customer: Customer,
  template: ProposalTemplate,
  values: CreateProposalFormInput,
): CreateProposalInput {
  return {
    quote_id: quote.id,
    template_id: template.id,
    branding: {
      company_name: template.company_name,
      logo_path: template.logo_url,
      primary_color: template.primary_color,
      phone: template.phone,
      email: template.email,
      website: template.website,
    },
    customer: {
      display_name: customer.display_name,
      email: customer.email,
      phone: customer.phone,
      property_address: null,
    },
    line_items: quote.line_items.map((item) => ({
      description: item.description,
      quantity: item.quantity,
      unit: item.unit,
      unit_price: { amount_minor: item.unit_price_minor, currency: quote.currency },
      line_total: { amount_minor: item.line_total_minor, currency: quote.currency },
    })),
    subtotal_minor: quote.subtotal_minor,
    tax_minor: quote.tax_minor,
    total_minor: quote.total_minor,
    currency: quote.currency,
    scope_of_work: values.scopeOfWork,
    warranty_text: values.warrantyText || null,
    terms_text: values.termsText || null,
    valid_until: quote.valid_until,
    qr_payload_url: null,
  };
}

interface CreateProposalFormProps {
  token: string;
  quote: Quote;
  customer: Customer;
  templates: ProposalTemplate[];
}

/**
 * Mounted only once the quote, customer, and templates have all loaded, so its
 * react-hook-form defaultValues are correct on first render — no effect needed
 * to sync async data into form state.
 */
export function CreateProposalForm({ token, quote, customer, templates }: CreateProposalFormProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [writeScopeOpen, setWriteScopeOpen] = React.useState(false);

  const defaultTemplate = templates.find((t) => t.is_default) ?? templates[0];

  // Tracks the template whose defaults are currently reflected in termsText/warrantyText,
  // so a later template switch can tell "still equals the auto-filled default" (safe to
  // update) apart from "user edited it" (must not clobber). Not react state — it's an
  // internal bookkeeping ref, not something that should trigger a re-render.
  const activeTemplateRef = React.useRef(defaultTemplate);

  const {
    register,
    handleSubmit,
    getValues,
    setValue,
    formState: { errors },
  } = useForm<CreateProposalFormInput>({
    resolver: zodResolver(createProposalFormSchema),
    defaultValues: {
      templateId: defaultTemplate.id,
      scopeOfWork: buildDefaultScopeOfWork(quote),
      termsText: defaultTemplate.default_terms_text ?? "",
      warrantyText: defaultTemplate.default_warranty_text ?? "",
    },
  });

  const templateRegistration = register("templateId");

  /**
   * Switching templates after the terms/warranty textareas were prefilled used to do
   * nothing — a user could pick "Residential", switch to "Commercial", and submit with
   * Residential's boilerplate silently baked into the Commercial-tagged PDF, with no
   * visual cue. Re-sync each field to the new template's default, but ONLY when the
   * field still equals the previous template's default (i.e. the user hasn't manually
   * edited it) — a deliberate edit must never be clobbered. Do not "simplify" this back
   * to an unconditional overwrite.
   */
  function handleTemplateChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const newTemplate = templates.find((t) => t.id === event.target.value);
    if (!newTemplate) return;
    const previousTemplate = activeTemplateRef.current;

    const currentTerms = getValues("termsText");
    if ((currentTerms ?? "") === (previousTemplate.default_terms_text ?? "")) {
      setValue("termsText", newTemplate.default_terms_text ?? "", { shouldValidate: false });
    }

    const currentWarranty = getValues("warrantyText");
    if ((currentWarranty ?? "") === (previousTemplate.default_warranty_text ?? "")) {
      setValue("warrantyText", newTemplate.default_warranty_text ?? "", { shouldValidate: false });
    }

    activeTemplateRef.current = newTemplate;
  }

  const createMutation = useMutation({
    mutationFn: (values: CreateProposalFormInput) => {
      const template = templates.find((t) => t.id === values.templateId);
      if (!template) throw new ApiError(0, "Select a valid template.");
      return createProposal(token, buildCreateProposalInput(quote, customer, template, values));
    },
    onSuccess: (proposal) => {
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      router.push(`/proposals/${proposal.id}`);
    },
    onError: (err) => {
      setServerError(err instanceof ApiError ? err.message : "Unable to create the proposal.");
    },
  });

  function onSubmit(values: CreateProposalFormInput) {
    setServerError(null);
    createMutation.mutate(values);
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
      <Card>
        <CardHeader>
          <CardTitle>Quote {quote.number}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p>Customer: {customer.display_name}</p>
          <p>
            {quote.line_items.length} line item{quote.line_items.length === 1 ? "" : "s"} — Total{" "}
            <span className="font-medium text-foreground">
              {formatMoney(quote.total_minor, quote.currency)}
            </span>
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Template</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="templateId">Proposal template</Label>
            <Select
              id="templateId"
              {...templateRegistration}
              onChange={(event) => {
                templateRegistration.onChange(event);
                handleTemplateChange(event);
              }}
            >
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                  {template.is_default ? " (default)" : ""}
                </option>
              ))}
            </Select>
            {errors.templateId && (
              <p className="text-sm text-destructive">{errors.templateId.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="scopeOfWork">Scope of work</Label>
              {!writeScopeOpen && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setWriteScopeOpen(true)}
                >
                  Write Scope
                </Button>
              )}
            </div>
            {writeScopeOpen && (
              <WriteScopePanel
                token={token}
                quote={quote}
                onGenerated={(text) => setValue("scopeOfWork", text, { shouldValidate: true })}
                onClose={() => setWriteScopeOpen(false)}
              />
            )}
            <textarea
              id="scopeOfWork"
              rows={6}
              className={textareaClassName}
              {...register("scopeOfWork")}
            />
            {errors.scopeOfWork && (
              <p className="text-sm text-destructive">{errors.scopeOfWork.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="termsText">Terms (optional override)</Label>
            <textarea
              id="termsText"
              rows={4}
              className={textareaClassName}
              {...register("termsText")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="warrantyText">Warranty (optional override)</Label>
            <textarea
              id="warrantyText"
              rows={4}
              className={textareaClassName}
              {...register("warrantyText")}
            />
          </div>
        </CardContent>
      </Card>

      {serverError && <p className="text-sm text-destructive">{serverError}</p>}

      <div className="flex justify-end">
        <Button type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending ? "Creating…" : "Create Proposal"}
        </Button>
      </div>
    </form>
  );
}
