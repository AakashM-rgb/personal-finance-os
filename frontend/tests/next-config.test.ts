import { describe, expect, it } from "vitest";

import {
  buildContentSecurityPolicy,
  buildNextConfig,
  buildSecurityHeaders,
  resolveBackendOrigin,
  resolveClientApiBaseUrl,
} from "@/next.config";

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
      { source: "/:path*", headers: buildSecurityHeaders({ BACKEND_ORIGIN: BACKEND }, BACKEND) },
      {
        source: "/api/:path*",
        headers: [{ key: "Cache-Control", value: "private, no-store" }],
      },
    ]);
  });

  it("adds no rewrite without BACKEND_ORIGIN (local dev), but still sends headers", async () => {
    const config = buildNextConfig({ NEXT_PUBLIC_API_URL: "http://localhost:8000" });

    expect(config.env).toEqual({ CLIENT_API_BASE_URL: "http://localhost:8000" });
    expect(await config.rewrites!()).toEqual([]);
    const headers = await config.headers!();
    expect(headers).toHaveLength(1);
    expect(headers[0].source).toBe("/:path*");
  });
});

// F-004: the app shipped with no security headers at all.
describe("buildSecurityHeaders", () => {
  const keysFor = (env: Record<string, string | undefined>, origin: string | null) =>
    buildSecurityHeaders(env, origin).map((header) => header.key);

  it("sends every baseline header on every route", () => {
    const keys = keysFor({ NODE_ENV: "production", BACKEND_ORIGIN: BACKEND }, BACKEND);

    expect(keys).toEqual(
      expect.arrayContaining([
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
      ])
    );
  });

  it("sends HSTS only in production, never from a plain-http dev server", () => {
    expect(keysFor({ NODE_ENV: "production" }, BACKEND)).toContain("Strict-Transport-Security");
    expect(keysFor({ NODE_ENV: "development" }, null)).not.toContain("Strict-Transport-Security");
  });

  it("denies framing and sniffing outright", () => {
    const headers = buildSecurityHeaders({ NODE_ENV: "production" }, BACKEND);
    const byKey = Object.fromEntries(headers.map((h) => [h.key, h.value]));

    expect(byKey["X-Frame-Options"]).toBe("DENY");
    expect(byKey["X-Content-Type-Options"]).toBe("nosniff");
    expect(byKey["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
  });
});

describe("buildContentSecurityPolicy", () => {
  const directives = (policy: string) =>
    Object.fromEntries(
      policy.split("; ").map((directive) => {
        const [name, ...values] = directive.split(" ");
        return [name, values.join(" ")];
      })
    );

  it("locks down the dangerous sinks", () => {
    const d = directives(buildContentSecurityPolicy({ NODE_ENV: "production" }, BACKEND));

    expect(d["default-src"]).toBe("'self'");
    expect(d["object-src"]).toBe("'none'");
    expect(d["frame-ancestors"]).toBe("'none'");
    expect(d["base-uri"]).toBe("'self'");
    expect(d["form-action"]).toBe("'self'");
  });

  it("keeps the proxy deployment's connect-src same-origin only", () => {
    const d = directives(buildContentSecurityPolicy({ NODE_ENV: "production" }, BACKEND));

    expect(d["connect-src"]).toBe("'self'");
  });

  it("allows the backend in connect-src when the browser calls it directly", () => {
    const policy = buildContentSecurityPolicy(
      { NODE_ENV: "production", NEXT_PUBLIC_API_URL: BACKEND },
      null
    );

    expect(directives(policy)["connect-src"]).toBe(`'self' ${BACKEND}`);
  });

  it("never allows eval in a production build", () => {
    const production = buildContentSecurityPolicy({ NODE_ENV: "production" }, BACKEND);
    const development = buildContentSecurityPolicy({ NODE_ENV: "development" }, null);

    expect(production).not.toContain("'unsafe-eval'");
    expect(production).toContain("upgrade-insecure-requests");
    expect(development).toContain("'unsafe-eval'");
  });
});
