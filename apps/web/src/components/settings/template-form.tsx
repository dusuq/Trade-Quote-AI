"use client";

import * as React from "react";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  createTemplate,
  updateTemplate,
  type ProposalTemplate,
  type TemplateInput,
} from "@/lib/proposal-templates";
import { ApiError } from "@/lib/api-client";

const templateFormSchema = z.object({
  name: z.string().min(1, "Name is required"),
  companyName: z.string().min(1, "Company name is required"),
  logoUrl: z.string().optional().or(z.literal("")),
  primaryColor: z.string().min(1, "Pick a color"),
  phone: z.string().optional().or(z.literal("")),
  email: z.string().optional().or(z.literal("")),
  website: z.string().optional().or(z.literal("")),
  defaultTermsText: z.string().optional().or(z.literal("")),
  defaultWarrantyText: z.string().optional().or(z.literal("")),
  isDefault: z.boolean(),
});

type TemplateFormInput = z.infer<typeof templateFormSchema>;

function toTemplateInput(values: TemplateFormInput): TemplateInput {
  return {
    name: values.name,
    company_name: values.companyName,
    logo_url: values.logoUrl || null,
    primary_color: values.primaryColor,
    phone: values.phone || null,
    email: values.email || null,
    website: values.website || null,
    default_terms_text: values.defaultTermsText || null,
    default_warranty_text: values.defaultWarrantyText || null,
    is_default: values.isDefault,
  };
}

const textareaClassName = cn(
  "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
);

interface TemplateFormProps {
  token: string;
  template?: ProposalTemplate;
  onSaved: () => void;
  onCancel: () => void;
}

export function TemplateForm({ token, template, onSaved, onCancel }: TemplateFormProps) {
  const queryClient = useQueryClient();
  const [serverError, setServerError] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<TemplateFormInput>({
    resolver: zodResolver(templateFormSchema),
    defaultValues: {
      name: template?.name ?? "",
      companyName: template?.company_name ?? "",
      logoUrl: template?.logo_url ?? "",
      primaryColor: template?.primary_color ?? "#111827",
      phone: template?.phone ?? "",
      email: template?.email ?? "",
      website: template?.website ?? "",
      defaultTermsText: template?.default_terms_text ?? "",
      defaultWarrantyText: template?.default_warranty_text ?? "",
      isDefault: template?.is_default ?? false,
    },
  });

  const saveMutation = useMutation({
    mutationFn: (values: TemplateFormInput) =>
      template
        ? updateTemplate(token, template.id, toTemplateInput(values))
        : createTemplate(token, toTemplateInput(values)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposal-templates"] });
      onSaved();
    },
    onError: (err) => {
      setServerError(err instanceof ApiError ? err.message : "Unable to save this template.");
    },
  });

  function onSubmit(values: TemplateFormInput) {
    setServerError(null);
    saveMutation.mutate(values);
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="name">Template name</Label>
          <Input id="name" placeholder="Standard proposal" {...register("name")} />
          {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="companyName">Company name</Label>
          <Input id="companyName" placeholder="Acme Electric" {...register("companyName")} />
          {errors.companyName && (
            <p className="text-sm text-destructive">{errors.companyName.message}</p>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="logoUrl">Logo URL (optional)</Label>
          <Input id="logoUrl" placeholder="https://…" {...register("logoUrl")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="primaryColor">Primary color</Label>
          <div className="flex items-center gap-2">
            <input
              id="primaryColor"
              type="color"
              className="h-10 w-14 cursor-pointer rounded border border-input bg-background"
              {...register("primaryColor")}
            />
          </div>
          {errors.primaryColor && (
            <p className="text-sm text-destructive">{errors.primaryColor.message}</p>
          )}
        </div>
        <div className="flex items-end gap-2 pb-2">
          <input
            id="isDefault"
            type="checkbox"
            className="h-4 w-4 rounded border-input"
            {...register("isDefault")}
          />
          <Label htmlFor="isDefault" className="font-normal">
            Use as default template
          </Label>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="phone">Phone (optional)</Label>
          <Input id="phone" {...register("phone")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">Email (optional)</Label>
          <Input id="email" type="email" {...register("email")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="website">Website (optional)</Label>
          <Input id="website" {...register("website")} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="defaultTermsText">Default terms (optional)</Label>
          <textarea
            id="defaultTermsText"
            rows={4}
            className={textareaClassName}
            {...register("defaultTermsText")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="defaultWarrantyText">Default warranty (optional)</Label>
          <textarea
            id="defaultWarrantyText"
            rows={4}
            className={textareaClassName}
            {...register("defaultWarrantyText")}
          />
        </div>
      </div>

      {serverError && <p className="text-sm text-destructive">{serverError}</p>}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={saveMutation.isPending}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={saveMutation.isPending}>
          {saveMutation.isPending ? "Saving…" : "Save Template"}
        </Button>
      </div>
    </form>
  );
}
