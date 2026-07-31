"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthGuard } from "@/lib/use-auth-guard";
import {
  listSignatureRequests,
  statusBadgeVariantForEsign,
  type SignatureRequestStatus,
} from "@/lib/esign";

const STATUS_TABS: { label: string; value: SignatureRequestStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Pending", value: "pending" },
  { label: "Signed", value: "signed" },
  { label: "Declined", value: "declined" },
  { label: "Voided", value: "voided" },
  { label: "Expired", value: "expired" },
];

export default function SignatureRequestsOverviewPage() {
  const token = useAuthGuard();
  const [activeTab, setActiveTab] = React.useState<SignatureRequestStatus | "all">("all");

  const {
    data: requests,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["signature-requests", { status: activeTab }],
    queryFn: () =>
      listSignatureRequests(token as string, activeTab === "all" ? {} : { status: activeTab }),
    enabled: !!token,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Signature Requests</h1>
        <p className="text-muted-foreground">
          Every e-signature request you&apos;ve sent, across all proposals.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <Button
            key={tab.value}
            type="button"
            size="sm"
            variant={activeTab === tab.value ? "default" : "outline"}
            onClick={() => setActiveTab(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t load signature requests. Is the API Gateway running?
            </p>
          )}
          {requests && requests.length === 0 && (
            <p className="text-sm text-muted-foreground">No signature requests found.</p>
          )}
          {requests && requests.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Signer</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 font-medium">Expires</th>
                    <th className="py-2 pr-4 font-medium">Proposal</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((request) => (
                    <tr key={request.id} className="border-b last:border-0 hover:bg-accent/50">
                      <td className="py-3 pr-4">
                        <p className="font-medium">{request.signer_name}</p>
                        <p className="text-xs text-muted-foreground">{request.signer_email}</p>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={statusBadgeVariantForEsign(request.status)} className="capitalize">
                          {request.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4">
                        {new Date(request.expires_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 pr-4">
                        <Link href={`/proposals/${request.proposal_id}`} className="hover:underline">
                          View proposal
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
