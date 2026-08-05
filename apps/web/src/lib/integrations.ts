import { apiFetch, ApiError } from "@/lib/api-client";

export type IntegrationProvider = "quickbooks" | "xero" | "zapier";
export type ConnectionStatus = "pending" | "active" | "expired" | "revoked" | "error";

export interface IntegrationConnection {
  id: string;
  provider: IntegrationProvider;
  status: ConnectionStatus;
  external_account_id: string | null;
  display_name: string | null;
  scopes: string | null;
  token_expires_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  created_by: string | null;
}

export interface SyncLogEntry {
  id: string;
  connection_id: string;
  direction: "push" | "pull";
  entity_type: string;
  entity_id: string | null;
  status: "pending" | "running" | "success" | "failed";
  external_id: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export function listConnections(token: string): Promise<IntegrationConnection[]> {
  return apiFetch<{ items: IntegrationConnection[]; total: number }>(
    "/v1/integrations/connections",
    {
      token,
    },
  ).then((res) => res.items);
}

export function createConnection(
  token: string,
  input: { provider: IntegrationProvider; display_name?: string },
): Promise<IntegrationConnection> {
  return apiFetch<IntegrationConnection>("/v1/integrations/connections", {
    method: "POST",
    token,
    body: input,
  });
}

/** Returns the provider's authorize URL — the caller redirects the browser
 * there (`window.location.href = authorize_url`). QuickBooks/Xero only;
 * calling this for a `zapier` connection 409s (see `connectZapier`). */
export function startOAuth(
  token: string,
  connectionId: string,
): Promise<{ connection: IntegrationConnection; authorize_url: string }> {
  return apiFetch(`/v1/integrations/connections/${connectionId}/oauth/start`, {
    method: "POST",
    token,
  });
}

/** Activates a Zapier connection and mints a signing secret, returned in
 * `api_key` exactly once — the caller must show it to the user immediately
 * (it is not retrievable again; only rotatable by calling this again). */
export function connectZapier(
  token: string,
  connectionId: string,
): Promise<{ connection: IntegrationConnection; api_key: string }> {
  return apiFetch(`/v1/integrations/connections/${connectionId}/zapier/connect`, {
    method: "POST",
    token,
  });
}

export function revokeConnection(
  token: string,
  connectionId: string,
): Promise<IntegrationConnection> {
  return apiFetch<IntegrationConnection>(`/v1/integrations/connections/${connectionId}/revoke`, {
    method: "POST",
    token,
  });
}

export function listSyncLogs(
  token: string,
  connectionId: string,
  limit = 50,
): Promise<SyncLogEntry[]> {
  return apiFetch<{ items: SyncLogEntry[]; total: number }>(
    `/v1/integrations/connections/${connectionId}/sync?limit=${limit}`,
    { token },
  ).then((res) => res.items);
}

export interface PushInvoiceInput {
  entity_type: string;
  entity_id?: string | null;
  payload: Record<string, unknown>;
}

/** Pushes one quote/invoice to the connected QuickBooks/Xero account and
 * returns the resulting `SyncLogEntry` — success or failure, never throws
 * for a failed sync (only for a request that couldn't even be attempted,
 * e.g. a 404/409 on the connection itself). */
export function pushInvoiceSync(
  token: string,
  connectionId: string,
  input: PushInvoiceInput,
): Promise<SyncLogEntry> {
  return apiFetch<SyncLogEntry>(`/v1/integrations/connections/${connectionId}/sync/push`, {
    method: "POST",
    token,
    body: input,
  });
}

export const PROVIDER_LABELS: Record<IntegrationProvider, string> = {
  quickbooks: "QuickBooks Online",
  xero: "Xero",
  zapier: "Zapier",
};

export function statusBadgeVariantForConnection(
  status: ConnectionStatus,
): "success" | "warning" | "destructive" | "outline" | "secondary" {
  switch (status) {
    case "active":
      return "success";
    case "pending":
      return "warning";
    case "expired":
      return "warning";
    case "revoked":
      return "outline";
    case "error":
      return "destructive";
  }
}

export function statusBadgeVariantForSync(
  status: SyncLogEntry["status"],
): "success" | "warning" | "destructive" | "outline" | "secondary" {
  switch (status) {
    case "success":
      return "success";
    case "running":
    case "pending":
      return "warning";
    case "failed":
      return "destructive";
  }
}

export function describeConnectionError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 404:
        return "That connection no longer exists.";
      case 409:
        return err.message || "This connection can't be changed right now.";
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}
