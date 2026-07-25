import { config } from "@/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Thin fetch wrapper around the API Gateway. Attaches the bearer token when
 * provided; the gateway verifies it and forwards tenant/user headers to services.
 *
 * A hard timeout guarantees this always settles — some network stacks
 * (proxies, certain sandboxed/automated browser contexts) can leave a fetch
 * neither resolving nor rejecting when a target is unreachable, which would
 * otherwise leave a page's loading state stuck forever with no feedback.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (options.token) headers.authorization = `Bearer ${options.token}`;

  let res: Response;
  try {
    res = await fetch(`${config.apiUrl}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError(0, "Request timed out — is the API Gateway running?");
    }
    throw new ApiError(0, "Network error — is the API Gateway running?");
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const message =
      (data && (data.message || data.error)) || `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message);
  }
  return data as T;
}
