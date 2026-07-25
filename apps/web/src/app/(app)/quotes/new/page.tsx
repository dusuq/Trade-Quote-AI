"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { listCustomers } from "@/lib/customers";
import {
  calculateFormSubtotalMinor,
  createQuote,
  newQuoteFormSchema,
  type NewQuoteFormInput,
} from "@/lib/quotes";
import { formatMoney } from "@/lib/money";
import { ApiError } from "@/lib/api-client";

const EMPTY_LINE_ITEM = { description: "", quantity: 1, unit: "each", unitPriceDollars: 0 };

export default function NewQuotePage() {
  const token = useAuthGuard();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = React.useState<string | null>(null);

  const { data: customers } = useQuery({
    queryKey: ["customers"],
    queryFn: () => listCustomers(token as string),
    enabled: !!token,
  });

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<NewQuoteFormInput>({
    resolver: zodResolver(newQuoteFormSchema),
    defaultValues: {
      customerId: "",
      title: "",
      taxRatePercent: 0,
      lineItems: [EMPTY_LINE_ITEM],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "lineItems" });
  const watchedLineItems = watch("lineItems");
  const subtotalMinor = calculateFormSubtotalMinor(watchedLineItems ?? []);

  const createMutation = useMutation({
    mutationFn: (values: NewQuoteFormInput) => createQuote(token as string, values),
    onSuccess: (quote) => {
      queryClient.invalidateQueries({ queryKey: ["quotes"] });
      router.push(`/quotes/${quote.id}`);
    },
    onError: (err) => {
      setServerError(err instanceof ApiError ? err.message : "Unable to create the quote.");
    },
  });

  function onSubmit(values: NewQuoteFormInput) {
    setServerError(null);
    createMutation.mutate(values);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Quote</h1>
        <p className="text-muted-foreground">Build a professional estimate in minutes.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="customerId">Customer</Label>
                <Select id="customerId" {...register("customerId")}>
                  <option value="">Select a customer…</option>
                  {customers?.items.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name}
                    </option>
                  ))}
                </Select>
                {errors.customerId && (
                  <p className="text-sm text-destructive">{errors.customerId.message}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="title">Title (optional)</Label>
                <Input id="title" placeholder="Panel upgrade" {...register("title")} />
              </div>
            </div>
            <div className="w-40 space-y-2">
              <Label htmlFor="taxRatePercent">Tax rate (%)</Label>
              <Input
                id="taxRatePercent"
                type="number"
                step="0.01"
                min="0"
                max="100"
                {...register("taxRatePercent")}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Line Items</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {fields.map((field, index) => (
              <div key={field.id} className="grid grid-cols-12 items-start gap-2">
                <div className="col-span-12 sm:col-span-5">
                  {index === 0 && <Label className="text-xs">Description</Label>}
                  <Input
                    placeholder="Replace 200A panel"
                    {...register(`lineItems.${index}.description`)}
                  />
                  {errors.lineItems?.[index]?.description && (
                    <p className="text-xs text-destructive">
                      {errors.lineItems[index]?.description?.message}
                    </p>
                  )}
                </div>
                <div className="col-span-4 sm:col-span-2">
                  {index === 0 && <Label className="text-xs">Qty</Label>}
                  <Input type="number" step="any" {...register(`lineItems.${index}.quantity`)} />
                </div>
                <div className="col-span-4 sm:col-span-2">
                  {index === 0 && <Label className="text-xs">Unit</Label>}
                  <Input placeholder="each" {...register(`lineItems.${index}.unit`)} />
                </div>
                <div className="col-span-3 sm:col-span-2">
                  {index === 0 && <Label className="text-xs">Unit Price</Label>}
                  <Input
                    type="number"
                    step="0.01"
                    {...register(`lineItems.${index}.unitPriceDollars`)}
                  />
                </div>
                <div className="col-span-1 flex items-end justify-end">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => fields.length > 1 && remove(index)}
                    disabled={fields.length === 1}
                    aria-label="Remove line item"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
            {errors.lineItems?.root && (
              <p className="text-sm text-destructive">{errors.lineItems.root.message}</p>
            )}

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => append(EMPTY_LINE_ITEM)}
            >
              <Plus className="h-4 w-4" /> Add line item
            </Button>

            <div className="flex justify-end border-t pt-4">
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Subtotal</p>
                <p className="text-lg font-semibold">{formatMoney(subtotalMinor)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {serverError && <p className="text-sm text-destructive">{serverError}</p>}

        <div className="flex justify-end">
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? "Creating…" : "Create Quote"}
          </Button>
        </div>
      </form>
    </div>
  );
}
