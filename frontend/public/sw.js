/**
 * Application-shell service worker. Scope is deliberately narrow:
 *
 *  - Only GET requests are ever intercepted. POST/PUT/PATCH/DELETE always
 *    go straight to the network, untouched - a mutating financial request
 *    (create/update/delete a transaction, login, refresh, ...) must never
 *    be served from or written into a cache.
 *  - Any request whose path starts with "/api/" is NEVER cached, even if
 *    the backend is later proxied same-origin - this is what stops an
 *    authenticated financial API response from ever being written to a
 *    cache that a later, different signed-in user on the same device
 *    could read from.
 *  - Cross-origin requests are left completely alone (not intercepted at
 *    all) - in the common dev/prod setup the backend API lives on a
 *    different origin than the frontend, so this alone already excludes
 *    it; the "/api/" check above is the second, same-origin-safe layer.
 *  - Only same-origin static build assets (/_next/static/..., /icons/...,
 *    the manifest, the favicon) and the offline fallback shell are ever
 *    written to the cache. There is no attempt to precache the full,
 *    content-hashed Next.js bundle - that requires build-time tooling
 *    this project doesn't have installed; what's cached here is the
 *    minimum needed to show a real offline shell instead of the browser's
 *    own "no internet" page.
 */

const CACHE_VERSION = "v1";
const SHELL_CACHE = `finance-app-shell-${CACHE_VERSION}`;
const STATIC_CACHE = `finance-app-static-${CACHE_VERSION}`;
const CURRENT_CACHES = new Set([SHELL_CACHE, STATIC_CACHE]);

const SHELL_URLS = [
  "/offline",
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/icons/icon-maskable.svg",
  "/favicon.ico",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Each URL cached independently - one 404 (e.g. no favicon in a
      // given environment) must never abort caching the rest of the shell.
      await Promise.all(
        SHELL_URLS.map((url) =>
          cache.add(url).catch(() => {
            /* best-effort precache only */
          })
        )
      );
      await self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => !CURRENT_CACHES.has(name)).map((name) => caches.delete(name))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") {
    void self.skipWaiting();
  }
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname === "/favicon.ico" ||
    url.pathname === "/manifest.webmanifest"
  );
}

async function networkFirstNavigation(request) {
  try {
    const response = await fetch(request);
    return response;
  } catch {
    const cache = await caches.open(SHELL_CACHE);
    const offline = await cache.match("/offline");
    return offline ?? Response.error();
  }
}

async function cacheFirstStatic(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  // Content-hashed/static assets are safe to cache long-term; only cache
  // genuinely successful responses, never an error page.
  if (response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // never intercept mutating requests

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // never touch cross-origin (the API)
  if (isApiRequest(url)) return; // never cache same-origin API responses either

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(cacheFirstStatic(request));
  }
  // Everything else: no interception, default network behavior.
});
