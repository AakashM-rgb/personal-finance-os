# Architecture

How the code in this repository is actually structured today. The engineering rules behind it are
in [`CLAUDE.md`](../CLAUDE.md). Related docs: [DATABASE.md](DATABASE.md),
[TESTING.md](TESTING.md), [ERROR_HANDLING.md](ERROR_HANDLING.md).

## System overview

```
┌────────────────────────────┐   HTTPS JSON    ┌───────────────────────────────────────────────┐
│ Frontend: Next.js 16       │ ──────────────▶ │ Backend: FastAPI (/api/v1)                     │
│ App Router, React 19, TS,  │  Bearer access  │                                                │
│ Tailwind 4, Recharts       │  token + httpOnly│  api/v1 (routers) → services → repositories    │
│                            │  refresh cookie  │                        │             │         │
│ lib/api-client.ts (only    │ ◀────────────── │                        ▼             ▼         │
│ HTTP client) + lib/*.ts    │  {data,error,meta}│                 ai/ search/      models/   │
│ IndexedDB offline queue    │                 │                 ocr/ storage/     (SQLAlchemy)│
└────────────────────────────┘                 │                 sync/ jobs/          │         │
                                               └──────────────────────────────────────┼─────────┘
                                                                                      ▼
                                                                          PostgreSQL (Alembic)
```

There are two deployables, `frontend/` and `backend/`, plus PostgreSQL. Optional integrations
(Anthropic, S3, OCR, the bank-sync provider) sit behind provider interfaces. When they aren't
configured, each one falls back to a labeled mock or local implementation.

## Backend request path

Every protected request follows the same path. Taking `PUT /api/v1/transactions/{id}` as the
example:

1. **Middleware** (`app/main.py`): CORS (origins from `CORS_ORIGINS`, credentials allowed) and
   `SecurityHeadersMiddleware` (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS in
   production only).
2. **Router** (`app/api/v1/transactions.py`): thin. FastAPI validates the path, query, and body
   against Pydantic schemas in `app/schemas/`, resolves `get_db` and `get_current_user`, calls
   one service function, commits, and wraps the result as `{"data": ..., "error": null, "meta": ...}`.
3. **Auth dependency** (`app/auth/dependencies.py::get_current_user`): the single place a bearer
   JWT is decoded. It checks `type == "access"`, parses `sub` as a UUID, and loads an active
   user. Any failure raises `AuthenticationError` (401).
4. **Service** (`app/services/transaction_service.py`): business rules, including transfer-shape
   validation, ownership of every referenced account and category, and balance updates. Services
   never accept a `user_id` from the request, only from `current_user.id`.
5. **Repository** (`app/repositories/transaction_repository.py`): the only layer that builds
   queries. Every method takes `user_id` and puts `Transaction.user_id == user_id` in the
   `WHERE` clause, so ownership can't be forgotten per endpoint.
6. **Model** (`app/models/transaction.py`): SQLAlchemy 2.0 async ORM. CHECK and UNIQUE
   constraints back up the service rules.
7. **Errors** (`app/core/errors.py`): domain exceptions (`ValidationAppError` 422,
   `AuthenticationError` 401, `AuthorizationError` 403, `NotFoundError` 404, `ConflictError` 409)
   and a catch-all handler that turn everything into `{data: null, error: {code, message,
   field_errors}, meta: null}`. See [ERROR_HANDLING.md](ERROR_HANDLING.md).

A request for another user's resource returns **404, not 403**. The repository simply finds no
row for `(id, user_id)`, so the response doesn't even confirm the resource exists.

### Backend packages

