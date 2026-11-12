import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "@/lib/api-client";
import { AuthProvider, refreshAccessToken, useAuth } from "@/lib/auth-context";

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

function sessionBody(token: string) {
  return {
    data: { access_token: token, token_type: "bearer", expires_in: 900, user: USER },
    error: null,
    meta: null,
  };
}

const UNAUTHENTICATED = {
  data: null,
  error: { code: "unauthenticated", message: "Invalid or expired session.", field_errors: null },
  meta: null,
};

const HEALTHY = { data: { status: "ok" }, error: null, meta: null };

const SETTINGS = {
  data: { theme: "system" },
  error: null,
  meta: null,
};

function urlOf(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input.toString();
}

function Probe() {
  const auth = useAuth();
  return (
    <>
      <p>
        {auth.isLoading ? "loading" : auth.user ? `signed in:${auth.accessToken}` : "signed out"}
        {auth.sessionExpired ? " (expired)" : ""}
      </p>
      <button type="button" onClick={() => void auth.logout()}>
        Log out
      </button>
    </>
  );
}

beforeEach(() => {
  document.cookie = "csrf_token=csrf-abc; path=/";
});

afterEach(() => {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  vi.unstubAllGlobals();
});

describe("refreshAccessToken", () => {
  it("shares one in-flight request between concurrent callers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, sessionBody("t1")));
    vi.stubGlobal("fetch", fetchMock);

    const [a, b] = await Promise.all([refreshAccessToken(), refreshAccessToken()]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a?.access_token).toBe("t1");
    expect(b?.access_token).toBe("t1");
  });

  it("resolves null (no session) when the server rejects the refresh", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, UNAUTHENTICATED)));
    await expect(refreshAccessToken()).resolves.toBeNull();
  });

  it("posts same-origin with cookies included and the CSRF cookie echoed as a header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, sessionBody("t1")));
    vi.stubGlobal("fetch", fetchMock);

    await refreshAccessToken();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    // Relative: through the frontend's own /api/* proxy, never the backend's origin.
    expect(url).toBe("/api/v1/auth/refresh");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["x-csrf-token"]).toBe("csrf-abc");
  });

  it("makes no request at all without a CSRF cookie", async () => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(refreshAccessToken()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("AuthProvider", () => {
  it("restores the session with a single refresh even under Strict Mode's double mount", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        urlOf(input).endsWith("/auth/refresh")
          ? jsonResponse(200, sessionBody("t1"))
          : jsonResponse(200, SETTINGS)
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrictMode>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </StrictMode>
    );

    expect(await screen.findByText("signed in:t1")).toBeInTheDocument();
    const refreshCalls = fetchMock.mock.calls.filter(([input]) =>
      urlOf(input).endsWith("/auth/refresh")
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it("transparently swaps in a new token when a request hits an expired one", async () => {
    let refreshCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = urlOf(input);
        if (url.endsWith("/auth/refresh")) {
          refreshCount += 1;
          return Promise.resolve(jsonResponse(200, sessionBody(`t${refreshCount}`)));
        }
        if (url.endsWith("/health")) return Promise.resolve(jsonResponse(200, HEALTHY));
      if (url.endsWith("/settings")) return Promise.resolve(jsonResponse(200, SETTINGS));
        const auth = (init?.headers as Record<string, string>).Authorization;
        return Promise.resolve(
          auth === "Bearer t2"
            ? jsonResponse(200, { data: [], error: null, meta: null })
            : jsonResponse(401, UNAUTHENTICATED)
        );
      })
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByText("signed in:t1");

    // Two requests expire at once - they must share a single refresh.
    let results: unknown[] = [];
    await act(async () => {
      results = await Promise.all([
        apiRequest("/api/v1/accounts", { accessToken: "t1" }),
        apiRequest("/api/v1/categories", { accessToken: "t1" }),
      ]);
    });

    expect(results).toEqual([[], []]);
    expect(refreshCount).toBe(2); // the mount restore + exactly one recovery
    expect(screen.getByText("signed in:t2")).toBeInTheDocument();
  });

  it("signs out and flags the session as expired when it can't be refreshed", async () => {
    let refreshCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = urlOf(input);
        if (url.endsWith("/auth/refresh")) {
          refreshCount += 1;
          return Promise.resolve(
            refreshCount === 1
              ? jsonResponse(200, sessionBody("t1"))
              : jsonResponse(401, UNAUTHENTICATED)
          );
        }
        if (url.endsWith("/health")) return Promise.resolve(jsonResponse(200, HEALTHY));
      if (url.endsWith("/settings")) return Promise.resolve(jsonResponse(200, SETTINGS));
        return Promise.resolve(jsonResponse(401, UNAUTHENTICATED));
      })
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByText("signed in:t1");

    await act(async () => {
      await apiRequest("/api/v1/accounts", { accessToken: "t1" }).catch(() => {});
    });

    await waitFor(() => expect(screen.getByText("signed out (expired)")).toBeInTheDocument());
  });

  it("survives a page reload after login: the remount restores the session", async () => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/auth/login")) {
        // What the backend's Set-Cookie does once the proxy makes it first-party.
        document.cookie = "csrf_token=csrf-after-login; path=/";
        return Promise.resolve(jsonResponse(200, sessionBody("t-login")));
      }
      if (url.endsWith("/auth/refresh")) return Promise.resolve(jsonResponse(200, sessionBody("t-reload")));
      return Promise.resolve(jsonResponse(200, SETTINGS));
    });
    vi.stubGlobal("fetch", fetchMock);

    function LoginProbe() {
      const auth = useAuth();
      return (
        <>
          <Probe />
          <button type="button" onClick={() => void auth.login({ email: "a@b.com", password: "pw" })}>
            Log in
          </button>
        </>
      );
    }

    const firstVisit = render(
      <AuthProvider>
        <LoginProbe />
      </AuthProvider>
    );
    expect(await screen.findByText("signed out")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("signed in:t-login")).toBeInTheDocument();

    // Reload: in-memory state (the access token) is gone; only cookies remain.
    firstVisit.unmount();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByText("signed in:t-reload")).toBeInTheDocument();
    const refreshCalls = fetchMock.mock.calls.filter(([input]) =>
      urlOf(input).endsWith("/auth/refresh")
    );
    expect(refreshCalls).toHaveLength(1);
    const [, init] = refreshCalls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["x-csrf-token"]).toBe("csrf-after-login");
  });

  it("logs out same-origin with cookies included and the CSRF header", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/auth/refresh")) return Promise.resolve(jsonResponse(200, sessionBody("t1")));
      if (url.endsWith("/health")) return Promise.resolve(jsonResponse(200, HEALTHY));
      if (url.endsWith("/settings")) return Promise.resolve(jsonResponse(200, SETTINGS));
      return Promise.resolve(jsonResponse(200, { data: { success: true }, error: null, meta: null }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByText("signed in:t1");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await screen.findByText("signed out");

    const logoutCall = fetchMock.mock.calls.find(([input]) => urlOf(input).endsWith("/auth/logout"));
    expect(logoutCall).toBeDefined();
    const [url, init] = logoutCall as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/logout");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["x-csrf-token"]).toBe("csrf-abc");
  });

  it("does not flag an explicit logout as an expired session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = urlOf(input);
        if (url.endsWith("/auth/refresh")) return Promise.resolve(jsonResponse(200, sessionBody("t1")));
        if (url.endsWith("/health")) return Promise.resolve(jsonResponse(200, HEALTHY));
      if (url.endsWith("/settings")) return Promise.resolve(jsonResponse(200, SETTINGS));
        return Promise.resolve(jsonResponse(200, { data: null, error: null, meta: null }));
      })
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByText("signed in:t1");

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByText("signed out")).toBeInTheDocument();
  });

  it("adopts the fresh session returned by change-password and stays signed in", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/auth/refresh")) return Promise.resolve(jsonResponse(200, sessionBody("t1")));
      if (url.endsWith("/auth/change-password")) {
        return Promise.resolve(jsonResponse(200, sessionBody("t2")));
      }
      if (url.endsWith("/health")) return Promise.resolve(jsonResponse(200, HEALTHY));
      return Promise.resolve(jsonResponse(200, SETTINGS));
    });
    vi.stubGlobal("fetch", fetchMock);

    function ChangePasswordProbe() {
      const auth = useAuth();
      return (
        <>
          <Probe />
          <button
            type="button"
            onClick={() =>
              void auth.changePassword({
                current_password: "old-pass-1",
                new_password: "new-pass-2",
                confirm_password: "new-pass-2",
              })
            }
          >
            Change
          </button>
        </>
      );
    }

    render(
      <AuthProvider>
        <ChangePasswordProbe />
      </AuthProvider>
    );
    await screen.findByText("signed in:t1");
    fireEvent.click(screen.getByRole("button", { name: "Change" }));

    expect(await screen.findByText("signed in:t2")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([input]) =>
      urlOf(input).endsWith("/auth/change-password")
    );
    const [, init] = call as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t1");
  });
});
