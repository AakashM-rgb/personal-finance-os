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

The browser talks to the API **directly** (client-side `fetch`, `credentials: "include"`). The
Next.js server never proxies API calls. The API base URL is baked into the frontend bundle at
build time from `NEXT_PUBLIC_API_URL`.

### Choosing domains (read this first)

Sessions are restored after a page reload through `POST /api/v1/auth/refresh`, which needs the
frontend's JavaScript to **read the `csrf_token` cookie** set by the API (a double-submit CSRF
check). So the frontend and API must be able to share cookies. That limits which domain layouts
work fully:

| Topology | Settings | Result |
|---|---|---|
| **A. Sibling subdomains of a domain you control** (recommended): `https://app.example.com` + `https://api.example.com` | `NEXT_PUBLIC_API_URL=https://api.example.com`, `CORS_ORIGINS=https://app.example.com`, `COOKIE_DOMAIN=example.com` | Everything works, including session restore on reload and logout. |
| **B. One public origin with path routing**: a platform router or reverse proxy sends `/api/*` to the backend and everything else to the frontend | `NEXT_PUBLIC_API_URL=https://app.example.com` (the shared origin), `CORS_ORIGINS=https://app.example.com`, `COOKIE_DOMAIN` unset | Everything works. Requires a host that supports path-based routing. |
| **C. Two unrelated domains** (e.g. two different platform-provided default subdomains) | `COOKIE_DOMAIN` unset. It can't be set to another site's domain, and platform default domains are usually on the Public Suffix List. | **Limited.** Sign-up, login, and the whole app work in the current tab, but **every full page reload or new tab signs the user out**, and logout can't revoke the server-side session (it simply expires). Acceptable only as a last-resort demo. |

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

**Environment (build-time, public):**

| Variable | Required | Staging value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | **yes** | The API origin: scheme and host only, no trailing slash, no `/api/v1`, e.g. `https://api.example.com` |

- It's inlined at **build time**. Set it in the platform's build environment and rebuild after
  changing it.
- If it's missing at build time, the code falls back to `http://127.0.0.1:8000`, and the
  deployed site can't reach the API. Always set it.
- It's public by design. **No other variable may be exposed with a `NEXT_PUBLIC_` prefix**, and
  the frontend needs no secrets. (Verified: the production bundle contains no `JWT_SECRET`,
  `DATABASE_URL`, `ANTHROPIC_API_KEY`, or `SETU_SANDBOX` references.)

Other notes:

- Every route is static or client-rendered. There's no server-side data fetching, no Next.js API
  routes, and no `next/image` remote config, so any Node host that can run `next start` works.
- Error pages: `app/error.tsx`, `app/(app)/error.tsx`, `app/global-error.tsx`, and a custom
  `app/not-found.tsx` (a real 404 status).
- `public/sw.js` is a service worker that never caches `/api/` responses or mutating requests.
  It needs HTTPS in production, which browsers require for service workers anyway.

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
- **One worker:** rate limits are kept in process memory (slowapi's default storage). With
  several workers or instances, each keeps its own counters, so the effective limit multiplies.
  One worker is enough for staging.

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
| `LOGIN_RATE_LIMIT`, `REGISTER_RATE_LIMIT` | yes | `5/minute` |
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

**Migrations.** Alembic runs 14 linear revisions. The head is `43b64866b554`. Run from `backend/`
with the staging `DATABASE_URL` in the environment:

```bash
cd backend
alembic upgrade head      # creates every table and seeds the 14 system categories
alembic current           # should print: 43b64866b554 (head)
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
   `alembic current` shows `43b64866b554 (head)`.
5. **Frontend service** (root `frontend/`):
   - Set `NEXT_PUBLIC_API_URL` to the backend origin in the **build** environment.
   - Build with `npm ci && npm run build` and start with `npm run start`.
6. **HTTPS** on both custom domains (the platform-managed certificate is fine).
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
  reload.
- **Access tokens last 15 minutes and aren't refreshed automatically** during a session. After
  that, API calls fail with "Invalid or expired session" until the page is reloaded, and a reload
  restores the session under A or B. See [ERROR_HANDLING.md](ERROR_HANDLING.md#3-known-gaps).
- **Receipts** are stored on local, ephemeral disk unless S3 or a volume is configured. OCR is
  the labeled mock.
- **AI assistant** is the labeled mock unless `ANTHROPIC_API_KEY` is set. **Bank sync** is mock
  only.
- **No scheduler:** recurring transactions generate when the user clicks "Generate", and
  notifications generate when they're read.
- **Rate limits are in-memory** and per process, and reset on restart.
- **Not implemented:** email verification, password reset, account deletion, and data export.
- **No deployment config files** (Dockerfile, platform manifests) are committed. Configure the
  commands above in the platform's settings.