| Package | Responsibility |
|---|---|
| `app/api/v1/` | 20 routers, 94 endpoints (listed in the [README](../README.md#api-reference)) |
| `app/schemas/` | Pydantic v2 request/response models, kept separate from ORM models |
| `app/services/` | Business logic. The `*_calculations.py` modules plus `recurrence.py`, `health_score.py`, and `month_bounds.py` are pure, DB-free functions so every money and date rule is unit-testable. |
| `app/repositories/` | User-scoped queries, one clearly scoped query per method |
| `app/models/` | 18 tables, see [DATABASE.md](DATABASE.md) |
| `app/auth/` | `get_current_user`, CSRF double-submit check, cookie helpers |
| `app/core/` | Settings (fail-fast env loading), DB session, error handlers, rate limiter, JWT/Argon2 helpers, logging |
| `app/ai/provider/` | `AnthropicProvider` / `MockProvider` for the assistant |
| `app/ai/tools/` | The fixed, read-only tool catalog the assistant may call: `get_monthly_spending`, `get_category_spending`, `get_transactions`, `get_budget_status`, `get_savings_goals`, `get_recurring_expenses`, `get_account_balances`, `compare_periods`. Each one calls the same service functions the REST API uses. |
| `app/ai/classifier/` | A separate one-shot merchant categorizer (Anthropic or mock), used only by sync, and only when the user has opted in |
| `app/search/` | Natural-language search. Text is compiled into a validated, allow-listed filter object and run through `TransactionRepository`. No generated SQL. |
| `app/ocr/`, `app/storage/` | Receipt OCR (mock) and file storage (local filesystem, or S3 when configured) behind interfaces |
| `app/sync/provider/` | Bank-sync provider seam: `mock` (default), plus a `setu_sandbox` stub whose operations aren't implemented |
| `app/jobs/` | Job seams: `recurring_transaction_generator`, `notification_generator`. No scheduler runs them automatically yet; see "Background work" below. |

### Key financial flows

**Transfers.** `type='transfer'` is a first-class enum value. The service requires a distinct,
active, same-currency destination account owned by the same user, and no category. The DB
constraint `ck_transactions_transfer_shape` backs this up. Balances move −amount on the source and
+amount on the destination. Income and expense aggregates filter on `type`, so transfers never
count as income or spending.

**Balances.** `accounts.balance_minor` is updated in the same DB transaction as the ledger write
(`_apply_balance_effect`). An edit reverses the old effect, then applies the new one. A delete
reverses the effect. The net-worth report rebuilds historical balances with a query that mirrors
these same rules (`sum_balance_delta_by_month_for_accounts`).

**Recurring generation.** There's no stored "next run" pointer. For each active schedule, the next
date is computed from the latest generated transaction (or from `start_date` if there is none) and
materialized through the same `create_transaction` path as a manual entry. Occurrences are stamped
at 00:00 UTC, and the `(recurring_transaction_id, occurred_at)` unique constraint makes a
concurrent double-run harmless. Month-end schedules clamp to short months without drifting
(`services/recurrence.py`).

**Subscriptions.** A subscription is a 1:1 marker on a recurring expense. Monthly and yearly
costs use the one canonical normalization in `subscription_calculations.py` (365 days, 52 weeks,
12 months per year). The same function feeds the analytics recurring breakdown.

**Budgets, analytics, reports, dashboard.** These are all read-side and computed on demand from
indexed SQL. There's no cache and no second source of truth. They share `month_bounds.py` (UTC
calendar months), base-currency-only aggregation, and half-open `[from, to)` ranges.

**Idempotent writes.** `POST /transactions` accepts `Idempotency-Key`. The frontend offline queue
(`lib/offline/sync-queue.ts`) sends one per queued expense, so a replay after reconnecting can't
double-book.

### Background work

`app/jobs/` defines `run_for_user` and `run_for_all_users` for recurring generation and
notification generation. What actually runs today:

- Recurring generation runs when the user calls `POST /api/v1/recurring-transactions/generate`.
- Notification generation runs inline when the notification list or unread count is requested.
- `run_for_all_users` sweeps exist, but **no scheduler is wired up to call them**.

## Frontend

```
app/
├── layout.tsx            Root layout: fonts, theme bootstrap script, service worker, AuthProvider
├── error.tsx             Render-error boundary for public pages
├── global-error.tsx      Boundary for failures in the root layout itself
├── not-found.tsx         Themed 404
├── (marketing)/page.tsx  Landing page
├── (auth)/               login, register
├── (app)/layout.tsx      Signed-in shell: auth guard, sidebar (md+), header, bottom nav (mobile)
├── (app)/error.tsx       Render-error boundary that keeps the app shell usable
├── (app)/<feature>/page.tsx  dashboard, transactions, accounts, budgets, goals, recurring-transactions,
│                         subscriptions, analytics, calendar, reports, receipts, ai, settings (+ categories,
│                         connected-accounts, merchant-rules)
└── offline/page.tsx      Service-worker navigation fallback
components/<feature>/     Feature components; components/ui/ holds shared primitives
lib/
├── api-client.ts         The only fetch wrapper (JSON, upload, blob). Throws ApiError.
├── <feature>.ts          Typed request functions per resource (accounts.ts, transactions.ts, ...)
├── money.ts              All money formatting and parsing (integer paise ⇄ display string)
├── auth-context.tsx      In-memory access token, session restore through the refresh cookie
└── offline/              IndexedDB drafts and sync queue, online/offline hook, SW registration
```

**Data fetching.** The app doesn't use React Query. Pages are client components that call typed
functions from `lib/<feature>.ts`, which go through `lib/api-client.ts`. Each page keeps its own
`data`, `error`, and loading state in `useState`/`useEffect`, with an `isMounted` guard and a
`reloadToken` for "Try again". This is the single data layer the project uses. There are no ad
hoc `fetch` calls in components.

**Auth on the client.** The access token lives only in React state, never in `localStorage`. On
first load, `AuthProvider` calls `POST /auth/refresh` if a `csrf_token` cookie exists, which
restores the session from the httpOnly refresh cookie. `(app)/layout.tsx` redirects to `/login`
when there's no user.

**Responsive layout.** At `md` and up, the app shows a persistent sidebar. Below `md`, it shows a
`MobileBottomNav` with a central Add action that opens the quick-add expense sheet.

**Offline and PWA.** `public/sw.js` intercepts same-origin GETs only. It caches static build
assets and the `/offline` shell, never `/api/` responses and never mutating requests, and falls
back to `/offline` for a failed navigation with nothing cached. Expenses
added while offline are stored in IndexedDB (`lib/offline/db.ts`) and replayed with
idempotency keys (`lib/offline/sync-queue.ts`).
