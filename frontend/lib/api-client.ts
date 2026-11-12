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

// Resolved at build time by next.config.ts: "" (same-origin, through the
// /api/* proxy) when BACKEND_ORIGIN is set, otherwise NEXT_PUBLIC_API_URL or
// the local dev backend. Outside a Next.js build (unit tests) it is unset,
// and requests stay relative.
const API_BASE_URL = process.env.CLIENT_API_BASE_URL ?? "";

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
  /** Aborts the request client-side. Only for side-effect-free requests: an
   * aborted write may still have been applied by the server. */
  signal?: AbortSignal;
}

interface Envelope<T> {
  data: T;
  error: ApiErrorBody | null;
  meta: Record<string, unknown> | null;
}

/** The message to show a user for a failed request: the backend's own
 * user-facing message for an ApiError, otherwise the caller's fallback - never
 * a raw network/parse error string. */
export function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ApiErrorBody).code === "string" &&
    typeof (value as ApiErrorBody).message === "string"
  );
}

/**
 * Only a well-formed backend error envelope becomes an ApiError, whose
 * `message` is written for users and safe to display. Anything else
 * (a JSON body without an `error` object, e.g. from a proxy) becomes a plain
 * Error, and callers show their own friendly fallback for that case instead:
 * `err instanceof ApiError ? err.message : "Failed to load …"`.
 */
function toRequestError(status: number, envelope: unknown): Error {
  const body = (envelope as { error?: unknown } | null)?.error;
  return isErrorBody(body) ? new ApiError(status, body) : new Error(`Request failed (${status}).`);
}

/**
 * Called when an authenticated request gets a 401, with the access token that
 * request used. Resolves to a fresh access token to retry with, or null when
 * the session can't be recovered (the caller then gets the original 401).
 * Registered by AuthProvider, which owns the session and keeps the refresh
 * single-flight: refresh tokens rotate, and the backend treats reuse of a
 * rotated-out token as a compromise, so concurrent 401s must never each start
 * their own refresh.
 */
export type SessionRefresher = (failedAccessToken: string) => Promise<string | null>;

let sessionRefresher: SessionRefresher | null = null;

export function setSessionRefresher(refresher: SessionRefresher | null): void {
  sessionRefresher = refresher;
}

/** Auth endpoints that authenticate with the access token like any other
 * protected route, so an expired token there is recoverable. Every other auth
 * endpoint's 401 is the answer itself (bad credentials, a dead refresh
 * cookie), and retrying /auth/refresh from inside a refresh would loop. */
const RECOVERABLE_AUTH_PATHS = new Set(["/api/v1/auth/change-password"]);

function canRecoverSession(path: string): boolean {
  return !path.startsWith("/api/v1/auth/") || RECOVERABLE_AUTH_PATHS.has(path);
}

/**
 * Sends a request built for a given access token and, on a 401, recovers the
 * session once and retries with the new token. Only a 401 is retried - a 4xx
 * such as a wrong current password (422) is the server's answer. A 401 means
 * the auth dependency rejected the request before any handler ran, so
 * retrying can't double-apply a write.
 */
async function sendWithSessionRecovery(
  path: string,
  accessToken: string | null | undefined,
  send: (token: string | null | undefined) => Promise<Response>
): Promise<Response> {
  const response = await send(accessToken);
  if (
    response.status !== 401 ||
    !accessToken ||
    !sessionRefresher ||
    !canRecoverSession(path)
  ) {
    return response;
  }
  const freshToken = await sessionRefresher(accessToken);
  return freshToken ? send(freshToken) : response;
}

async function performRequest<T>(path: string, options: RequestOptions): Promise<Envelope<T>> {
  const response = await sendWithSessionRecovery(path, options.accessToken, (accessToken) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }
    if (options.csrfToken) {
      headers["x-csrf-token"] = options.csrfToken;
    }
    if (options.idempotencyKey) {
      headers["Idempotency-Key"] = options.idempotencyKey;
    }
    return fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      credentials: "include",
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  });

  const envelope = await response.json();

  if (!response.ok) {
    throw toRequestError(response.status, envelope);
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

/**
 * Like apiRequest, but sends a FormData body (multipart/form-data) instead of
 * JSON - the one place a file upload goes through, so it stays next to every
 * other request in this single HTTP client rather than a one-off `fetch`.
 * The browser sets the multipart Content-Type header (with its boundary)
 * itself; this must never set one explicitly.
 */
export async function apiUpload<T>(
  path: string,
  formData: FormData,
  options: { accessToken?: string | null } = {}
): Promise<T> {
  const response = await sendWithSessionRecovery(path, options.accessToken, (accessToken) =>
    fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: "include",
      body: formData,
    })
  );

  const envelope = await response.json();
  if (!response.ok) {
    throw toRequestError(response.status, envelope);
  }
  return envelope.data as T;
}

/**
 * Fetches a non-JSON, authenticated binary response (a receipt's stored
 * file, a report export) as a Blob. There is no public URL for this data -
 * every request carries the same bearer token as every other authenticated
 * call.
 */
export async function apiFetchBlob(path: string, accessToken?: string | null): Promise<Blob> {
  const response = await sendWithSessionRecovery(path, accessToken, (token) =>
    fetch(`${API_BASE_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "include",
    })
  );
  if (!response.ok) {
    const envelope = await response.json().catch(() => null);
    throw toRequestError(response.status, envelope);
  }
  return await response.blob();
}

/** Reads a non-httpOnly cookie by name (used for the CSRF double-submit cookie). */
export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}
