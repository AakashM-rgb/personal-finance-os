# personal-finance-os

A personal finance web app built as a "personal financial operating system". Its core loop is
**Record → Understand → Predict → Improve**: fast expense entry, a ledger that handles transfers
correctly, budgets, goals, recurring bills and subscriptions, analytics, reports, receipts, and a
tool-restricted AI assistant. It's INR-first, with money stored as integer paise from the
database all the way to the UI.

- Product requirements: [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md)
- Engineering rules: [`CLAUDE.md`](CLAUDE.md)
- Deep dives: [Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE.md) ·
  [Testing](docs/TESTING.md) · [Error handling](docs/ERROR_HANDLING.md)

## Contents

[Features](#features) · [Architecture](#architecture) · [Setup](#setup) ·
[Environment variables](#environment-variables) · [API reference](#api-reference) ·
[Database schema](#database-schema) · [Testing](#testing) · [Security](#security) ·
[Development workflow](#development-workflow) · [Current project status](#current-project-status)

## Features

Everything listed here is implemented and has tests. The "Status" column is for integrations that
fall back to a mock when they aren't configured.

| Area | What it does | Status |
|---|---|---|
| Auth | Register and log in (Argon2 hashes), a 15-minute access JWT, a rotating httpOnly refresh cookie with reuse detection, CSRF double-submit on refresh and logout, a session list, "log out everywhere", rate limits | Live |
| Accounts | Bank, cash, UPI, savings, wallet, and credit card (limit, statement and due days, utilization). Archiving instead of deletion. | Live |
| Categories | 14 seeded system categories plus custom categories, archiving, and duplicate-name protection | Live |
| Transactions | Income, expense, and first-class **transfers**; filters, search, sort, pagination; duplicate; quick-add text parsing; `Idempotency-Key` for safe retries | Live |
| Dashboard | Balances, net worth, month income/expense/savings, category breakdown, projection, upcoming credit-card payments, **Financial Health Score** with its factors explained | Live |
| Budgets | Monthly per-category limits, status thresholds (70/90/100%), a linear projection labeled as an estimate, suggestions from trailing averages | Live |
| Savings goals | Progress, remaining amount, and the required monthly and weekly pace | Live |
| Recurring transactions | Daily, weekly, monthly, quarterly, and yearly schedules; idempotent catch-up generation; month-end clamping | Live (generation runs on demand; see status) |
| Subscriptions | Built on recurring transactions; monthly and yearly cost normalization; an evidence-based "possibly unused" flag | Live |
| Analytics | Spending over time, category breakdown, income vs. expense, savings trend, daily spending, budget performance, recurring breakdown | Live |
| Calendar | Month view of real daily income/expense totals and transactions, plus bills projected from recurring schedules | Live |
| Reports | Monthly, yearly, category, income, expense, budget, savings, and net-worth reports; CSV, Excel, and PDF export | Live |
| Receipts | Upload with type checked by content and a 10 MB limit, OCR extraction, review and confirm, create a transaction | Storage: local or S3 · OCR: **mock** |
| AI assistant | Chat over a fixed read-only tool catalog (8 tools), obeys the per-user AI toggle | Anthropic when `ANTHROPIC_API_KEY` is set, otherwise a labeled **mock** |
| Natural-language search | "food last month over ₹500" becomes a validated filter, run by the normal repository | Live (deterministic interpreter) |
| Notifications | Budget warnings and overruns, subscription/recurring/credit-card reminders, goal milestones, unusual spending; deduplicated | Live (generated on read) |
| Settings | Profile (read-only), currency and theme, AI toggles, notification preferences, active sessions | Live |
| Bank sync | Account-aggregator-style consent linking, sync runs, dedupe, a review flag, merchant rules, opt-in AI categorization | **Mock** provider; `setu_sandbox` is a stub with no implementation |
| PWA / offline | Installable manifest, a service worker (static assets and offline shell only), and offline expense queueing with idempotent replay | Live |
| Landing page | Marketing page with demo data (clearly illustrative) | Live |

## Architecture

```
Next.js (App Router, TS, Tailwind)  ──JSON over HTTPS──▶  FastAPI /api/v1
  lib/api-client.ts (only client)                          api/v1 routers (thin)
  lib/<feature>.ts typed calls                               → services/ (rules, money math, ownership)
  IndexedDB offline queue                                    → repositories/ (every query scoped by user_id)
                                                             → models/ (SQLAlchemy 2.0 async)
                                                             → PostgreSQL (Alembic)
                                              side ports: ai/ · search/ · ocr/ · storage/ · sync/ · jobs/
```

- Routers validate input and call **one** service. Services hold every business rule.
  Repositories are the only layer that queries the database, and every query filters by the
  authenticated `user_id`.
- The AI assistant, NL search, reports, and analytics all use the **same service functions** as
  the REST endpoints. There's never a second code path to the same number.
- Pure calculation modules (`*_calculations.py`, `recurrence.py`, `health_score.py`,
  `month_bounds.py`) have no DB access, so every money and date rule is unit-tested directly.

Full walkthrough, including the request lifecycle and the transfer, recurring, and idempotency
flows: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Setup

### Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- PostgreSQL running locally (or reachable), with a dedicated application role and database
  created (see `backend/.env.example` for the connection string shape). Never use the Postgres
  superuser for the running application.

### Backend (`backend/`)

```bash
cd backend
uv venv .venv                 # or: python -m venv .venv
uv pip install -e ".[dev]"    # or: .venv/Scripts/pip install -e ".[dev]"
                              # optional extras: ".[dev,ai]" (Anthropic SDK), ".[dev,s3]" (boto3)

cp .env.example .env          # fill in real values - .env is gitignored

.venv/Scripts/alembic upgrade head      # apply migrations to DATABASE_URL
ALEMBIC_DATABASE_URL="<test db url>" .venv/Scripts/alembic upgrade head  # and to the test DB

.venv/Scripts/python -m pytest          # run tests
.venv/Scripts/python -m ruff check app tests
.venv/Scripts/python -m mypy app

.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Interactive OpenAPI docs are served at `http://localhost:8000/docs` while the backend runs.

### Frontend (`frontend/`)

```bash
cd frontend
npm install
cp .env.example .env.local    # points at the backend, defaults to http://localhost:8000
                               # (must share a hostname with the frontend - e.g. both
                               # `localhost` - never `127.0.0.1` here: cookies are scoped
                               # per-hostname, and the CSRF cookie has to be readable by
                               # this frontend's own JavaScript to restore a session)

npm run dev          # http://localhost:3000
npm run test         # vitest
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
npm run build        # production build
```

## Environment variables

Loaded by `backend/app/core/config.py` (pydantic-settings, from `backend/.env`). **Required**
variables have no default: the app refuses to start if one is missing or invalid, and it never
falls back to a hardcoded secret. The full commented template is `backend/.env.example`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ENVIRONMENT` | yes | none | `production` turns on `Secure` cookies and HSTS |
| `DATABASE_URL` | yes | none | `postgresql+asyncpg://…` for the app (least-privilege role) |
| `TEST_DATABASE_URL` | yes | none | A separate database for pytest |
| `JWT_SECRET_KEY` | yes (≥ 32 chars) | none | Signs access tokens |
| `JWT_ALGORITHM` | yes | none | e.g. `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | yes (> 0) | none | Access-token lifetime (template: 15) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | yes (> 0) | none | Refresh-session lifetime (template: 30) |
| `CORS_ORIGINS` | yes | none | Comma-separated frontend origins |
| `LOGIN_RATE_LIMIT`, `REGISTER_RATE_LIMIT` | yes | none | e.g. `5/minute` |
| `REFRESH_RATE_LIMIT` | no | `60/minute` | `/auth/refresh` and `/auth/logout` |
| `RECEIPT_STORAGE_DIR` | no | `var/receipts` | Local receipt storage (dev) |
| `S3_BUCKET`, `S3_REGION` | no | unset | Switch receipt storage to S3 when both are set |
| `OCR_PROVIDER` | no | `mock` | Only `mock` is implemented |
| `ANTHROPIC_API_KEY` | no | unset | Enables the real AI assistant and classifier; otherwise a labeled mock |
| `AI_MODEL` | no | `claude-sonnet-5` | Model id for the Anthropic provider |
| `AI_RATE_LIMIT`, `SEARCH_RATE_LIMIT` | no | `20/minute`, `30/minute` | Per-user limits on AI and search |
| `SYNC_PROVIDER` | no | `mock` | `mock` or `setu_sandbox` (a stub with no real calls) |
| `SYNC_LINK_RATE_LIMIT`, `SYNC_TRIGGER_RATE_LIMIT` | no | `10/minute`, `20/minute` | Sync endpoint limits |
| `SETU_NOTIFICATION_RATE_LIMIT` | no | `120/minute` | Per-IP limit on the Setu notification webhook |
| `SETU_SANDBOX_BASE_URL`, `SETU_SANDBOX_CLIENT_ID`, `SETU_SANDBOX_CLIENT_SECRET` | no | unset | Sandbox-only placeholders. Unused today. |
| `ALEMBIC_DATABASE_URL` | no | `DATABASE_URL` | Migration target override (used to migrate the test DB) |

Frontend (`frontend/.env.local`, template `frontend/.env.example`):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend base URL, e.g. `http://localhost:8000`. Must share a hostname with the frontend. |

## API reference

Base path `/api/v1`. There are **94 endpoints across 20 routers**, extracted from the running
app's OpenAPI schema (`app.openapi()`). The live, typed schema is at `/docs` and `/openapi.json`.

**Conventions**

- **Envelope:** every response is `{"data": …, "error": null | {code, message, field_errors},
  "meta": … | null}`. List endpoints with pagination put `{count, limit, offset}` in `meta`.
- **Auth:** 🔒 means `Authorization: Bearer <access token>`. Every 🔒 endpoint is scoped to the
  caller, and another user's resource returns **404**. 🍪 means the endpoint uses the httpOnly
  refresh cookie plus an `x-csrf-token` header matching the `csrf_token` cookie.
- **Money** is always an integer in minor units (`amount_minor: 125050` means ₹1,250.50). It's
  never a float.
- **Errors:** 401 unauthenticated · 404 not found (including other users' data) · 409 conflict ·
  422 validation (with `field_errors`) · 429 rate limited · 500 generic message only. See
  [docs/ERROR_HANDLING.md](docs/ERROR_HANDLING.md).
- ⏱ means the endpoint is rate-limited (limits come from the environment; see above).

### Health and auth

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| POST | `/auth/register` | none ⏱ | Create an account. Returns the access token and user, and sets the refresh and CSRF cookies. |
| POST | `/auth/login` | none ⏱ | Email and password login. Failed attempts are audit-logged. |
| POST | `/auth/refresh` | 🍪 ⏱ | Rotate the refresh token and get a new access token. Reusing a rotated token revokes every session for that user. |
| POST | `/auth/logout` | 🍪 ⏱ | Revoke the current session and clear cookies |
| POST | `/auth/logout-all` | 🔒 | Revoke every session for the user |
| GET | `/auth/me` | 🔒 | Current user |
| GET | `/auth/sessions` | 🔒 | The caller's active sessions |

### Accounts and categories

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/accounts?include_inactive=` | 🔒 | List accounts, with credit-card details and utilization |
| POST | `/accounts` | 🔒 | Create an account. `credit_card` requires limit, statement, and due-day fields. |
| GET / PUT | `/accounts/{account_id}` | 🔒 | Get or update (type can't be changed) |
| DELETE | `/accounts/{account_id}` | 🔒 | **Archive** (soft delete) |
| GET | `/categories?include_inactive=` | 🔒 | System plus custom categories |
| POST | `/categories` | 🔒 | Create a custom category (409 on a duplicate active name) |
| GET / PUT | `/categories/{category_id}` | 🔒 | Get or update |
| DELETE | `/categories/{category_id}` | 🔒 | Archive a custom category |

### Transactions

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/transactions` | 🔒 | Filters: `q`, `category_id`, `account_id` (matches either transfer leg), `type`, `date_from`, `date_to`, `amount_min`, `amount_max`, `is_recurring`, `tags` (any match), `sort_by` (`occurred_at` \| `amount_minor` \| `created_at`), `sort_dir`, `limit` (1–200, default 50), `offset` |
| POST | `/transactions` | 🔒 | Create an income, expense, or transfer and update balances. Accepts an `Idempotency-Key` header. |
| POST | `/transactions/quick-add/parse` | 🔒 | Parse text like `"250 food lunch"` into a draft (amount, category, confidence). Doesn't save anything. |
| GET / PUT | `/transactions/{transaction_id}` | 🔒 | Get or partially update (reverses the old balance effect, then applies the new one). `remember_category_for_merchant` creates a merchant rule. |
| DELETE | `/transactions/{transaction_id}` | 🔒 | Delete and reverse the balance effect |
| POST | `/transactions/{transaction_id}/duplicate` | 🔒 | Copy with today's date |

### Dashboard, budgets, and goals

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/dashboard` | 🔒 | Balances, net worth, this month's income/expense/savings, projection, category breakdown, recent transactions, upcoming payments, health score |
| GET | `/budgets` | 🔒 | Budget items with spent, remaining, percent, status, and projection for the current month |
| POST | `/budgets` | 🔒 | Create a budget for a category (409 if one exists) |
| GET | `/budgets/suggestions` | 🔒 | Suggestions from a 3-month trailing average or the category default |
| GET / PUT / DELETE | `/budgets/{item_id}` | 🔒 | Get, update the amount, or delete |
| GET | `/goals` | 🔒 | Savings goals with progress and required monthly/weekly pace |
| POST | `/goals` | 🔒 | Create a goal |
| GET / PUT / DELETE | `/goals/{goal_id}` | 🔒 | Get, update, or delete |

### Recurring transactions and subscriptions

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/recurring-transactions` | 🔒 | Schedules with the computed `next_occurrence_date` |
| POST | `/recurring-transactions` | 🔒 | Create an income or expense schedule |
| POST | `/recurring-transactions/generate` | 🔒 | Generate every due occurrence up to today (idempotent) |
| GET / PUT | `/recurring-transactions/{recurring_id}` | 🔒 | Get or update |
| DELETE | `/recurring-transactions/{recurring_id}` | 🔒 | Deactivate. Past generated transactions are kept. |
| GET | `/subscriptions` | 🔒 | Subscriptions with monthly and yearly cost and unused-evidence |
| POST | `/subscriptions` | 🔒 | Create (creates the underlying recurring expense) |
| GET / PUT | `/subscriptions/{subscription_id}` | 🔒 | Get or update |
| DELETE | `/subscriptions/{subscription_id}` | 🔒 | Deactivate |

### Analytics, calendar, and reports

`range` is one of `current_month` (default), `previous_month`, `last_3_months`,
`last_6_months`, `last_12_months`, or `custom` (which needs `custom_from` and `custom_to`,
inclusive). Export `format` is `csv`, `xlsx`, or `pdf`.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/analytics?range=&custom_from=&custom_to=` | 🔒 | Spending over time, category breakdown, income vs. expense, savings trend, daily spending, budget performance, recurring breakdown |
| GET | `/calendar?year=&month=` | 🔒 | Per-day income/expense totals and transactions, plus projected recurring bills |
| GET | `/reports/monthly?year=&month=` | 🔒 | Monthly report |
| GET | `/reports/yearly?year=` | 🔒 | Yearly report with a month-by-month breakdown |
| GET | `/reports/category`, `/reports/income`, `/reports/expense`, `/reports/savings` `?range=…` | 🔒 | Range reports |
| GET | `/reports/budget` | 🔒 | Budget report for the current month |
| GET | `/reports/net-worth` | 🔒 | Net worth now, plus a reconstructed monthly trend |
| GET | `/reports/{monthly,yearly,category,income,expense,budget,savings,net-worth}/export?format=…` | 🔒 | 8 export endpoints. Each takes the same parameters as its report and returns a file download. |

### Receipts, AI, and search

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/receipts` | 🔒 | List receipts |
| POST | `/receipts/upload` | 🔒 | Multipart upload (JPEG, PNG, or PDF, checked by magic bytes; 10 MB max), then OCR |
| GET / DELETE | `/receipts/{receipt_id}` | 🔒 | Get or delete (also deletes the stored file) |
| GET | `/receipts/{receipt_id}/file` | 🔒 | Stream the stored file (authenticated; there's no public URL) |
| PUT | `/receipts/{receipt_id}/confirm` | 🔒 | Save the user-reviewed merchant, date, total, and items |
| POST | `/receipts/{receipt_id}/transaction` | 🔒 | Create an expense from a confirmed receipt |
| POST | `/ai/assistant` | 🔒 ⏱ | Chat message (≤ 2000 chars, ≤ 20 history messages). Answers only from tool output; refuses when the user has turned AI off. |
| POST | `/search/financial` | 🔒 ⏱ | Natural-language query → validated filter → the interpreted criteria, the total match count, and a capped list of matching transactions |

### Settings, notifications, sync, and merchant rules

| Method | Path | Auth | Description |
|---|---|---|---|
| GET / PATCH | `/settings` | 🔒 | Currency, theme, `ai_enabled`, `ai_categorization_enabled`, notification preferences |
| GET | `/notifications?unread_only=&limit=&offset=` | 🔒 | Generates any due notifications, then lists them (limit ≤ 100) |
| GET | `/notifications/unread-count` | 🔒 | Unread count |
| PUT | `/notifications/{notification_id}/read` | 🔒 | Mark one as read |
| POST | `/notifications/read-all` | 🔒 | Mark all as read |
| GET | `/sync/links` | 🔒 | Linked (connected) accounts |
| POST | `/sync/links` | 🔒 ⏱ | Start a consent link with the provider |
| POST | `/sync/links/{consent_handle}/callback` | 🔒 | Complete a link (idempotent per consent) |
| GET / PATCH | `/sync/links/{linked_account_id}` | 🔒 | Get, or map to a local account |
| DELETE | `/sync/links/{linked_account_id}` | 🔒 | Revoke consent |
| POST | `/sync/links/{linked_account_id}/sync` | 🔒 ⏱ | Run a sync: fetch, dedupe, categorize, create transactions |
| GET | `/sync/links/{linked_account_id}/runs` | 🔒 | Sync history |
| GET | `/merchant-rules` | 🔒 | Merchant → category rules |
| POST | `/merchant-rules` | 🔒 | Create (an existing merchant key updates instead) |
| GET / PATCH / DELETE | `/merchant-rules/{rule_id}` | 🔒 | Get, update, or delete |

## Database schema

PostgreSQL with **18 tables**, created by **14 linear Alembic migrations** (head
`43b64866b554`). Full column, constraint, index, and delete-behavior reference:
[docs/DATABASE.md](docs/DATABASE.md).

| Group | Tables |
|---|---|
| Identity and security | `users`, `user_settings` (1:1), `sessions` (revocable refresh tokens), `audit_logs` |
| Core ledger | `accounts`, `credit_card_details` (1:1 extension), `categories` (system + custom, self-referencing), `transactions` |
| Planning | `budgets` (one per user), `budget_items`, `savings_goals`, `recurring_transactions`, `subscriptions` (1:1 extension), `notifications` |
| Documents and sync | `receipts`, `linked_accounts`, `sync_runs`, `merchant_category_rules` |

Key relationships and invariants:

- Every user-owned table has `user_id → users.id ON DELETE CASCADE`. `audit_logs` uses
  `SET NULL` so the audit trail survives.
- `transactions.type ∈ {income, expense, transfer}`. A CHECK constraint makes a transfer carry
  `transfer_account_id` and no category. Every income/expense aggregate filters on `type`, so
  transfers never count as income or spending.
- All money columns are `BIGINT *_minor` (paise). `amount_minor > 0`, and the sign comes from
  `type`.
- Transactions reference accounts with `RESTRICT` (accounts are archived, never hard-deleted), and
  reference categories and recurring schedules with `SET NULL`, so history survives.
- Unique constraints make retries safe: `(user_id, idempotency_key)`,
  `(recurring_transaction_id, occurred_at)`, `(linked_account_id, external_transaction_id)`, and
  `(user_id, dedupe_key)` on notifications.
- Indexes: `transactions (user_id, occurred_at)`, `(user_id, account_id)`,
  `(user_id, category_id)`, plus an index on every foreign key.

## Testing

| Suite | Count (last run 2026-09-28) | Command |
|---|---|---|
| Backend (pytest, real PostgreSQL) | **1066 passed** in 52 files. 475 pure-function unit tests, 591 HTTP → DB integration tests, 76 cross-user isolation tests using the second-user fixture. | `cd backend && .venv/Scripts/python -m pytest` |
| Frontend (Vitest + RTL, jsdom) | **256 passed** in 41 files | `cd frontend && npm run test` |
| E2E / browser | **none committed** | none |

Strategy, fixtures, per-module testing matrix, and known gaps: [docs/TESTING.md](docs/TESTING.md).

## Security

- **Isolation:** every repository query filters by the authenticated `user_id`. A cross-user
  access gets a 404, and each entity has negative tests.
- **Passwords:** Argon2 (passlib). They're never logged or returned.
- **Tokens:** a short-lived access JWT held **in memory only** on the frontend (never
  `localStorage`), and a refresh token in an httpOnly, `SameSite=Lax` cookie scoped to
  `/api/v1/auth` (`Secure` in production). Only the token's hash is stored in `sessions`.
  Refresh tokens rotate, and reuse revokes all of the user's sessions and is audit-logged.
- **CSRF:** a double-submit `csrf_token` cookie and `x-csrf-token` header on the cookie-authenticated
  endpoints (`/auth/refresh`, `/auth/logout`). Every other mutation needs a bearer header, which a
  cross-site request can't attach.
- **Rate limits:** register, login, refresh/logout, the AI assistant, search, and sync
  link/trigger (slowapi).
- **Headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and HSTS in production.
- **Uploads:** file type is checked from the file's own bytes, not its name; there's a 10 MB
  limit; files are served only through an authenticated endpoint.
- **AI:** no database access. It can only call 8 read-only, user-scoped tools that reuse the
  service layer. It never runs generated SQL. Stored user text (merchants, descriptions) reaches
  the model only inside structured `tool_result` blocks, never in the system prompt. There's no
  additional explicit prompt-injection instruction or filter yet. The per-user `ai_enabled`
  toggle is enforced in the tool layer itself (`app/ai/tools/registry.py`).
- **Secrets:** only from the environment. Startup fails if a required value is missing. `.env`
  files are gitignored.
- **Audit log:** register, login, failed login, logout-all, refresh-token reuse, and sync link
  lifecycle events.
- **Service worker:** never caches `/api/` responses or mutating requests.

## Development workflow

1. Read the relevant section of `CLAUDE.md` (the rules) and `PRODUCT_SPEC.md` (the requirements)
   before starting a feature. Work phase by phase.
2. Backend changes go through the layers in order: schema (`schemas/`) → repository method
   (scoped by `user_id`) → service → thin router. Put money and date rules in a pure
   `*_calculations.py` module and unit-test them.
3. Schema changes go through Alembic only:
   `.venv/Scripts/alembic revision --autogenerate -m "…"`. Review the generated file, write a
   real `downgrade()`, then `upgrade head` on both the dev and test databases and run
   `alembic check`.
4. Frontend: add typed calls in `lib/<feature>.ts` (through `lib/api-client.ts`), format money
   only with `lib/money.ts`, and give every data view loading (skeleton), empty, and error states.
5. Before calling a task done, run pytest, ruff, and mypy, then vitest, `npm run typecheck`,
   `npm run lint`, and `npm run build`.
6. Commits use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`). Never
   commit `.env` files or secrets.

## Current project status

Phases 1–5 of `CLAUDE.md` §21 are largely built, and part of Phase 6 (PWA/offline, a security
pass) is done. The current branch, `feat/automatic-transaction-sync`, adds bank sync with a mock
provider and a Setu sandbox seam.

**Verification (2026-09-28):** backend 1066/1066 passed, frontend 256/256 passed; ruff, mypy,
`tsc`, ESLint, `next build`, and `alembic check` all clean. Details in
[docs/TESTING.md](docs/TESTING.md#current-results).

**Not implemented yet** (no code exists for these):

- Email verification and password reset. The `users.email_verified_at` column exists, but there
  are no endpoints. There's also no password change or Google OAuth.
- Account deletion and full data export endpoints.
- CSV/Excel **import**. Only export exists.
- Expense splitting, gamification, and the financial calculator toolbox (Phase 6).
- A real scheduler for the `app/jobs/` sweeps. Recurring generation is triggered by
  `POST /recurring-transactions/generate`, and notifications are generated when they're read.
- A real OCR provider. A real bank-sync provider (`setu_sandbox` is an unimplemented stub).
- Budget adherence and emergency fund as health-score factors.

**Known engineering gaps:** automatic access-token refresh on the client, request and user IDs
in server error logs, an explicit prompt-injection guard for user text sent to the LLM, a
committed E2E suite, and coverage reporting. See
[docs/ERROR_HANDLING.md](docs/ERROR_HANDLING.md#3-known-gaps) and
[docs/TESTING.md](docs/TESTING.md#known-testing-gaps).

## Project layout

- `backend/`: FastAPI, SQLAlchemy (async), and Alembic. Layered as `api → services → repositories → models`.
- `frontend/`: Next.js (App Router), TypeScript, Tailwind CSS, and Recharts.
- `docs/`: architecture, database, testing, and error-handling references.
- `PRODUCT_SPEC.md`: the product requirements.
- `CLAUDE.md`: the engineering rules and the phased development plan this project follows.
- `SYNC_PROVIDER*.md`: research and decision records for the bank-sync provider.
