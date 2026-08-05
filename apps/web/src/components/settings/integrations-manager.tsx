"use client";

import * as React from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  connectZapier,
  createConnection,
  describeConnectionError,
  listConnections,
  listSyncLogs,
  PROVIDER_LABELS,
  revokeConnection,
  startOAuth,
  statusBadgeVariantForConnection,
  statusBadgeVariantForSync,
  type IntegrationConnection,
  type IntegrationProvider,
} from "@/lib/integrations";

interface IntegrationsManagerProps {
  token: string;
}

const PROVIDERS: IntegrationProvider[] = ["quickbooks", "xero", "zapier"];

/** For each provider, the most recently created connection (list is already
 * ordered newest-first by the backend) — a tenant can have older revoked
 * rows for the same provider, but only the newest one is actionable. */
function latestByProvider(
  connections: IntegrationConnection[],
): Partial<Record<IntegrationProvider, IntegrationConnection>> {
  const result: Partial<Record<IntegrationProvider, IntegrationConnection>> = {};
  for (const conn of connections) {
    if (!result[conn.provider]) result[conn.provider] = conn;
  }
  return result;
}

export function IntegrationsManager({ token }: IntegrationsManagerProps) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [zapierSecret, setZapierSecret] = React.useState<{
    provider: string;
    apiKey: string;
  } | null>(null);
  const [historyConnection, setHistoryConnection] = React.useState<IntegrationConnection | null>(
    null,
  );

  const connectionsQuery = useQuery({
    queryKey: ["integration-connections"],
    queryFn: () => listConnections(token),
    enabled: !!token,
  });

  // The OAuth callback redirects the browser back here with `?provider=` +
  // `connected=true|false` (+ `error=` on failure) — see integration-service's
  // app/interface/routes.py `_redirect_url`. Surface it once, then scrub the
  // query string so a page refresh doesn't re-show a stale banner.
  const [callbackBanner, setCallbackBanner] = React.useState<{
    provider: string;
    connected: boolean;
    error: string | null;
  } | null>(null);

  React.useEffect(() => {
    const provider = searchParams.get("provider");
    const connected = searchParams.get("connected");
    if (!provider || connected === null) return;
    setCallbackBanner({
      provider,
      connected: connected === "true",
      error: searchParams.get("error"),
    });
    queryClient.invalidateQueries({ queryKey: ["integration-connections"] });
    router.replace("/settings/integrations");
  }, [queryClient, router, searchParams]);

  const connectionByProvider = React.useMemo(
    () => latestByProvider(connectionsQuery.data ?? []),
    [connectionsQuery.data],
  );

  const startOAuthMutation = useMutation({
    mutationFn: async (provider: IntegrationProvider) => {
      const existing = connectionByProvider[provider];
      const conn =
        existing && existing.status === "pending"
          ? existing
          : await createConnection(token, { provider });
      return startOAuth(token, conn.id);
    },
    onSuccess: (result) => {
      window.location.href = result.authorize_url;
    },
    onError: (err) => setActionError(describeConnectionError(err)),
  });

  const connectZapierMutation = useMutation({
    mutationFn: async () => {
      const existing = connectionByProvider.zapier;
      const conn = existing ?? (await createConnection(token, { provider: "zapier" }));
      return connectZapier(token, conn.id);
    },
    onSuccess: (result) => {
      setZapierSecret({ provider: "zapier", apiKey: result.api_key });
      queryClient.invalidateQueries({ queryKey: ["integration-connections"] });
    },
    onError: (err) => setActionError(describeConnectionError(err)),
  });

  const revokeMutation = useMutation({
    mutationFn: (connectionId: string) => revokeConnection(token, connectionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integration-connections"] }),
    onError: (err) => setActionError(describeConnectionError(err)),
  });

  function handleConnect(provider: IntegrationProvider) {
    setActionError(null);
    if (provider === "zapier") {
      connectZapierMutation.mutate();
    } else {
      startOAuthMutation.mutate(provider);
    }
  }

  return (
    <div className="space-y-6">
      {callbackBanner && (
        <div
          className={`rounded-md border p-3 text-sm ${
            callbackBanner.connected
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-destructive/30 bg-destructive/10 text-destructive"
          }`}
        >
          {callbackBanner.connected
            ? `${PROVIDER_LABELS[callbackBanner.provider as IntegrationProvider] ?? callbackBanner.provider} connected successfully.`
            : `Couldn't connect ${PROVIDER_LABELS[callbackBanner.provider as IntegrationProvider] ?? callbackBanner.provider}${callbackBanner.error ? `: ${callbackBanner.error}` : "."}`}
        </div>
      )}

      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      {connectionsQuery.isLoading && (
        <p className="text-sm text-muted-foreground">Loading integrations…</p>
      )}
      {connectionsQuery.isError && (
        <div className="space-y-2">
          <p className="text-sm text-destructive">
            Couldn&apos;t load integrations. Is the API Gateway running?
          </p>
          <Button size="sm" variant="outline" onClick={() => connectionsQuery.refetch()}>
            Retry
          </Button>
        </div>
      )}

      {connectionsQuery.data && (
        <div className="grid gap-4 sm:grid-cols-3">
          {PROVIDERS.map((provider) => {
            const conn = connectionByProvider[provider];
            const isConnecting =
              provider === "zapier"
                ? connectZapierMutation.isPending
                : startOAuthMutation.isPending;
            return (
              <Card key={provider}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between text-base">
                    {PROVIDER_LABELS[provider]}
                    {conn && (
                      <Badge variant={statusBadgeVariantForConnection(conn.status)}>
                        {conn.status}
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {conn?.external_account_id && (
                    <p className="text-xs text-muted-foreground">
                      Account: {conn.external_account_id}
                    </p>
                  )}
                  {!conn || conn.status === "revoked" || conn.status === "error" ? (
                    <Button
                      size="sm"
                      onClick={() => handleConnect(provider)}
                      disabled={isConnecting}
                    >
                      {isConnecting ? "Connecting…" : "Connect"}
                    </Button>
                  ) : conn.status === "pending" ? (
                    <Button
                      size="sm"
                      onClick={() => handleConnect(provider)}
                      disabled={isConnecting}
                    >
                      {isConnecting ? "Connecting…" : "Continue connecting"}
                    </Button>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {provider !== "zapier" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setHistoryConnection(conn)}
                        >
                          Sync history
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => revokeMutation.mutate(conn.id)}
                        disabled={revokeMutation.isPending}
                      >
                        Disconnect
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog
        open={zapierSecret !== null}
        onClose={() => setZapierSecret(null)}
        title="Zapier connected"
      >
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Paste this into your Zap&apos;s &quot;Webhooks by Zapier&quot; auth step. It is shown
            once — if you lose it, connect again to generate a new one.
          </p>
          <code className="block break-all rounded-md border bg-muted p-3 text-sm">
            {zapierSecret?.apiKey}
          </code>
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setZapierSecret(null)}>
              Done
            </Button>
          </div>
        </div>
      </Dialog>

      {historyConnection && (
        <SyncHistoryDialog
          token={token}
          connection={historyConnection}
          onClose={() => setHistoryConnection(null)}
        />
      )}
    </div>
  );
}

function SyncHistoryDialog({
  token,
  connection,
  onClose,
}: {
  token: string;
  connection: IntegrationConnection;
  onClose: () => void;
}) {
  const historyQuery = useQuery({
    queryKey: ["integration-sync-logs", connection.id],
    queryFn: () => listSyncLogs(token, connection.id),
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={`${PROVIDER_LABELS[connection.provider]} sync history`}
      className="max-w-2xl"
    >
      {historyQuery.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {historyQuery.isError && (
        <p className="text-sm text-destructive">Couldn&apos;t load sync history.</p>
      )}
      {historyQuery.data && historyQuery.data.length === 0 && (
        <p className="text-sm text-muted-foreground">No syncs recorded yet.</p>
      )}
      {historyQuery.data && historyQuery.data.length > 0 && (
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-2">Entity</th>
                <th className="py-2 pr-2">Direction</th>
                <th className="py-2 pr-2">Status</th>
                <th className="py-2 pr-2">External ID</th>
                <th className="py-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {historyQuery.data.map((log) => (
                <tr key={log.id} className="border-b last:border-0">
                  <td className="py-2 pr-2">{log.entity_type}</td>
                  <td className="py-2 pr-2">{log.direction}</td>
                  <td className="py-2 pr-2">
                    <Badge variant={statusBadgeVariantForSync(log.status)}>{log.status}</Badge>
                  </td>
                  <td className="py-2 pr-2 font-mono text-xs">{log.external_id ?? "—"}</td>
                  <td className="py-2 text-xs text-muted-foreground">
                    {log.started_at ? new Date(log.started_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {historyQuery.data.some((log) => log.status === "failed" && log.error_message) && (
            <div className="mt-3 space-y-1">
              {historyQuery.data
                .filter((log) => log.status === "failed" && log.error_message)
                .map((log) => (
                  <p key={log.id} className="text-xs text-destructive">
                    {log.entity_type}: {log.error_message}
                  </p>
                ))}
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}
