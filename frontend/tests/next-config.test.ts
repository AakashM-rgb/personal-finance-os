import { describe, expect, it } from "vitest";

import { buildNextConfig, resolveBackendOrigin, resolveClientApiBaseUrl } from "@/next.config";

const BACKEND = "https://personal-finance-os-ug9o.onrender.com";

describe("resolveBackendOrigin", () => {
  it("is off when BACKEND_ORIGIN is unset or blank", () => {
    expect(resolveBackendOrigin({})).toBeNull();
    expect(resolveBackendOrigin({ BACKEND_ORIGIN: "   " })).toBeNull();
  });

  it("normalizes a valid https origin, including a trailing slash", () => {
    expect(resolveBackendOrigin({ BACKEND_ORIGIN: `${BACKEND}/` })).toBe(BACKEND);
    expect(resolveBackendOrigin({ BACKEND_ORIGIN: ` ${BACKEND} ` })).toBe(BACKEND);
  });

  it("allows plain http only for a local backend", () => {
    expect(resolveBackendOrigin({ BACKEND_ORIGIN: "http://localhost:8000" })).toBe(
      "http://localhost:8000"
    );
    expect(() => resolveBackendOrigin({ BACKEND_ORIGIN: "http://api.example.com" })).toThrow(
      /https/
    );
  });

  it.each([
    ["not a URL", "personal-finance-os-ug9o.onrender.com"],
    ["a path", `${BACKEND}/api/v1`],
    ["a query", `${BACKEND}?x=1`],
    ["a fragment", `${BACKEND}#x`],
    ["credentials", "https://user:pass@api.example.com"],
    ["a non-http scheme", "ftp://api.example.com"],
  ])("rejects an origin with %s", (_label, value) => {
    expect(() => resolveBackendOrigin({ BACKEND_ORIGIN: value })).toThrow(/BACKEND_ORIGIN/);
  });

  it("never echoes the raw value in its error (it may contain credentials)", () => {
    expect(() => resolveBackendOrigin({ BACKEND_ORIGIN: "https://user:hunter2@x.com" })).toThrow(
      expect.objectContaining({ message: expect.not.stringContaining("hunter2") })
    );
  });

  it.each([
    ["VERCEL_URL", "personal-finance-os-abc123.vercel.app"],
    ["VERCEL_BRANCH_URL", "personal-finance-os-git-main.vercel.app"],
    ["VERCEL_PROJECT_PRODUCTION_URL", "personal-finance-os-six-sandy.vercel.app"],
  ])("rejects proxying to this deployment itself (%s) - a rewrite loop", (key, host) => {
    expect(() => resolveBackendOrigin({ BACKEND_ORIGIN: `https://${host}`, [key]: host })).toThrow(
      /loop/
    );
  });

  it("rejects proxying to the local frontend server's own port", () => {
    expect(() => resolveBackendOrigin({ BACKEND_ORIGIN: "http://localhost:3000" })).toThrow(/loop/);
    expect(() =>
      resolveBackendOrigin({ BACKEND_ORIGIN: "http://localhost:3100", PORT: "3100" })
    ).toThrow(/loop/);
  });
});

describe("resolveClientApiBaseUrl", () => {
  it("makes browser requests same-origin (relative) when the proxy is on", () => {
    expect(resolveClientApiBaseUrl({}, BACKEND)).toBe("");
  });

  it("refuses a direct API URL alongside the proxy - it would bypass it", () => {
    expect(() =>
      resolveClientApiBaseUrl({ NEXT_PUBLIC_API_URL: BACKEND }, BACKEND)
    ).toThrow(/not both/);
  });

  it("keeps local development's direct mode unchanged without the proxy", () => {
    expect(resolveClientApiBaseUrl({}, null)).toBe("http://localhost:8000");
    expect(resolveClientApiBaseUrl({ NEXT_PUBLIC_API_URL: "http://localhost:9000" }, null)).toBe(
      "http://localhost:9000"
    );
  });
});

describe("buildNextConfig", () => {
  it("proxies /api/* to the backend's /api/* and marks it uncacheable", async () => {
    const config = buildNextConfig({ BACKEND_ORIGIN: BACKEND });

    expect(config.env).toEqual({ CLIENT_API_BASE_URL: "" });
    expect(await config.rewrites!()).toEqual([
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
    ]);
    expect(await config.headers!()).toEqual([
      {
        source: "/api/:path*",
        headers: [{ key: "Cache-Control", value: "private, no-store" }],
      },
    ]);
  });

  it("adds no rewrite or header without BACKEND_ORIGIN (local dev)", async () => {
    const config = buildNextConfig({ NEXT_PUBLIC_API_URL: "http://localhost:8000" });

    expect(config.env).toEqual({ CLIENT_API_BASE_URL: "http://localhost:8000" });
    expect(await config.rewrites!()).toEqual([]);
    expect(await config.headers!()).toEqual([]);
  });
});
