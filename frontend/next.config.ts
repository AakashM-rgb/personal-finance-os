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

/**
 * Security headers applied to every response.
 *
 * The app serves one user's financial data, so the defaults matter: without
 * these, Next.js sends no CSP, no HSTS, no framing or MIME protection at all.
 *
 * `connect-src` has to include the backend when the browser calls it
 * directly (no proxy); with the proxy on, every request is same-origin and
 * `'self'` already covers it.
 *
 * Known weakness, deliberately accepted: `script-src` allows
 * `'unsafe-inline'`. Next.js App Router streams its hydration payload through
 * inline `<script>` tags, and the stricter nonce-based policy is not
 * available to this app as built -- Next.js injects a nonce only during
 * server-side rendering, so (per its own CSP guide) "to use a nonce, your
 * page must be dynamically rendered". Every route here prerenders as static
 * content, which is why the build output lists them all as `○ (Static)`.
 * Earning a nonce would mean making all 22 routes dynamic: a real
 * architectural and performance trade-off, not a config tweak, and one to
 * decide deliberately rather than in a hardening pass. `'unsafe-inline'`
 * alongside `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`
 * and a locked-down `connect-src` is still far stronger than no policy at
 * all. `'unsafe-eval'` is dev-only (React Refresh needs it) and never set in
 * a production build.
 */
export function buildContentSecurityPolicy(
  env: BuildEnv,
  backendOrigin: string | null
): string {
  const isDev = env.NODE_ENV !== "production";
  const directApi = backendOrigin ? null : env.NEXT_PUBLIC_API_URL?.trim() || LOCAL_DEV_API_URL;
  const connect = ["'self'", directApi, isDev ? "ws://localhost:*" : null].filter(Boolean);
  const script = ["'self'", "'unsafe-inline'", isDev ? "'unsafe-eval'" : null].filter(Boolean);

  return [
    "default-src 'self'",
    `script-src ${script.join(" ")}`,
    // Tailwind injects a stylesheet; Next.js also inlines critical CSS.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src ${connect.join(" ")}`,
    // Receipts are rendered from blob: URLs the app itself creates.
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

export function buildSecurityHeaders(
  env: BuildEnv,
  backendOrigin: string | null
): { key: string; value: string }[] {
  const headers = [
    { key: "Content-Security-Policy", value: buildContentSecurityPolicy(env, backendOrigin) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    // Redundant with frame-ancestors above, kept for older browsers.
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    {
      key: "Permissions-Policy",
      value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    { key: "X-DNS-Prefetch-Control", value: "off" },
  ];
  // HSTS only where the site is actually served over TLS: sending it from a
  // plain-http dev server would pin localhost to https in the browser.
  if (env.NODE_ENV === "production") {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=63072000; includeSubDomains",
    });
  }
  return headers;
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
      const headers = [
        { source: "/:path*", headers: buildSecurityHeaders(env, backendOrigin) },
      ];
      if (!backendOrigin) return headers;
      // Proxied responses carry one user's financial data and auth cookies;
      // a shared CDN cache in front of them must never store or replay one.
      return [
        ...headers,
        {
          source: "/api/:path*",
          headers: [{ key: "Cache-Control", value: "private, no-store" }],
        },
      ];
    },
  };
}

export default buildNextConfig(process.env);
