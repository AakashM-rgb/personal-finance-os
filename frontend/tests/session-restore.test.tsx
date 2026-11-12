import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "@/lib/api-client";
import { AuthProvider, refreshAccessToken, restoreSession, useAuth } from "@/lib/auth-context";
import { waitForBackend } from "@/lib/backend-readiness";

vi.mock("@/lib/backend-readiness", () => ({ waitForBackend: vi.fn() }));
const waitForBackendMock = vi.mocked(waitForBackend);

const USER = {
  id: "u1",
  email: "a@b.com",
  full_name: "Asha Rao",
  is_active: true,
  email_verified_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SESSION = {
  data: { access_token: "t1", token_type: "bearer", expires_in: 900, user: USER },
  error: null,
  meta: null,
};

function errorBody(code: string) {
  return { data: null, error: { code, message: "Nope.", field_errors: null }, meta: null };
}

const TRANSIENT_FAILURES: Array<[string, () => Promise<Response>]> = [
  ["a network failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ["a proxy's HTML 504 page", () => Promise.resolve(new Response("<html>504</html>", { status: 504 }))],
  ["a backend 500", () => Promise.resolve(jsonResponse(500, errorBody("internal_error")))],
  ["a 429 rate limit", () => Promise.resolve(jsonResponse(429, errorBody("rate_limited")))],
];

function urlOf(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input.toString();
}

/** Routes refresh to `refresh`, settings to a default, everything else to `other`. */
function stubBackend(
  refresh: () => Promise<Response>,
  other: () => Promise<Response> = () => Promise.resolve(jsonResponse(200, { data: [] }))
) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = urlOf(input);
    if (url.endsWith("/auth/refresh")) return refresh();
    if (url.endsWith("/settings")) return Promise.resolve(jsonResponse(200, { data: { theme: "system" } }));
    return other();
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    fetchMock,
    refreshCalls: () => fetchMock.mock.calls.filter(([i]) => urlOf(i).endsWith("/auth/refresh")),
  };
}

function Probe() {
  const auth = useAuth();
  const state = auth.isLoading ? "loading" : auth.user ? `signed in:${auth.accessToken}` : "signed out";
  return (
    <>
      <p>
        {state}
        {auth.connectionIssue ? ` [${auth.connectionIssue}]` : ""}
        {auth.sessionExpired ? " (expired)" : ""}
      </p>
      <button type="button" onClick={auth.retrySessionRestore}>
        Retry
      </button>
    </>
  );
}

beforeEach(() => {
  document.cookie = "csrf_token=csrf-abc; path=/";
  waitForBackendMock.mockResolvedValue(true);
});

afterEach(() => {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  vi.unstubAllGlobals();
  waitForBackendMock.mockReset();
});

describe("refreshAccessToken", () => {
  it.each(TRANSIENT_FAILURES)("rejects (never 'no session') on %s", async (_label, failure) => {
    stubBackend(failure);
    await expect(refreshAccessToken()).rejects.toBeDefined();
  });

  it("resolves null only for the backend's own 401", async () => {
    stubBackend(() => Promise.resolve(jsonResponse(401, errorBody("unauthenticated"))));
    await expect(refreshAccessToken()).resolves.toBeNull();
  });
});

describe("restoreSession", () => {
  it("never calls refresh while the backend is unreachable", async () => {
    waitForBackendMock.mockResolvedValue(false);
    const backend = stubBackend(() => Promise.resolve(jsonResponse(200, SESSION)));

    await expect(restoreSession()).rejects.toThrow(/could not be reached/);
    expect(backend.refreshCalls()).toHaveLength(0);
  });

  it("refreshes only after the backend is up, and restores the session", async () => {
    const backend = stubBackend(() => Promise.resolve(jsonResponse(200, SESSION)));

    await expect(restoreSession()).resolves.toMatchObject({ access_token: "t1" });
    expect(waitForBackendMock).toHaveBeenCalledTimes(1);
    expect(backend.refreshCalls()).toHaveLength(1);
  });

  it.each(TRANSIENT_FAILURES)(
    "does not retry refresh after %s - a replayed rotated token would revoke every session",
    async (_label, failure) => {
      const backend = stubBackend(failure);

      await expect(restoreSession()).rejects.toBeDefined();
      expect(backend.refreshCalls()).toHaveLength(1);
    }
  );

  it("resolves null for a genuinely invalid session", async () => {
    stubBackend(() => Promise.resolve(jsonResponse(401, errorBody("unauthenticated"))));
    await expect(restoreSession()).resolves.toBeNull();
  });

  it("does nothing at all without a session cookie", async () => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    const backend = stubBackend(() => Promise.resolve(jsonResponse(200, SESSION)));

    await expect(restoreSession()).resolves.toBeNull();
    expect(waitForBackendMock).not.toHaveBeenCalled();
    expect(backend.fetchMock).not.toHaveBeenCalled();
  });
});

describe("AuthProvider session restore", () => {
  it("reports an unreachable server instead of signing out, then recovers on retry", async () => {
    waitForBackendMock.mockResolvedValueOnce(false);
    const backend = stubBackend(() => Promise.resolve(jsonResponse(200, SESSION)));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    expect(await screen.findByText("signed out [unreachable]")).toBeInTheDocument();
    expect(backend.refreshCalls()).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("signed in:t1")).toBeInTheDocument();
    expect(backend.refreshCalls()).toHaveLength(1);
  });

  it("reports a transient refresh failure as unreachable, not as an expired session", async () => {
    stubBackend(() => Promise.resolve(new Response("<html>502</html>", { status: 502 })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByText("signed out [unreachable]")).toBeInTheDocument();
  });

  it("signs out normally when the server rejects the session", async () => {
    stubBackend(() => Promise.resolve(jsonResponse(401, errorBody("unauthenticated"))));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByText("signed out")).toBeInTheDocument();
  });

  it("explains a slow restore while the backend is still waking up", async () => {
    let backendUp: (ready: boolean) => void = () => {};
    waitForBackendMock.mockReturnValue(new Promise((resolve) => (backendUp = resolve)));
    stubBackend(() => Promise.resolve(jsonResponse(200, SESSION)));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(await screen.findByText("loading [waking]", {}, { timeout: 5_000 })).toBeInTheDocument();

    await act(async () => backendUp(true));
    expect(await screen.findByText("signed in:t1")).toBeInTheDocument();
  });

  it("keeps a signed-in user signed in when a mid-session refresh fails transiently", async () => {
    let refreshCount = 0;
    stubBackend(
      () => {
        refreshCount += 1;
        return refreshCount === 1
          ? Promise.resolve(jsonResponse(200, SESSION))
          : Promise.resolve(new Response("<html>504</html>", { status: 504 }));
      },
      () => Promise.resolve(jsonResponse(401, errorBody("unauthenticated")))
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByText("signed in:t1");

    let requestError: unknown;
    await act(async () => {
      requestError = await apiRequest("/api/v1/accounts", { accessToken: "t1" }).catch(
        (err: unknown) => err
      );
    });

    expect(requestError).toBeInstanceOf(Error);
    expect(screen.getByText("signed in:t1")).toBeInTheDocument();
  });
});
