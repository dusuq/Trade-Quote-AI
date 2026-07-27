"use client";

import * as React from "react";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { createProposal, type CreateProposalInput } from "@/lib/proposals";
import type { ProposalTemplate } from "@/lib/proposal-templates";
import type { Quote } from "@/lib/quotes";
import type { Customer } from "@/lib/customers";
import { formatMoney } from "@/lib/money";
import { ApiError } from "@/lib/api-client";

const createProposalFormSchema = z.object({
  templateId: z.string().min(1, "Select a template"),
  termsText: z.string().optional(),
  warrantyText: z.string().optional(),
});

type CreateProposalFormInput = z.infer<typeof createProposalFormSchema>;

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
    scope_of_work: quote.title ?? quote.number,
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

  const defaultTemplate = templates.find((t) => t.is_default) ?? templates[0];

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateProposalFormInput>({
    resolver: zodResolver(createProposalFormSchema),
    defaultValues: {
      templateId: defaultTemplate.id,
      termsText: defaultTemplate.default_terms_text ?? "",
      warrantyText: defaultTemplate.default_warranty_text ?? "",
    },
  });

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
            <Select id="templateId" {...register("templateId")}>
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
            <Label htmlFor="termsText">Terms (optional override)</Label>
            <textarea
              id="termsText"
              rows={4}
              className={cn(
                "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
              )}
              {...register("termsText")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="warrantyText">Warranty (optional override)</Label>
            <textarea
              id="warrantyText"
              rows={4}
              className={cn(
                "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
              )}
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
