# Deployment (public staging)

How to run this repository as two separately deployed services plus a managed PostgreSQL
database. It isn't tied to any hosting provider. **Nothing has been deployed yet.** This is the
preparation guide, and every command in it was checked against the actual code (see
[Local production-like verification](#6-local-production-like-verification)).

Related: [ARCHITECTURE.md](ARCHITECTURE.md) · [DATABASE.md](DATABASE.md) ·
[ERROR_HANDLING.md](ERROR_HANDLING.md)

## 1. Architecture

```
Browser ──HTTPS──▶ Next.js frontend (frontend/)         public web app, static pages + client JS
   │
   └──HTTPS──▶ FastAPI backend (backend/)  /api/v1/...  JSON API, auth cookies
                      │
                      └──TLS──▶ Managed PostgreSQL        migrated with Alembic
```

All API calls are client-side `fetch` with `credentials: "include"`, through
`frontend/lib/api-client.ts`. Where they go is decided at **build time** by `next.config.ts`:

- **Direct mode** (`NEXT_PUBLIC_API_URL` set, or neither variable set in local dev): the browser
  calls the API origin directly.
- **Proxy mode** (`BACKEND_ORIGIN` set): the browser calls its own origin
  (`/api/v1/...`), and the frontend host reverse-proxies `/api/*` to `BACKEND_ORIGIN`. The
  browser never contacts the backend origin itself.

### Choosing domains (read this first)

Sessions are restored after a page reload through `POST /api/v1/auth/refresh`, which needs the
frontend's JavaScript to **read the `csrf_token` cookie** set by the API (a double-submit CSRF
check). So the frontend and API must be able to share cookies. That limits which domain layouts
work fully:

| Topology | Settings | Result |
|---|---|---|
| **A. Sibling subdomains of a domain you control** (recommended): `https://app.example.com` + `https://api.example.com` | `NEXT_PUBLIC_API_URL=https://api.example.com`, `CORS_ORIGINS=https://app.example.com`, `COOKIE_DOMAIN=example.com` | Everything works, including session restore on reload and logout. |
| **B. One public origin with path routing**: the frontend reverse-proxies `/api/*` to the backend (built in: set `BACKEND_ORIGIN`), so the browser sees one origin. Works with two unrelated platform domains, such as `*.vercel.app` + `*.onrender.com`; no custom domain needed. | Frontend: `BACKEND_ORIGIN=https://<backend host>`, `NEXT_PUBLIC_API_URL` **unset**. Backend: `COOKIE_DOMAIN` unset. | Everything works, including session restore on reload and logout. See [Vercel + Render](#vercel--render-same-origin-proxy). |
| **C. Two unrelated domains, called directly** (`NEXT_PUBLIC_API_URL` set to the other domain) | `COOKIE_DOMAIN` unset. It can't be set to another site's domain, and platform default domains are usually on the Public Suffix List. | **Broken session restore. Don't use; use B instead.** The cookies belong to the backend's domain, so the frontend's JavaScript can't read `csrf_token`, and `SameSite=Lax` keeps both cookies off cross-site requests. Login works in the current tab, but **every full page reload or new tab signs the user out**, and logout can't revoke the server-side session. |

`COOKIE_DOMAIN` broadens the cookies to every subdomain of that domain. Only use it with a
domain whose subdomains you fully control.

## 2. Frontend (`frontend/`)

| Item | Value |
|---|---|
| Runtime | Node.js **≥ 20.9** (Next.js 16's `engines` requirement; verified locally on 24.14) |
| Package manager | **npm** (`package-lock.json` is committed). Use `npm ci` for reproducible installs. |
| Install | `npm ci` |
| Build | `npm run build` (`next build`) |
| Start | `npm run start` (`next start`). It listens on `$PORT` (defaults to 3000). |
| Root directory | `frontend/` |

**Environment (build-time). Set exactly one of these; the build fails if both are set:**

| Variable | Topology | Value |
|---|---|---|
| `BACKEND_ORIGIN` | **B** (proxy) | The backend origin the frontend proxies `/api/*` to: `https://` + host only, no trailing slash, no `/api/v1`. Not public: read only by `next.config.ts`, never inlined into the browser bundle. |
| `NEXT_PUBLIC_API_URL` | A (direct) | The API origin the browser calls: scheme and host only, no trailing slash, no `/api/v1`, e.g. `https://api.example.com`. Public, inlined into the bundle. |

- Both are read at **build time**. Set them in the platform's build environment and **rebuild**
  after any change. Changing them without a rebuild has no effect.
- With neither set, the browser calls `http://localhost:8000` (local dev only), and a deployed
  site can't reach the API.
- `next.config.ts` validates `BACKEND_ORIGIN` and fails the build with a clear message if it
  isn't `https://`, has a path, query, fragment, or credentials, or points at the frontend's own
  deployment (`VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`), which would
  loop forever.
- **No variable other than `NEXT_PUBLIC_API_URL` may use the `NEXT_PUBLIC_` prefix**, and
  the frontend needs no secrets. (Verified: the production bundle contains no `JWT_SECRET`,
  `DATABASE_URL`, `ANTHROPIC_API_KEY`, or `SETU_SANDBOX` references.)

Other notes:

- Every route is static or client-rendered. There's no server-side data fetching, no Next.js API
  routes, and no `next/image` remote config, so any Node host that can run `next start` works.
- Error pages: `app/error.tsx`, `app/(app)/error.tsx`, `app/global-error.tsx`, and a custom
  `app/not-found.tsx` (a real 404 status).
- `public/sw.js` is a service worker that never caches `/api/` responses or mutating requests.
  That includes same-origin `/api/` requests in proxy mode. It needs HTTPS in production, which
  browsers require for service workers anyway.

### Vercel + Render (same-origin proxy)

This is topology B with the platforms' default domains, so no custom domain is needed:

```
Browser ──▶ https://<project>.vercel.app/dashboard           pages (Vercel)
        └─▶ https://<project>.vercel.app/api/v1/...  ──rewrite──▶  https://<service>.onrender.com/api/v1/...
```

**How it works.** With `BACKEND_ORIGIN` set, `next.config.ts` adds one rewrite,
`/api/:path*` → `${BACKEND_ORIGIN}/api/:path*`, and builds the client with an empty API base
URL, so every call in `lib/api-client.ts` is relative (`/api/v1/...`). That covers JSON calls,
auth, refresh, logout, receipt uploads, and blob downloads. The backend's `Set-Cookie` headers
pass through unchanged, so the browser stores the session cookies as **first-party, host-only**
cookies of the Vercel host:

- `refresh_token`: `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`. That path still matches
  the proxied auth URLs. JavaScript can't read it.
- `csrf_token`: `Secure; SameSite=Lax; Path=/`. Readable by the app's JavaScript, which echoes it
  in `X-CSRF-Token` for refresh and logout. The double-submit check is unchanged.

None of the backend's cookie flags change, and no cookie needs `SameSite=None`. CORS no longer
applies, because the browser makes only same-origin requests.

**Proxy behavior to know about:**

- **Caching:** the backend sends no `Cache-Control` header, so its responses aren't
  CDN-cacheable to begin with. As defense in depth, `next.config.ts` also declares
  `Cache-Control: private, no-store` for `/api/*`, and Vercel applies header rules at its edge.
  Self-hosted `next start` does **not** add config headers to externally proxied responses
  (verified locally), so check this on Vercel with step 1 below. If the header is missing there,
  the protection rests on the backend never sending a cacheable `Cache-Control`.
- **Forwarded headers:** the proxy passes the request's method, path, query, body, `Cookie`,
  and `X-CSRF-Token` through unchanged, and the response's `Set-Cookie` headers back unchanged.
  It rewrites `Host` to the backend's host and adds `X-Forwarded-Host`. Self-hosted
  `next start` forwards a client-supplied `X-Forwarded-For` as is (verified locally), which is
  why the backend must never trust it blindly (see below).
- **Redirects:** no API route the frontend calls returns a redirect. Next.js redirects a
  trailing-slash URL (`/api/v1/x/` → `/api/v1/x`, 308) before the rewrite runs. If the backend
  ever returned an absolute `Location` on the Render host, the browser would follow it
  cross-origin without the session cookies. It would fail visibly; it can't leak the session.
- **Cold starts:** a sleeping Render free instance can take tens of seconds to wake, and the
  proxy has its own upstream timeout, so a request after idle can fail with a gateway error.
  Session restore on page load handles this (`restoreSession` in `lib/auth-context.tsx`):
  1. It polls the side-effect-free `GET /api/v1/health` with backoff, for at most 60 seconds
     (`lib/backend-readiness.ts`). After 3 seconds the page says the server is waking up.
  2. Only once health answers does it send `POST /auth/refresh`, **exactly once**. It's never
     retried automatically. If an earlier refresh's response were lost in transit, the backend
     would already have rotated the token, and resending the old one would trip reuse detection
     and revoke every session.
  3. Only the backend's own 401 counts as "no session" and leads to the login page. A network
     failure, a gateway error, a 5xx, a 429, or a health budget that runs out shows "We couldn't
     reach the server" with **Try again** and **Go to sign in**. It never signs the user out.
  4. Mid-session, a failed refresh after a 401 also signs the user out only on a real 401.
     Otherwise that one request fails and the session stays.
- **Upload size:** receipts are capped at 10 MB by the backend. Verify after deploy that an
  upload close to that size passes through the proxy (see the checklist below).
- **Client IP and rate limiting:** see [Client IP behind the proxy](#client-ip-behind-the-proxy).

**Exact settings:**

| Where | Variable | Value |
|---|---|---|
| Vercel (Production; Preview too if used) | `BACKEND_ORIGIN` | `https://personal-finance-os-ug9o.onrender.com` |
| Vercel | `NEXT_PUBLIC_API_URL` | **Delete it.** If both are set, the build fails on purpose. |
| Render | `COOKIE_DOMAIN` | Unset (unchanged). |
| Render | `CORS_ORIGINS` | Keep `https://personal-finance-os-six-sandy.vercel.app`. It's still required at startup, and it's harmless because the browser no longer makes cross-origin calls. |
| Render | `ENVIRONMENT` | `production` (unchanged; keeps the cookies `Secure`). |

**Redeploy, in this order:**

1. **Backend first.** Run `alembic upgrade head` against the Render database. It adds the
   `login_failures` table, and the new code's login endpoint needs it. Then deploy the
   backend. The migration is additive, so the old backend keeps working if it runs first.
2. **Frontend.** Change the two Vercel variables, then trigger a **new build**: use "Redeploy"
   without the build cache, or push a commit. An old build keeps the old inlined API URL.
3. Run the [proxy verification](#proxy-verification-after-deploy) checks.

#### Proxy verification after deploy

Use a fresh browser profile or a private window (stale cookies from the old Render-domain setup
don't matter, but a clean profile makes the checks unambiguous):

1. `curl -sI https://<frontend>/api/v1/health` returns `200`, with `cache-control: private,
   no-store` and the backend's `x-content-type-options: nosniff`. This proves the rewrite
   reaches Render.
2. Log in. In DevTools → Network, the login request goes to `https://<frontend>/api/v1/auth/login`
   (not `onrender.com`). In DevTools → Application → Cookies, for the **Vercel** host,
   `refresh_token` has HttpOnly, Secure, Lax, and path `/api/v1/auth`, and `csrf_token` has
   Secure, Lax, and path `/`.
3. **Hard-reload `/dashboard`.** You stay signed in, and the network log shows exactly one
   `POST /api/v1/auth/refresh` with status `200` and an `x-csrf-token` request header.
4. Open `/transactions` in a **new tab**. You're signed in there too.
5. Filter Network by `onrender.com`. There should be **no** requests.
6. Upload a receipt (try one close to 10 MB), then open it. Both work.
7. Settings → Security lists this session. Log out, reload, and you're on the login page. Log in
   on a second browser, choose "Log out of all devices", then reload the first browser. It's
   signed out.
8. Wait more than 15 minutes (the access token lifetime), then click around. The app refreshes
   silently and doesn't send you to the login page.
9. In the Render logs, confirm that login requests show **your** public IP, not a Vercel IP
   (see the next section).
10. **Cold start:** let the Render instance go to sleep (about 15 idle minutes on the free plan),
    then reload `/dashboard`. You see "Loading your account…", then "Waking up the server…",
    and you end up signed in. You're **not** sent to the login page. Network shows repeated
    `GET /api/v1/health` and then exactly **one** `POST /api/v1/auth/refresh`.
11. **Per-account throttle:** with a throwaway account, enter a wrong password 10 times, then the
    right one. You get "Too many failed sign-in attempts…". Do the same with an email that has
    no account: the messages are identical. Don't test this on an account you need in the next
    15 minutes.

## 3. Backend (`backend/`)

| Item | Value |
|---|---|
| Runtime | Python **≥ 3.11** (`requires-python`; verified locally on 3.13) |
| Install | `pip install .` from `backend/`. Add `".[ai]"` only if `ANTHROPIC_API_KEY` is set, and `".[s3]"` only if `S3_BUCKET` is set. |
| App module | `app.main:app` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers` (working directory `backend/`) |
| Workers | **1** (see below) |
| Root directory | `backend/` (Alembic and the app both expect it as the working directory) |

**Start command details:**

- `--port $PORT`: nothing in the code hard-codes a port. The platform supplies `$PORT`.
- `--proxy-headers`, plus the environment variable `FORWARDED_ALLOW_IPS=*`: behind a platform
  load balancer, this makes uvicorn trust `X-Forwarded-For` and `X-Forwarded-Proto`. Without it,
  every request appears to come from the proxy's IP, so all users share **one** login and
  registration rate limit (5/minute), and audit logs record the proxy IP. `*` is only safe when
  the backend can be reached **only** through the platform's proxy (the normal PaaS setup).
  Otherwise, set it to the proxy's IP or range. (uvicorn reads `FORWARDED_ALLOW_IPS` itself; the
  app doesn't.)
- **Client IP trust:** with `FORWARDED_ALLOW_IPS=*`, uvicorn (0.53) takes the **left-most**
  `X-Forwarded-For` entry as the client IP, and the caller controls that entry. See
  [Client IP behind the proxy](#client-ip-behind-the-proxy).
- **One worker:** the per-IP rate limits are kept in process memory (slowapi's default
  storage). With several workers or instances, each keeps its own counters, so the effective
  limit multiplies, and every restart resets them. One worker is enough for staging. Before
  scaling out, back slowapi with a shared store: Redis, through `Limiter(storage_uri=...)`.
  The per-account login throttle is not affected: it's stored in PostgreSQL.

There are **no startup side effects**: no `create_all`, no seeding, no background scheduler, no
WebSockets. Settings are loaded at import, and a missing or invalid required variable stops the
process immediately with a validation error. There's no fallback to defaults.

**Logging:** application loggers (`app.*`) write to stdout/stderr, which the platform captures.
Unhandled exceptions are logged with a traceback server-side, and the client only receives a
generic `internal_error` envelope.

### Backend environment variables

Set these in the platform's secret/environment settings, never in a committed file. The full
annotated template is `backend/.env.example`.

| Variable | Required | Staging value / notes |
|---|---|---|
| `ENVIRONMENT` | yes | **`production`**, including for staging. This is what turns on `Secure` cookies and HSTS; any other value leaves both off. |
| `DATABASE_URL` | yes | `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB?ssl=require`. See [Database](#4-database) for the required format. |
| `TEST_DATABASE_URL` | yes | The settings loader requires it, but the running app never uses it. Set a placeholder such as `postgresql+asyncpg://unused:unused@unused.invalid:5432/unused`. **Never** the staging database: the test suite deletes all users. |
| `JWT_SECRET_KEY` | yes | A new random value of 32+ characters, used only for this environment (`python -c "import secrets; print(secrets.token_urlsafe(64))"`). |
| `JWT_ALGORITHM` | yes | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | yes | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | yes | `30` (or shorter for staging) |
| `CORS_ORIGINS` | yes | The exact frontend origin(s), comma-separated, e.g. `https://app.example.com`. No trailing slash, never `*`. |
| `LOGIN_RATE_LIMIT`, `REGISTER_RATE_LIMIT` | yes | `5/minute` (per client IP) |
| `LOGIN_ACCOUNT_MAX_FAILURES`, `LOGIN_ACCOUNT_WINDOW_MINUTES` | no | Defaults `10` and `15`: the per-account login throttle. See [Client IP behind the proxy](#client-ip-behind-the-proxy). |
| `COOKIE_DOMAIN` | topology A only | The shared parent domain, e.g. `example.com`. Leave unset for B and C. |
| `FORWARDED_ALLOW_IPS` | recommended | `*` behind a platform proxy (read by uvicorn) |
| `REFRESH_RATE_LIMIT`, `AI_RATE_LIMIT`, `SEARCH_RATE_LIMIT`, `SYNC_LINK_RATE_LIMIT`, `SYNC_TRIGGER_RATE_LIMIT` | no | Defaults are fine |
| `SYNC_PROVIDER` | no | Leave the default, **`mock`**. See [Setu considerations](#9-setu-staging-and-qualification-considerations). |
| `ANTHROPIC_API_KEY`, `AI_MODEL` | no | Unset means the labeled mock AI provider |
| `RECEIPT_STORAGE_DIR`, `S3_BUCKET`, `S3_REGION`, `OCR_PROVIDER` | no | See [File storage](#file-storage-receipts) |
| `SETU_SANDBOX_BASE_URL`, `SETU_SANDBOX_CLIENT_ID`, `SETU_SANDBOX_CLIENT_SECRET` | no | Leave unset. The code doesn't use them yet. |

### CORS

`CORSMiddleware` allows exactly the origins in `CORS_ORIGINS`, with `allow_credentials=True`.
Browsers reject `*` together with credentials, and the auth cookies need credentials, so list
each real frontend origin exactly. Verified locally: a preflight from the configured origin gets
`access-control-allow-origin` and `allow-credentials: true`, while a preflight from any other
origin gets HTTP 400 with no CORS headers.

### HTTPS and cookies

TLS is terminated by the platform. With `ENVIRONMENT=production`:

- The refresh cookie (`httpOnly`, `Path=/api/v1/auth`) and the CSRF cookie (`Path=/`) are sent
  `Secure; SameSite=Lax`.
- The API adds `Strict-Transport-Security: max-age=63072000; includeSubDomains`, plus the
  always-on `nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy` headers.

The access token is returned in the JSON body and kept only in browser memory.

### Client IP behind the proxy

Login, registration, refresh, and webhook rate limits are keyed by client IP
(`slowapi.get_remote_address`, which is `request.client.host`). Sessions and audit logs record
the same IP. In topology B, every proxied request reaches the backend from the frontend host's
egress IP, so the real client IP is only available from `X-Forwarded-For`:

- **What has to hold:** the frontend proxy must put the real client IP at the left of
  `X-Forwarded-For`, *overwriting* any client-supplied value, never appending to it. Confirm
  this after deploy with step 9 of the proxy verification. If Render logs show a Vercel IP
  instead, all users share one login bucket (5/minute). That's a denial-of-service on login, not
  a data leak.
- **Remaining limitation, already present before the proxy:** the backend's public URL is
  still reachable directly, bypassing the proxy. Because `FORWARDED_ALLOW_IPS=*` makes uvicorn
  trust the left-most entry, a direct caller can send an arbitrary `X-Forwarded-For` value on
  each request, get a fresh rate-limit bucket every time, and write a false IP into audit logs.
  Narrowing `FORWARDED_ALLOW_IPS` to the platform proxy's range doesn't help in topology B. The
  proxied traffic would then resolve to the frontend host's egress IPs, and every user would
  share one bucket.
- **Mitigation in place: a per-account login throttle** (`app/services/login_throttle.py`),
  alongside the per-IP limit. It's keyed by the account under attack, not by any header, so
  rotating or spoofing IPs no longer buys more guesses against one account:
  - After `LOGIN_ACCOUNT_MAX_FAILURES` (10) failed logins within `LOGIN_ACCOUNT_WINDOW_MINUTES`
    (15), that account refuses every attempt with a 429. That includes the correct password,
    or the throttle would confirm a guess.
  - The window slides, and refused attempts aren't counted, so the lock lifts on its own at
    most 15 minutes after the last counted failure. There's no permanent lockout.
  - A successful login clears the account's failures.
  - Unregistered emails are throttled identically, with the same 401 and 429 bodies, and an
    unknown email still pays for a full Argon2 verification. Neither the response nor its
    timing reveals whether an email is registered.
  - State lives in PostgreSQL (`login_failures`, which stores only an HMAC of the email). A
    per-account, non-blocking advisory lock (`pg_try_advisory_xact_lock`) keeps the count
    exact across workers, instances, and restarts. An attempt that overlaps another one on the
    same account gets the 429 right away instead of queueing, so a flood against one email
    can't hold database connections that every other user needs.
  - **Trade-off:** someone who knows a user's email can keep that account throttled by failing
    10 logins every 15 minutes. That's a nuisance denial of service; it can't let them in. If
    it happens, the fixes are a CAPTCHA or proof-of-work after a few failures, or trusted-device
    cookies that exempt a user's known browsers. None is implemented.
  - **Still IP-keyed and spoofable by direct callers:** registration, refresh, and webhook rate
    limits, and the IP recorded in audit logs and sessions.
- **Further mitigation (not yet made):**
  1. **Authenticate the proxy hop:** the frontend proxy adds a secret header that only it knows
     (set in both platforms' secret settings). The backend rejects requests without it, and
     trusts the forwarded client IP only from requests that carry it. That makes the backend
     unusable except through the frontend. It needs request-header injection at the proxy,
     which a plain `next.config.ts` rewrite can't do, so it means adding a Next.js `proxy.ts`.

### File storage (receipts)

`POST /api/v1/receipts/upload` stores files through `app/storage`:

- **Default:** the local filesystem at `RECEIPT_STORAGE_DIR` (`var/receipts`, relative to
  `backend/`). Most platforms give containers an **ephemeral disk**, so uploaded receipts are
  **lost on every restart or redeploy**, while their database rows remain, and reading the file
  afterwards returns an error. For staging, accept this as a limitation or attach a persistent
  volume at that path.
- **S3:** set `S3_BUCKET` and `S3_REGION`, install `".[s3]"`, and provide AWS credentials through
  boto3's standard environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
  **Not verified against a real bucket.**

The rest of the app writes nothing to disk.

## 4. Database

- **PostgreSQL** is required (the code uses `timestamptz`, partial unique indexes, `ARRAY`, and
  `date_trunc(..., 'UTC')`). There's no SQLite fallback. `DATABASE_URL` is required, and the app
  won't start without it.
- **Driver:** asyncpg. The URL **must** start with `postgresql+asyncpg://`, so rewrite a
  provider's `postgres://` or `postgresql://` scheme.
- **TLS:** use `?ssl=require`. **Don't use `?sslmode=require`**, which many providers print by
  default: SQLAlchemy passes it through to `asyncpg.connect()`, which has no `sslmode` parameter,
  so the connection fails.
- **Password characters:** percent-encode special characters (`@` → `%40`, `/` → `%2F`, `%` →
  `%25`). Both the app and Alembic accept percent-encoded passwords (`migrations/env.py` escapes
  `%` for Alembic's config parser).
- **Least privilege:** use an application role that owns the schema, not a superuser.
- **Pool:** SQLAlchemy's default async pool (size 5, overflow 10) with `pool_pre_ping=True`.
  That's at most 15 connections per worker, within a small managed plan.

**Migrations.** Alembic runs 15 linear revisions. The head is `5d7e1c2a9b30`. Run from `backend/`
with the staging `DATABASE_URL` in the environment:

```bash
cd backend
alembic upgrade head      # creates every table and seeds the 14 system categories
alembic current           # should print: 5d7e1c2a9b30 (head)
```

- On a fresh database this is the complete setup. On later deploys, the same command applies
  only the new revisions, so run it **before** starting the new backend version.
- `upgrade` never drops data. **Never run `alembic downgrade` against staging** unless you mean
  to, and only with a backup: a downgrade drops the tables it removes.
- `ALEMBIC_DATABASE_URL` overrides the target for one invocation (used to migrate the test DB
  locally).

## 5. Health check

| | |
|---|---|
| Endpoint | `GET /api/v1/health` |
| Auth | none |
| Success | `200` with `{"data": {"status": "ok"}, "error": null, "meta": null}` |
| Scope | **Liveness only.** It confirms the process is serving requests and doesn't query the database, so it stays fast and never exposes configuration, credentials, or user data. Database problems show up as 500s on real endpoints and as tracebacks in the logs. |

Frontend liveness: `GET /` returns 200.

## 6. Local production-like verification

What was run locally on 2026-09-28 (Windows 11, Node 24.14, Python 3.13). This was **not a
deployment and not a browser test**:

```bash
# Backend: production start command
cd backend
PORT=8765 FORWARDED_ALLOW_IPS='*' uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
curl -i http://localhost:8765/api/v1/health        # 200, envelope, security headers
curl -i http://localhost:8765/api/v1/dashboard     # 401 unauthenticated envelope
curl -i -X OPTIONS http://localhost:8765/api/v1/auth/login \
     -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: POST"   # 200 + allow-origin
curl -i -X OPTIONS ... -H "Origin: https://evil.example" ...                       # 400, no CORS headers
curl http://localhost:8765/api/v1/health -H "X-Forwarded-For: 203.0.113.7"         # access log shows 203.0.113.7

# Frontend: production build and start
cd frontend
npm run build
PORT=3100 npm run start
curl -o /dev/null -w "%{http_code}" http://localhost:3100/                       # 200 (also /login, /register, /dashboard, /offline, /sw.js)
curl -o /dev/null -w "%{http_code}" http://localhost:3100/definitely-not-a-page  # 404, custom "Page not found"
```

## 7. Staging deployment checklist

1. **Pick a topology** (section 1). If you use A, you need a domain whose DNS you control.
2. **Create a managed PostgreSQL database** and an application role. Build `DATABASE_URL` in the
   asyncpg format with `?ssl=require`.
3. **Backend service** (root `backend/`):
   - Install with `pip install .`.
   - Set every required variable from section 3: `ENVIRONMENT=production`, a new
     `JWT_SECRET_KEY`, `CORS_ORIGINS` set to the frontend origin, the `TEST_DATABASE_URL`
     placeholder, `FORWARDED_ALLOW_IPS=*`, and `COOKIE_DOMAIN` for topology A.
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`.
   - Health check path: `/api/v1/health`. One instance, one worker.
4. **Run migrations** once against the staging database: `alembic upgrade head`, then confirm
   `alembic current` shows `5d7e1c2a9b30 (head)`.
5. **Frontend service** (root `frontend/`):
   - In the **build** environment, set `BACKEND_ORIGIN` to the backend origin (topology B), or
     set `NEXT_PUBLIC_API_URL` to it (topology A). Never set both.
   - Build with `npm ci && npm run build` and start with `npm run start`.
6. **HTTPS** on both domains (the platform-managed certificate is fine).
7. **Smoke test in a real browser:**
   - The landing page loads.
   - Register, then log in.
   - Add an expense and see it on the dashboard.
   - **Reload the page and confirm you're still signed in** (this validates the cookie and CORS
     setup).
   - Log out.
   - Check the headers with `curl -I https://api.example.com/api/v1/health`.
8. **Confirm nothing sensitive is public:**
   - The frontend bundle holds only the API URL.
   - No `.env` file is in the repository or the build artifacts.
   - Real Setu credentials are nowhere at all (none are needed yet).

## 8. Security requirements

- **HTTPS only** for both services. `ENVIRONMENT=production` is required on any HTTPS
  deployment; without it, cookies aren't marked `Secure`.
- **Secrets only in platform environment variables:** the database URL and password,
  `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`, AWS keys, and any future Setu credentials. Never in the
  repository, never in a `NEXT_PUBLIC_*` variable, never in build logs.
- **Never commit `.env` files.** `backend/.env` and `frontend/.env.local` are gitignored and
  have never been in git history. Only the placeholder `.env.example` templates are tracked.
- **Never expose database credentials:** keep the database off public networks where the
  platform allows it, and use a least-privilege role.
- Use a **separate `JWT_SECRET_KEY` per environment**. Rotating it signs out every user.
- `/docs` and `/openapi.json` (FastAPI's interactive API docs) are **publicly reachable** in the
  current code. They describe the API but expose no data or secrets. Disabling them in
  production is recommended hardening, not yet done.

## 9. Setu staging and qualification considerations

- **Read-only, consent-based.** The bank-sync feature (`/api/v1/sync/*`) links accounts only
  through an Account-Aggregator-style consent flow and only **reads** transactions. There's **no
  payment initiation, no fund transfer, and no mandate**. The app never asks for or stores a UPI
  PIN, card PIN, CVV, OTP, net-banking password, or bank login; there are no fields for them in
  the database, the API, or the UI.
- **What staging runs today:** `SYNC_PROVIDER=mock`, a deterministic, clearly labeled demo
  provider. `setu_sandbox` exists only as a structural stub whose operations aren't implemented,
  and it makes no network calls. **Keep `mock` for the public staging URL.** Selecting
  `setu_sandbox` doesn't connect to Setu.
- **Credentials stay server-side.** When Setu issues sandbox credentials, they go **only** into
  the backend platform's secret settings (`SETU_SANDBOX_*`). Never into a tracked file, a
  `NEXT_PUBLIC_*` variable, the frontend, logs, screenshots, or support tickets.
- **Real (production) Setu credentials must never be committed** or placed in any staging
  environment. Nothing in this codebase supports a production Account Aggregator connection.
- AI categorization of synced transactions is off by default. It needs both `ANTHROPIC_API_KEY`
  and each user's own opt-in.

## Staging limitations (as of this document)

- **Session restore after reload needs topology A or B.** Under C, users are signed out on every
  reload. Vercel + Render uses B through the built-in proxy.
- **Client-IP rate limits can be spoofed** by calling the backend's public URL directly. Login
  is also protected per account, but registration, refresh, and audit-log IPs aren't. See
  [Client IP behind the proxy](#client-ip-behind-the-proxy).
- **Access tokens last 15 minutes** and are refreshed automatically on the first 401, which
  needs the refresh cookie to reach the backend (topology A or B, same as session restore).
  When the refresh is rejected, the user is sent to the login page with a "session expired"
  message.
- **Receipts** are stored on local, ephemeral disk unless S3 or a volume is configured. OCR is
  the labeled mock.
- **AI assistant** is the labeled mock unless `ANTHROPIC_API_KEY` is set. **Bank sync** is mock
  only.
- **No scheduler:** recurring transactions generate when the user clicks "Generate", and
  notifications generate when they're read.
- **Per-IP rate limits are in-memory** and per process, and reset on restart. The per-account
  login throttle is in PostgreSQL and is unaffected.
- **Not implemented:** email verification, password reset, account deletion, and data export.
- **No deployment config files** (Dockerfile, platform manifests) are committed. Configure the
  commands above in the platform's settings.
