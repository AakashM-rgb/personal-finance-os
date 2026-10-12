import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiFetchBlob,
  apiRequest,
  setSessionRefresher,
} from "@/lib/api-client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const EXPIRED = {
  data: null,
  error: {
    code: "unauthenticated",
    message: "Invalid or expired session. Please log in again.",
    field_errors: null,
  },
  meta: null,
};

function authHeaderOf(call: unknown[]): string | undefined {
  const init = call[1] as RequestInit;
  return (init.headers as Record<string, string>).Authorization;
}

afterEach(() => {
  setSessionRefresher(null);
  vi.unstubAllGlobals();
});

describe("api-client session recovery", () => {
  it("refreshes once on a 401 and retries the request with the new token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, EXPIRED))
      .mockResolvedValueOnce(jsonResponse(200, { data: { ok: true }, error: null, meta: null }));
    vi.stubGlobal("fetch", fetchMock);
    const refresher = vi.fn().mockResolvedValue("fresh-token");
    setSessionRefresher(refresher);

    const result = await apiRequest<{ ok: boolean }>("/api/v1/accounts", {
      accessToken: "stale-token",
    });

    expect(result).toEqual({ ok: true });
    expect(refresher).toHaveBeenCalledWith("stale-token");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(authHeaderOf(fetchMock.mock.calls[0])).toBe("Bearer stale-token");
    expect(authHeaderOf(fetchMock.mock.calls[1])).toBe("Bearer fresh-token");
  });

  it("keeps the same Idempotency-Key on the retried write", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, EXPIRED))
      .mockResolvedValueOnce(jsonResponse(201, { data: { id: "t1" }, error: null, meta: null }));
    vi.stubGlobal("fetch", fetchMock);
    setSessionRefresher(vi.fn().mockResolvedValue("fresh-token"));

    await apiRequest("/api/v1/transactions", {
      method: "POST",
      accessToken: "stale-token",
      body: { amount_minor: 100 },
      idempotencyKey: "key-1",
    });

    for (const call of fetchMock.mock.calls) {
      const headers = (call[1] as RequestInit).headers as Record<string, string>;
      expect(headers["Idempotency-Key"]).toBe("key-1");
    }
  });

  it("surfaces the original 401 when the session can't be recovered - no retry, no loop", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, EXPIRED));
    vi.stubGlobal("fetch", fetchMock);
    const refresher = vi.fn().mockResolvedValue(null);
    setSessionRefresher(refresher);

    const error = await apiRequest("/api/v1/accounts", { accessToken: "stale-token" }).catch(
      (err: unknown) => err
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries at most once even if the retried request is also rejected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, EXPIRED));
    vi.stubGlobal("fetch", fetchMock);
    const refresher = vi.fn().mockResolvedValue("fresh-token");
    setSessionRefresher(refresher);

    await expect(apiRequest("/api/v1/accounts", { accessToken: "stale" })).rejects.toBeInstanceOf(
      ApiError
    );
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never tries to recover a 401 from an auth endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, EXPIRED));
    vi.stubGlobal("fetch", fetchMock);
    const refresher = vi.fn();
    setSessionRefresher(refresher);

    await expect(
      apiRequest("/api/v1/auth/logout-all", { method: "POST", accessToken: "stale" })
    ).rejects.toBeInstanceOf(ApiError);
    expect(refresher).not.toHaveBeenCalled();
  });

  it("does not attempt recovery for an unauthenticated request", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, EXPIRED)));
    const refresher = vi.fn();
    setSessionRefresher(refresher);

    await expect(apiRequest("/api/v1/accounts")).rejects.toBeInstanceOf(ApiError);
    expect(refresher).not.toHaveBeenCalled();
  });

  it("recovers blob downloads (receipt files, report exports) the same way", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, EXPIRED))
      .mockResolvedValueOnce(new Response("a,b\n1,2", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setSessionRefresher(vi.fn().mockResolvedValue("fresh-token"));

    const blob = await apiFetchBlob("/api/v1/reports/monthly/export?format=csv", "stale-token");

    expect(await blob.text()).toBe("a,b\n1,2");
    expect(authHeaderOf(fetchMock.mock.calls[1])).toBe("Bearer fresh-token");
  });
});

describe("api-client error shapes", () => {
  it("turns a JSON error body without an error envelope into a plain Error, not a crash", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(502, { detail: "bad gateway" })));

    const error = await apiRequest("/api/v1/accounts", { accessToken: "t" }).catch(
      (err: unknown) => err
    );

    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(ApiError);
  });
});

describe("api-client base URL (set at build time by next.config.ts)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  async function callEveryRequestKind(): Promise<ReturnType<typeof vi.fn>> {
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).endsWith("/file") ? new Response("blob") : jsonResponse(200, { data: null })
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = await import("@/lib/api-client");
    await client.apiRequest("/api/v1/auth/refresh", { method: "POST", csrfToken: "c" });
    await client.apiUpload("/api/v1/receipts/upload", new FormData(), { accessToken: "t" });
    await client.apiFetchBlob("/api/v1/receipts/r1/file", "t");
    return fetchMock;
  }

  it("keeps JSON, upload, and blob requests same-origin in proxy mode, with cookies included", async () => {
    vi.stubEnv("CLIENT_API_BASE_URL", "");
    const fetchMock = await callEveryRequestKind();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/refresh",
      "/api/v1/receipts/upload",
      "/api/v1/receipts/r1/file",
    ]);
    for (const [, init] of fetchMock.mock.calls) {
      expect((init as RequestInit).credentials).toBe("include");
    }
  });

  it("prefixes every request kind with the direct API origin in direct mode", async () => {
    vi.stubEnv("CLIENT_API_BASE_URL", "http://localhost:8000");
    const fetchMock = await callEveryRequestKind();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/v1/auth/refresh",
      "http://localhost:8000/api/v1/receipts/upload",
      "http://localhost:8000/api/v1/receipts/r1/file",
    ]);
  });
});
