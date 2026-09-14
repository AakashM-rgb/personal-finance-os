/**
 * Single HTTP client for the backend API. Every request/mutation in the app
 * goes through this module - no component should call `fetch` directly.
 *
 * The access token is held only in memory (passed in by the auth context),
 * never in localStorage, to limit exposure if a script-injection
 * vulnerability were ever present. The refresh token lives in an httpOnly
 * cookie the browser sends automatically; this client never touches it
 * directly.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export interface ApiErrorBody {
  code: string;
  message: string;
  field_errors: Record<string, string> | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string> | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.fieldErrors = body.field_errors;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  accessToken?: string | null;
  csrfToken?: string | null;
  /** Sent as the `Idempotency-Key` header - lets a retried create be safely replayed. */
  idempotencyKey?: string | null;
}

interface Envelope<T> {
  data: T;
  error: ApiErrorBody | null;
  meta: Record<string, unknown> | null;
}

async function performRequest<T>(path: string, options: RequestOptions): Promise<Envelope<T>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }
  if (options.csrfToken) {
    headers["x-csrf-token"] = options.csrfToken;
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const envelope = await response.json();

  if (!response.ok) {
    throw new ApiError(response.status, envelope.error);
  }

  return envelope as Envelope<T>;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const envelope = await performRequest<T>(path, options);
  return envelope.data;
}

/** Like apiRequest, but also returns `meta` (e.g. pagination's total count). */
export async function apiRequestWithMeta<T>(
  path: string,
  options: RequestOptions = {}
): Promise<{ data: T; meta: Record<string, unknown> | null }> {
  const envelope = await performRequest<T>(path, options);
  return { data: envelope.data, meta: envelope.meta };
}

/** Reads a non-httpOnly cookie by name (used for the CSRF double-submit cookie). */
export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}
