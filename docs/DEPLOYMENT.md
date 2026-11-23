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
| Install | `npm ci` (recommended). The Vercel project currently leaves Install Command on auto-detect, which runs `npm install` |
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

**Migrations.** Alembic runs 18 linear revisions. The head is `d7a1e4c9b3f2`. Run from `backend/`
with the staging `DATABASE_URL` in the environment:

```bash
cd backend
alembic upgrade head      # creates every table and seeds the 14 system categories
alembic current           # should print: d7a1e4c9b3f2 (head)
```

- On a fresh database this is the complete setup. On later deploys, the same command applies
  only the new revisions, so run it **before** starting the new backend version.
- `upgrade` never drops data. **Never run `alembic downgrade` against staging** unless you mean
  to, and only with a backup: a downgrade drops the tables it removes.
- `ALEMBIC_DATABASE_URL` overrides the target for one invocation (used to migrate the test DB
  locally).

### Lockstep deploy: credit-card ledger fix (F-001)

> **Status:** the ledger code fix and its data-correction migration `c8e4a1f6b2d9` are on branch
> `fix/credit-card-ledger-semantics`, not deployed. Rehearse the whole procedure on a copy of the
> target data before running it against production.

**Why lockstep.** Before the fix, card transactions were booked with asset signs: a purchase
*lowered* the stored amount owed. The fixed code books and reverses card legs as changes to the
amount owed. Both mixed states are wrong:

- **New code, uncorrected data:** editing or deleting an old card transaction reverses it with
  the new sign, doubling the original error.
- **Old code, corrected data:** every new card transaction is booked with the old, wrong sign.

So nothing may write to the ledger while the correction runs, and only the new backend may write
after it. The frontend change (labels only, same API) can ship in either order.

**What migration `c8e4a1f6b2d9` does.** For each card it computes D (the sum of its legs'
cash-flow deltas) and corrects the balance by `−2·D`. It computes exactly the per-card figures of
Part 2 of the impact check, and a test keeps the two in agreement.

- It takes `LOCK TABLE accounts, transactions IN SHARE ROW EXCLUSIVE MODE` (10 s lock timeout),
  so no write can land between computing D and updating the balance. If a long-running request
  holds the tables, it fails on the timeout and changes nothing; retry.
- **Nothing to correct** (no card with D ≠ 0, including a database with no cards): it runs
  without a flag, changes no balance, and writes one `ledger.card_balance_correction` summary
  audit row (`mode: none`).
- **Something to correct:** it refuses unless the operator passes
  `-x card_balance_correction=apply`.
