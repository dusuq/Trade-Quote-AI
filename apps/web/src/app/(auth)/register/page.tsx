"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { register as registerTenant, registerSchema, type RegisterInput } from "@/lib/auth";
import { authStore } from "@/lib/auth-store";
import { ApiError } from "@/lib/api-client";

export default function RegisterPage() {
  const router = useRouter();
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const {
    register: field,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterInput>({ resolver: zodResolver(registerSchema) });

  async function onSubmit(values: RegisterInput) {
    setServerError(null);
    setSubmitting(true);
    try {
      const tokens = await registerTenant(values);
      authStore.setTokens(tokens.access_token, tokens.refresh_token);
      router.push("/dashboard");
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Unable to create your workspace. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your workspace</CardTitle>
        <CardDescription>Start quoting in minutes.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="tenantName">Company name</Label>
            <Input id="tenantName" placeholder="Acme Electric" {...field("tenantName")} />
            {errors.tenantName && (
              <p className="text-sm text-destructive">{errors.tenantName.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="slug">Workspace URL</Label>
            <Input id="slug" placeholder="acme-electric" {...field("slug")} />
            {errors.slug && <p className="text-sm text-destructive">{errors.slug.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="ownerName">Your name</Label>
            <Input id="ownerName" placeholder="Jordan Rivera" {...field("ownerName")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ownerEmail">Email</Label>
            <Input
              id="ownerEmail"
              type="email"
              placeholder="you@company.com"
              {...field("ownerEmail")}
            />
            {errors.ownerEmail && (
              <p className="text-sm text-destructive">{errors.ownerEmail.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="ownerPassword">Password</Label>
            <Input id="ownerPassword" type="password" {...field("ownerPassword")} />
            {errors.ownerPassword && (
              <p className="text-sm text-destructive">{errors.ownerPassword.message}</p>
            )}
          </div>

          {serverError && <p className="text-sm text-destructive">{serverError}</p>}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Creating workspace…" : "Create workspace"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Already have a workspace?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
