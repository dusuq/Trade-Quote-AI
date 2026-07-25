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

/**
 * Thin fetch wrapper around the API Gateway. Attaches the bearer token when
 * provided; the gateway verifies it and forwards tenant/user headers to services.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (options.token) headers.authorization = `Bearer ${options.token}`;

  const res = await fetch(`${config.apiUrl}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const message =
      (data && (data.message || data.error)) || `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message);
  }
  return data as T;
}