- **Cards it refuses even with `apply`** (`blockers` in the audit row): a card with a leg in
  another currency (`currency_mismatch` -- the account's currency was edited after booking, so D
  would mix currencies); a card with an `account.balance_updated` audit row
  (`balance_set_after_ledger_fix` -- only the fixed code writes those, so the old-sign formula
  doesn't describe the card); or a card with a leg written since a previous run of this revision
  (`ledger_activity_since_previous_correction` -- see "Re-upgrading after a downgrade"). Reconcile
  such a card by hand, then exclude it with
  `-x card_balance_correction_skip=<account id>[,<account id>...]`; "Reconciling a skipped card"
  below is the procedure. A skipped card is left untouched and gets an
  `account.balance_correction_skipped` audit row.
- **Review signals** (reported, not blocking): a credit balance or over-limit balance after
  correction, or an account row changed more than 60 s after its last ledger write (a possible
  hand-entered balance under the old code, which kept no audit trail; also triggered by a rename
  or a deleted transaction). They are recorded in each card's audit row. What they cannot catch
  is set out in "Limits of detection" below -- read it before treating a clean report as a
  guarantee.
- Every corrected card gets an `account.balance_corrected` audit row with the previous balance,
  D, the correction and the new balance. Transactions are never touched.
- A refusal raises before any write. Alembic runs every pending revision in one transaction, so
  the whole run rolls back and `alembic current` is unchanged. An unknown `card_balance_correction*`
  option, a bad mode value, a skip id with nothing to skip, and offline (`--sql`) mode are refused
  the same way.

**Zero cards doesn't remove the safeguards.** The production check on 2026-11-22 found no credit
card accounts and no transactions, so the expected production run is the no-flag, `mode: none`
path. Nothing is special-cased for that: the migration recomputes everything at deploy time, and
if a card has been booked since the check it refuses instead of applying a stale conclusion. Other
databases (staging, restored backups, local databases used while developing this branch, where
card transactions were booked by the *fixed* code) can legitimately need correction, or must not
receive it. In those, the flag and the blockers are what stop a wrong correction.

**Render specifics — verified, not assumed.** Checked on 2026-11-22 against the live service
(Render MCP `list_services`) and Render's docs. Re-check before each deploy; a plan change alters
which procedure below applies.

| Fact | Value (2026-11-22) | Why it matters |
|---|---|---|
| Service | `personal-finance-os`, `srv-db39m7flk1mc739t5g80`, region `singapore` | the target |
| Instance plan | **`free`**, `numInstances: 1` | decides the procedure (see below) |
| Deployed branch | `feat/automatic-transaction-sync`, `autoDeploy: yes`, trigger `commit` | any commit on that branch deploys itself |
| Start command | `alembic upgrade head && uvicorn app.main:app ...` | the migration runs as part of starting the new instance |
| Health check path | **empty — none configured** | Render does not gate the traffic switch on the app being healthy |
| Maintenance mode | `enabled: false` | and unavailable on this plan, see next row |
| Render docs | "Maintenance mode is available only for paid web services." | **maintenance mode cannot be used while the service is on `free`** |
| Render docs | Free web services have no "Shell access via SSH or the Render Dashboard" and no "Running one-off jobs" | `alembic` cannot be run on Render except via the start command |
| Render docs | "Render **spins down** a Free web service that goes 15 minutes without receiving any inbound traffic"; ~1 minute to restart | a spun-down service is not a stopped service — it restarts on the next request |
| Render events (2026-11-14) | a settings change started a deploy (`trigger: service_updated`) | change build command / env vars only while suspended, after the migration (RELEASE_RUNBOOK §6) |
| Render docs (Python) | `PYTHON_VERSION` is read first and must be fully qualified; services created 2026-02-11 – 2026-10-12 default to 3.14.3 | set `PYTHON_VERSION=3.13.13`; the lock is tested on 3.13 only |
| Vercel (2026-11-23, `vercel project inspect`) | production branch `feat/automatic-transaction-sync`, root `frontend`, Node 24.x | a push to the Render branch is also a Vercel production deploy |
| Render docs (deploy order) | the start command runs on the new instance before it receives traffic; traffic switches when it is up; the old instance gets `SIGTERM` 60 s after the switch, then a ~30 s shutdown delay | the **old** backend can keep writing for roughly 90 s after the migration has already committed |

Two consequences follow, and they are why the procedure below is not "merge and watch the deploy":

- **The start-command path cannot stop writes.** The migration commits inside the new instance
  while the old instance is still serving. Its `LOCK TABLE` only covers its own transaction, so
  for up to ~90 s afterwards the *old* code can book card legs with the old sign, which the
  correction was already computed without. On a database with cards to correct that is a silent,
  per-card wrong balance.
- **The write-stop this runbook used to name does not exist on this plan.** Earlier revisions said
  "turn on maintenance mode". On `free` that option is unavailable, and it would not have stopped
  the new instance either: a service in maintenance mode still serves its private network and SSH,
  and returns 503 only to the public internet.

**Stopping writes, by plan.** Pick one and record which you used:

- **Free plan (current).** Turn auto-deploy **off**, then **suspend** the service from the Render
  dashboard. Confirm it actually stopped before touching data: `get_service` must report
  `"suspended": "suspended"`. Suspending stops the instance, so the migration cannot run from the
  start command — run it from an operator machine against the database instead (the free plan has
  no SSH and no one-off jobs, so there is no in-Render alternative). A spin-down is **not** a
  substitute: the next inbound request wakes the service.
- **Paid plan.** Turn auto-deploy off, then turn on maintenance mode, and confirm
  `maintenanceMode.enabled: true`. The start-command path is still exposed to the ~90 s
  old-instance overlap, so prefer the same out-of-band migration; if you do use the start command,
  treat Part 3 of the post-migration check as mandatory rather than advisory.

**Procedure (free plan, migration run out of band):**

1. **Measure first, on the old code.** While the target still runs the pre-fix backend, run the
   read-only check `scripts/sql/f001_card_ledger_impact_check.sql` (it is only valid against data
   booked by the old code). Keep its output with the deploy record. Part 1:
   - `cards_needing_correction = 0`: no flag is needed.
   - `correction_minor_by_currency`: the total correction per currency (never summed across
     currencies), with `cards_with_positive_correction` / `cards_with_negative_correction`.
     `distinct_card_transactions` counts transactions; `total_card_legs` counts legs (a card →
     card transfer is one transaction and two legs).
   - `cards_blocking_migration > 0` (`cards_with_currency_mismatch`,
     `cards_with_post_fix_balance_edit`, `cards_with_activity_since_previous_correction`):
     reconcile those cards (Part 2) and plan to skip them — see "Reconciling a skipped card".
   - `cards_possibly_edited_by_hand`, `cards_negative_after_correction` or
     `cards_over_limit_after_correction` > 0: review those cards in Part 2 before choosing
     `apply`, and read "Limits of detection" first.
2. **Back up.** Take a platform snapshot and/or `pg_dump -Fc` to encrypted storage. Never put the
   dump in the repository's `backups/` folder unencrypted.
3. **Stop writes.** Auto-deploy **off** first (so nothing deploys itself mid-procedure), then
   suspend the service. **Gate:** `get_service` reports `"suspended": "suspended"`. Record the
   timestamp.
4. **Put the new code on the branch without starting it.** Merge or push the migration-containing
   commit to the deployed branch. With auto-deploy off and the service suspended, nothing runs on
   Render. **Vercel does deploy it:** its production branch is the same
   `feat/automatic-transaction-sync`, so this push is also the frontend's production deploy. That
   is why it happens only while the backend is suspended: the new frontend calls endpoints and
   fields the old backend lacks (`/auth/delete-account`, `over_limit_minor`). Record the commit
   SHA — every check below compares against it.
5. **Migrate out of band.** From an operator machine, with the target `DATABASE_URL` in the
   environment: `alembic upgrade head`, plus `-x card_balance_correction=apply` only if step 1
   found cards to correct, plus `-x card_balance_correction_skip=<id>[,<id>]` for each card you
   reconciled by hand. A refusal changes nothing and leaves the revision unapplied; fix the cause
   and re-run.
6. **Verify, still suspended.** `alembic current` prints `d7a1e4c9b3f2 (head)` (the RLS revision
   ships in the same run; if this procedure is ever used for `c8e4a1f6b2d9` alone, it prints
   `c8e4a1f6b2d9 (head)`). Run the read-only
   `scripts/sql/f001_card_ledger_post_migration_check.sql`:
   - Part 1: the summary row exists, and its `mode`, `cards_corrected`, `cards_skipped` and
     `correction_minor_by_currency` match step 1.
   - Part 2: `cards_corrected` / `cards_skipped` match Part 1, and `rows_for_deleted_accounts` is 0.
   - Part 3: `card_legs_written_in_window` must be **0**. Anything else means something was still
     writing while writes were meant to be stopped; review the cards it touched before resuming.
   - Re-running the impact check now still shows non-zero D, because D is computed from
     transactions. That is expected.
7. **Resume, but only through the gate below.** Resuming is what exposes users to the new code, so
   it is the one step with a hard precondition.
8. **Smoke test:** a card expense raises the amount owed; a bank → card payment lowers the bank
   balance and the amount owed and leaves net worth unchanged.
9. **Restore the deploy settings.** Turn auto-deploy back on, then deploy the frontend.

**The resume gate.** Do not un-suspend the service (on a paid plan: do not turn maintenance mode
off) until **every** one of these is true. Each is a fact to read off a tool, not a judgement:

| # | Check | How |
|---|---|---|
| 1 | The database is at the migration's revision | `alembic current` prints `d7a1e4c9b3f2 (head)` — never just `c8e4a1f6b2d9 (head)`, because the two revisions ship together |
| 2 | The post-migration check passed, Part 3 included (`card_legs_written_in_window = 0`) | step 6 |
| 3 | A deploy exists for **the exact commit from step 4** | `list_deploys` — the newest deploy's `commit.id` equals that SHA |
| 4 | That deploy's `status` is `live` | `get_deploy` on its id — not `build_in_progress`, not `update_in_progress`, not `deactivated` |
| 5 | The live backend answers as healthy | `curl -fsS https://personal-finance-os-ug9o.onrender.com/api/v1/health` returns 200 |
| 6 | The code that is live is the fixed code | the deploy's commit SHA, not "the deploy went green" |

Order matters, and on the free plan it is circular unless read carefully: checks 3–5 need the
service *running*, but resuming is what you are gating. Resolve it by resuming in two stages —
un-suspend, then immediately verify 3–5 **before** announcing the service as available and before
turning auto-deploy back on. Render's docs don't say whether resuming rebuilds the branch's latest
commit or restarts the last successful deploy (checked 2026-11-23), so expect either. If check 3
shows the previous commit, use **Manual Deploy → Deploy latest commit** right away and repeat
checks 3–5 on that deploy. Until it is live, the pre-fix code serves corrected data. That window is
acceptable only because the step 1 check found **zero credit-card accounts**; with any card, do
not use this path on the free plan. If any check fails, suspend again; at that point the data is already
correct and consistent, and the only wrong thing is which code is serving it. Never leave a failed
deploy serving: on the free plan a failed start command means Render keeps the **previous**
(pre-fix) image, which is exactly the forbidden "old code, corrected data" state.

**Wire up the health check.** `healthCheckPath` is currently empty, so Render switches traffic to a
new instance without asking the app whether it is healthy, and check 5 is the only thing standing
in for that. Set it to `/api/v1/health` so Render gates the switch itself; until then check 5 is
mandatory and manual.

**Limits of detection.** The impact check and the migration can only see edits that left a trace.
These leave none, and no amount of re-running the check will surface them:

- **A balance typed in through `PUT /accounts` before this fix shipped.** The
  `account.balance_updated` audit row is part of *this* fix (decision E), so edits made under the
  old code wrote nothing to `audit_logs`. Such a balance is not `opening + D`, so `−2·D` moves it
  to a number wrong by twice the hand-entered difference.
- **A card transaction deleted under the old code.** The leg is gone from `transactions`, so it is
  absent from D, but its wrongly-signed effect is still baked into the stored balance.
- **An edit made within 60 s of a ledger write**, which `updated_after_last_ledger_write` cannot
  separate from the write itself.

What the signal does and does not mean: `cards_possibly_edited_by_hand` is a *hint*, not a finding
— a rename, a category change, or a deleted transaction also bumps `accounts.updated_at` past the
last ledger write. It is noisy in both directions. **Treat a clean report as "no evidence of a
manual edit", never as proof that none happened.** Practical consequences:

- A card whose corrected balance the user disputes after the deploy is not evidence the migration
  misbehaved; it may be one of the invisible cases above. The per-card
  `account.balance_corrected` audit row holds `previous_balance_minor`, `cash_flow_delta_minor`
  and `correction_minor`, which is enough to reconstruct and undo one card by hand.
- For any database where users could have edited balances by hand before the fix (not the current
  production database, which has no cards at all), prefer confirming opening balances with the
  user over trusting D.

**Reconciling a skipped card.** A blocked card is one the `−2·D` formula does not describe, so its
correct balance has to be established by hand and set deliberately. For each card in Part 2 of the
impact check with a non-empty blocker:

1. **Record the evidence** before changing anything: from Part 2, the `account_id`,
   `stored_balance_minor`, `cash_flow_delta_minor`, `correction_minor`, the blocker columns
   (`currency_mismatch_legs`, `has_balance_audit`, `legs_since_previous_correction`) and the
   timestamps. Keep it with the deploy record.
2. **Work out the true amount owed from the card's own statements**, not from D: start from the
   opening balance the user confirms, then apply each leg with the owed convention (purchase and
   cash advance raise it; refund and repayment lower it). The blocker says which legs are suspect:
   `currency_mismatch` → legs booked in another currency, which must not be summed with the rest;
   `balance_set_after_ledger_fix` → a `PUT /accounts` balance already set under the fixed code,
   usually already right; `ledger_activity_since_previous_correction` → legs the fixed backend
   booked, which are already correct and must be excluded from D.
3. **Exclude the card from the migration** with
   `-x card_balance_correction_skip=<account id>[,<account id>...]`. It is left untouched and gets
   an `account.balance_correction_skipped` audit row recording the blockers and the correction that
   was *not* applied. Every other card is still corrected in the same run.
4. **Set the balance afterwards, through the application**, with the new backend live:
   `PUT /api/v1/accounts/{id}` with the figure from step 2. That writes an
   `account.balance_updated` audit row (decision E), so the change is attributable, and it keeps
   the service layer as the only writer of balances. Never `UPDATE accounts` by hand.
5. **Re-run the impact check** afterwards. The card will still report a non-zero
   `correction_minor` (D comes from transactions and does not change), so this is not a pass/fail
   check — what you are confirming is that the card still appears with the same blocker and that
   no *other* card regressed. Record that you reconciled it, so the next operator does not try to
   "fix" it again.

**Rollback.** Prefer fixing forward. Card transactions created after the upgrade are booked with
the new rule, and the old code would reverse them with the wrong sign, so redeploying the old
backend is not safe on its own. If the correction itself must be undone,
`alembic -x card_balance_correction=revert downgrade a3f9c1d2e7b4` subtracts exactly the
correction recorded for each card, keeping later ledger activity, and writes an
`account.balance_correction_reverted` audit row. It refuses (changing nothing) for any card whose
balance was set through `PUT /accounts` after the correction, because reverting would overwrite
the user's balance. Reconcile it and exclude it with `-x card_balance_correction_skip=...`. With
nothing recorded (the zero-card case) the downgrade needs no flag and changes nothing.

**Re-upgrading after a downgrade.** Once the revision has run, the fixed backend is live and
every card leg written from (**the first run** − 60 s) onward is already correct. A second
upgrade recomputes D over *all* legs, so folding those in would move the balance by twice their
amount. The migration therefore blocks any such card with
`ledger_activity_since_previous_correction`, and the impact check counts them in
`cards_with_activity_since_previous_correction`. This also covers the state production is
actually in: the first run finds nothing to correct (`mode: none`) but still records that it
ran, so cards created and used *after* that run are protected too. To re-upgrade, reconcile
each blocked card by hand and skip it.

**Two records, because one can be deleted.** The guard above is only as good as the evidence
that the revision already ran, so every run writes that evidence twice, in the same transaction
as the correction:

| Record | Where | Survives |
|---|---|---|
| `ledger.card_balance_correction` summary row (`entity_type: migration`) | `audit_logs` | user deletion (`user_id` is `SET NULL`) |
| one row per invocation, `direction` `upgrade` / `downgrade` | `data_correction_runs` | a purge of `audit_logs` |

The migration dates the first run from **whichever record is older**, so losing one source does
not re-arm the double correction. Operational rules that follow from this:

- **Never prune `audit_logs` or `data_correction_runs`.** Nothing in the app deletes audit rows
  today and there is no retention job; if one is ever added it must exclude the
  `ledger.card_balance_correction*` actions, and it must not touch `data_correction_runs` at all.
- **The downgrade does not drop `data_correction_runs`.** That is deliberate asymmetry: a
  reverted correction still happened, and the next upgrade needs to know. `alembic check` stays
  clean because `app/models/data_correction_run.py` declares the table, so an autogenerated
  migration will not propose dropping it. A test asserts that.
- **Restoring a backup taken before the correction is safe**, because it restores the ledger and
  the records together: the data is pre-fix again and so is the evidence. The dangerous case is a
  *partial* restore or purge that removes the records while keeping fixed-code card legs.
- **If every record of the run is destroyed, nothing can detect it.** No safeguard can tell
  pre-fix from post-fix data without knowing when the fix went live, so a re-upgrade would then
  double-count. `backend/tests/test_migration_card_balance_correction.py` pins that limit in
  `test_guard_is_blind_only_if_every_record_of_the_run_is_destroyed` so nobody mistakes the
  guard for absolute. Treat the two records as part of the ledger's integrity, not as logs.
- The impact-check script reads `audit_logs` only, so after an audit purge it can report a card
  as clean that the migration will still refuse. The migration is the authority; the script is
  advisory.

Restoring the snapshot is the last resort: it is only consistent because writes were stopped, and
it discards every write made after the snapshot.

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
   `alembic current` shows `d7a1e4c9b3f2 (head)`. A deploy that includes the credit-card ledger
   fix must follow the [lockstep procedure](#lockstep-deploy-credit-card-ledger-fix-f-001)
   instead.
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

## 10. Production release procedure

This is the procedure for **every** release to the production stack (Render backend, Vercel
frontend, Supabase PostgreSQL). A release that contains migration `c8e4a1f6b2d9` (the F-001
branch) must instead follow the [lockstep procedure](#lockstep-deploy-credit-card-ledger-fix-f-001),
which replaces steps 3–5 below. Every step that changes production needs the owner's explicit
approval at the time; nothing here is automatic.

### Release gate (before anything is merged to the deployed branch)

1. **CI is green on the exact commit.** `.github/workflows/ci.yml` runs on every push: backend
   Ruff, pip-audit, `mypy app`, `alembic upgrade head` on a fresh PostgreSQL 17, a single-head check,
   `alembic check`, and the full pytest suite; frontend typecheck, ESLint, Vitest, the production
   build, and `npm audit --audit-level=high`. Render deploys without consulting CI, so this is a
   check the operator makes, not a gate Render enforces.
2. **Know which migrations ship.** `alembic history -r <revision live in prod>:head` lists them.
   Read each one: anything that rewrites data, or that the *old* code can't run against, needs a
   write-stop (see "Ordering" below).
3. **Environment variables.** Compare the names in `backend/.env.example` and
   `frontend/.env.example` against the platform settings. Compare names only; never copy values
   into tickets, chat, or logs. The backend refuses to start if a required one is missing, and
   with `ENVIRONMENT=production` it refuses a `*` in `CORS_ORIGINS`, because credentials are
   always on.
4. **Dependencies are the tested set.** CI installs with `pip install -c requirements.lock`,
   and Render must too (build command `pip install -c requirements.lock .`). `pyproject.toml`
   has only lower bounds, so without the lock a deploy picks whatever is newest that day. The
   project requires Python 3.13 (`backend/.python-version`). Don't rely on that file on Render:
   Render's docs place `.python-version` at the *repository* root, and the service builds from
   `backend/`. Set the service's `PYTHON_VERSION` environment variable instead, which Render
   checks first and which must be fully qualified (`3.13.13`, not `3.13`). Without it, this
   service (created 2026-10-07) defaults to Python 3.14.3, which the lock was not tested on.
5. **Supabase's Data API must not reach the app's tables.** The backend talks to PostgreSQL
   directly and never uses Supabase's REST/GraphQL API. As of 2026-11-22, production's Data API
   (PostgREST) was running, every `public` table had RLS disabled, and `anon`/`authenticated`
   held full table privileges, including through default privileges for new tables. So anyone
   with the project's publishable key could read or rewrite every row. Migration
   `d7a1e4c9b3f2` closes this at the database (see "Supabase Data API containment" below). Before
   each release, confirm the Data API is off or `public` is not exposed, and once the migration
   has run, that RLS is enabled on every table.

### Ordering

Render's start command runs `alembic upgrade head` on the **new** instance, and the old instance
keeps serving for about 90 s after the traffic switch (see "Render specifics" above). So:

- **Additive migrations** (new tables, nullable columns, new indexes): the normal path below is
  safe, because the old code ignores what it doesn't know about.
- **Destructive or data-rewriting migrations**, or ones the old code can't run against: stop
  writes first (auto-deploy off, suspend), migrate out of band, then resume, as in the lockstep
  procedure. Never rely on the start command for these.
- **Frontend after backend** when the frontend needs a new endpoint or field. A labels-only
  frontend change can ship in either order.

### Normal release (no write-stop needed)

1. **Back up.** Take a `pg_dump -Fc` of the production database to encrypted storage outside the
   repository. Check the Supabase dashboard's backup page for what the current plan retains, and
   don't assume a platform backup exists until you've seen it listed there.
2. **Merge to the deployed branch** (`feat/automatic-transaction-sync` as of 2026-11-22; re-check
   in Render). With auto-deploy on, this starts the Render deploy.
3. **Watch the deploy.** In the Render deploy log, `alembic upgrade head` must log each expected
   revision and then uvicorn must start. A failed start command leaves the previous image
   serving, so a red deploy is not an outage, but the migration may have committed. Check
   `alembic current` before retrying.
4. **Verify the live backend:**
   - `curl -i https://<backend>/api/v1/health` returns 200 with the envelope, and an
     `X-Request-Id` header.
   - The deploy's commit SHA in Render matches the commit you merged.
5. **The frontend deploys itself.** Vercel's production branch is the same branch, so step 2
   already started a Vercel production deploy; confirm it is Ready and built the merged commit
   (`vercel inspect <deployment url> --logs` shows `Commit: <sha>`). Then check
   `curl -I https://<frontend>/` for `Content-Security-Policy`, `Strict-Transport-Security`,
   `X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff`.
6. **Smoke test in a browser:** log in, reload and stay signed in, add an expense, see it on the
   dashboard, then log out.

### Rollback

| What shipped | How to roll back |
|---|---|
| Frontend only | Vercel: promote the previous production deployment (instant, no data impact). |
| Backend code, no migration | Render: redeploy the previous successful deploy. |
| Backend with an additive migration | Redeploy the previous code. Old code ignores the new schema, so leave the migration applied and fix forward. |
| Backend with a data-rewriting migration | Don't redeploy old code over migrated data. Follow that migration's own documented downgrade (for `c8e4a1f6b2d9`, the "Rollback" paragraph of the lockstep section). |
| Anything, as a last resort | Restore the step-1 dump. That discards every write since it was taken, so it's only consistent if writes were stopped. |

### Supabase Data API containment

**Status (2026-11-22): verified read-only, not yet contained.** Production's PostgREST was
running, all 20 `public` tables had RLS off, and `anon`/`authenticated` held every table
privilege. The backend does not depend on the Data API at all: it connects to PostgreSQL through
`DATABASE_URL` as `postgres`, uses its own JWT auth (not Supabase Auth), and stores receipts on
local disk or S3 (not Supabase Storage). No frontend code or dependency talks to Supabase.

Two independent layers close it. Do the first immediately; the second ships with the release.
The beginner-friendly, step-by-step version, with the expected result of each step, is
[RELEASE_RUNBOOK.md](RELEASE_RUNBOOK.md) §1.

1. **Turn the Data API off (dashboard, reversible, no code).**
   - Supabase Dashboard → project `zomkpjmpodescgprigxr` (check the ref in the URL; staging is
     `ghzgqdbeqoklktnocvet`) → **Integrations → Data API** → turn **Enable Data API** off. If you
     would rather keep it on, open the project's **API settings** and remove `public` from
     **Exposed schemas** instead.
   - Verify from any machine with the PowerShell commands in
     [RELEASE_RUNBOOK.md](RELEASE_RUNBOOK.md) §1. They read the project's **publishable/anon** key
     (Project Settings → API Keys) without echoing it; never use the secret/service_role key here.
     Anything other than 200 means the endpoint no longer serves the table. A 200 with a JSON
     array means it is still reachable.
   - Check **Logs → API Gateway** filtered to paths starting `/rest/v1/` for requests you didn't
     make. That's the only evidence of whether the exposure was used.
   - Effect on the app: none, because the backend's database connection doesn't go through the
     Data API. Undo by turning the toggle back on.
2. **Migration `d7a1e4c9b3f2` (database, with the release).** It revokes every `anon`/
   `authenticated` privilege (table, sequence, function, and default privileges for future
   objects), enables RLS on every table with no policies, and verifies both before committing.
   It needs no flag and runs in the same `alembic upgrade head` as `c8e4a1f6b2d9`, so it rides
   the lockstep procedure above. The owner-connected backend is unaffected (tested). Downgrade
   keeps the protection unless `-x rls_hardening=revert`, and never re-grants.
   - Verify afterwards (read-only):
     `SELECT count(*) FILTER (WHERE NOT relrowsecurity) AS without_rls, bool_or(has_table_privilege('anon', oid, 'SELECT')) AS anon_can_read FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r';`
     Expect `0` and `false`.
3. **After both, because the exposure existed:** have the one production user change their
   password (this revokes every session), and treat the data as possibly read. This is a
   production write and needs explicit approval.

### Logging, monitoring and error reporting (what exists today)

- **Logs:** the backend logs to stdout, which Render collects. Every request gets an id (inbound
  `X-Request-Id` if well-formed, else a fresh uuid4). It is returned in the `X-Request-Id`
  response header and stamped on every `app.*` log line, so a user-reported failure can be traced
  from its response header to the server traceback. Secrets, tokens, and request bodies are not
  logged.
- **Health:** `/api/v1/health` is liveness only (section 5). Render's health-check path is not yet
  configured on the service (see "Wire up the health check").
- **Not in place:** no alerting on errors or downtime, no uptime monitor, and no remote error
  reporting (Sentry or similar) for either the backend or the browser. Until one is added, the
  operator watches the Render log stream and the smoke test after each release.

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
