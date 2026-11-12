import type { NextConfig } from "next";

// Kept self-contained (no imports from lib/): Next.js loads next.config.ts
// through its own restricted module resolution, and these helpers are
// exported only so tests can exercise them without running a build.

type BuildEnv = Record<string, string | undefined>;

// `localhost`, never `127.0.0.1`: cookies are scoped per hostname, so this
// must match the frontend's own dev hostname or session restore silently
// fails (see .env.example).
const LOCAL_DEV_API_URL = "http://localhost:8000";
const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]"]);
const DEFAULT_FRONTEND_PORT = "3000";

/**
 * The backend that `/api/*` is reverse-proxied to, or null when the proxy is
 * off (local dev, where the browser calls NEXT_PUBLIC_API_URL directly).
 *
 * The proxy exists so the browser only ever talks to the frontend's own
 * origin: the refresh and CSRF cookies are then first-party, readable by
 * this app's JavaScript, and sent on reload (see docs/DEPLOYMENT.md).
 * Error messages never echo the raw value - it could carry credentials if
 * mistyped.
 */
export function resolveBackendOrigin(env: BuildEnv): string | null {
  const raw = env.BACKEND_ORIGIN?.trim();
  if (!raw) return null;

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(
      "BACKEND_ORIGIN must be an absolute origin such as https://api.example.com."
    );
  }

  const isLocal = LOCAL_HOSTNAMES.has(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && isLocal)) {
    throw new Error("BACKEND_ORIGIN must use https:// (http:// is allowed only for localhost).");
  }
  if (url.username || url.password) {
    throw new Error("BACKEND_ORIGIN must not contain credentials.");
  }
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new Error(
      "BACKEND_ORIGIN must be scheme and host only - no path (not even /api/v1), query, or fragment."
    );
  }

  // Proxying to this deployment itself would make every /api/* request
  // re-enter the same rewrite forever.
  const ownHostnames = [env.VERCEL_URL, env.VERCEL_BRANCH_URL, env.VERCEL_PROJECT_PRODUCTION_URL]
    .filter((host): host is string => Boolean(host))
    .map((host) => host.toLowerCase());
  const backendPort = url.port || (url.protocol === "https:" ? "443" : "80");
  const isOwnLocalServer =
    isLocal && backendPort === (env.PORT?.trim() || DEFAULT_FRONTEND_PORT);
  if (ownHostnames.includes(url.hostname) || isOwnLocalServer) {
    throw new Error("BACKEND_ORIGIN points at this frontend itself, which would loop forever.");
  }

  return url.origin;
}

/**
 * The base URL the browser prefixes every `/api/v1/...` request with. Empty
 * (same-origin, relative) whenever the proxy is on. Setting both variables
 * is rejected rather than resolved silently: the browser would bypass the
 * proxy and lose its session on every reload again.
 */
export function resolveClientApiBaseUrl(env: BuildEnv, backendOrigin: string | null): string {
  const directApiUrl = env.NEXT_PUBLIC_API_URL?.trim();
  if (backendOrigin) {
    if (directApiUrl) {
      throw new Error(
        "Set BACKEND_ORIGIN (same-origin proxy) or NEXT_PUBLIC_API_URL (direct calls), not both."
      );
    }
    return "";
  }
  return directApiUrl || LOCAL_DEV_API_URL;
}

export function buildNextConfig(env: BuildEnv): NextConfig {
  const backendOrigin = resolveBackendOrigin(env);

  return {
    env: {
      CLIENT_API_BASE_URL: resolveClientApiBaseUrl(env, backendOrigin),
    },
    async rewrites() {
      if (!backendOrigin) return [];
      return [{ source: "/api/:path*", destination: `${backendOrigin}/api/:path*` }];
    },
    async headers() {
      if (!backendOrigin) return [];
      // Proxied responses carry one user's financial data and auth cookies;
      // a shared CDN cache in front of them must never store or replay one.
      return [
        {
          source: "/api/:path*",
          headers: [{ key: "Cache-Control", value: "private, no-store" }],
        },
      ];
    },
  };
}

export default buildNextConfig(process.env);
