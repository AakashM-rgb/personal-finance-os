# CLAUDE.md — Engineering Rules for this Project

This file is the **permanent engineering constitution** for this project. It applies to every
session, every phase, and every contributor (human or AI). `PRODUCT_SPEC.md` defines *what* to
build; this file defines *how* it must be built. When the two ever appear to conflict, treat it as
a signal to stop and reconcile explicitly — do not silently pick one.

---

## 1. Project Purpose

Build a **premium, production-quality personal finance web application** — a "Personal Financial
Operating System," not a basic expense tracker. Core loop: **Record → Understand → Predict →
Improve**. It must feel like a real SaaS product used daily by students, young professionals, and
families, at any income scale (₹5,000/month to ₹5,00,000/month).

Full functional requirements live in `PRODUCT_SPEC.md`. Do not duplicate that content here —
this file only encodes durable engineering rules and decisions.

---

## 2. Product Principles (non-negotiable)

1. Simple for beginners, powerful for advanced users.
2. Expense entry must be extremely fast.
3. Beautiful, modern, restrained UI — mobile-first, but desktop must be excellent too.
4. Privacy-first. Secure financial data handling always wins over convenience.
5. Never overwhelm the user. Every dashboard element must earn its place.
6. No unnecessary animations, no decorative charts, no meaningless UI.
7. Every number shown must come from a real calculation over real data.
8. Design for scale from day one, but do not over-engineer for hypothetical futures.

---

## 3. Tech Stack (fixed — do not swap without explicit user approval)

**Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui + Recharts.
**Backend:** Python + FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + Alembic.
**Database:** PostgreSQL. Normalized schema. Integer minor-unit money.
**Auth:** JWT access token (short-lived) + rotating refresh token in httpOnly secure cookies,
backed by a revocable `sessions` table.
**Object storage:** Abstracted interface — local filesystem in dev, S3-compatible in production.
**Background jobs:** Abstracted job-runner interface — in-process scheduler in dev, swappable for
Celery/RQ + Redis in production. Never hard-depend on infra that isn't actually provisioned.
**AI:** Provider-abstraction interface. `AnthropicProvider` is the default; `MockProvider` is used
automatically when no API key is configured (clearly labeled as demo mode — never fabricate
results silently).
**Currency:** INR first-class; architecture must not preclude USD/EUR/GBP/JPY later.

---

## 4. Architecture

Layered, monorepo, two deployables:

```
Frontend (Next.js)  ──HTTP/JSON──▶  Backend (FastAPI)  ──▶  PostgreSQL
                                          │
                                          ├─▶ Object storage (receipts)
                                          ├─▶ Job runner (recurring, OCR, notifications)
                                          └─▶ AI provider (via tool catalog only)
```

Backend internal layering — **strict, one-directional**:

```
api/ (routers, thin)  →  services/ (business logic, money math, authorization)
                       →  repositories/ (DB access, ownership-scoped queries)
                       →  models/ (SQLAlchemy ORM)
```

- Routers must never contain business logic or raw queries — they validate input (via
  `schemas/`), call a service, and return its result.
- Services must never be bypassed. Anything that reads/writes financial data — including the AI
  tool catalog, reports, analytics, and NL search — goes through the same service layer that
  regular REST endpoints use. There must never be a second, divergent code path to the same
  numbers.
- Repositories are the only layer that talks to the ORM/DB and must always scope queries by
  `user_id` (see §10).

Architectural invariants established during design (do not silently change these):

- **Transfers** are a first-class `transactions.type = 'transfer'`, carrying `account_id` +
  `transfer_account_id`, excluded from income/expense/analytics **by query construction**, not by
  developer discipline.
- **Recurring generation** is idempotent, keyed by `(recurring_transaction_id, period)`.
- **Subscriptions** are a 1:1 extension of `recurring_transactions`, not a parallel scheduler.
- **Credit card fields** live in a 1:1 `credit_card_details` extension of `accounts`, not on the
  base account row.
- **Receipts** can exist before a transaction does (scan-first flow) — `transaction_id` is
  nullable with an explicit status.
- **Analytics/insights/reports/AI** are read-side consumers of the ledger. They compute on demand
  from indexed SQL for v1. A cache may be introduced later, but only inserted transparently behind
  the existing service-layer interface — never by adding a second source of truth.
- **v1 enforces one base currency per user.** Never silently sum or average across currencies.

---

## 5. Folder Structure

```
finance-app/
├── CLAUDE.md  README.md  ARCHITECTURE.md  API.md  DATABASE.md  SECURITY.md  AI.md  DEPLOYMENT.md
├── docker-compose.yml
├── .env.example
├── frontend/
│   ├── app/
│   │   ├── (marketing)/            # landing page
│   │   ├── (auth)/                 # login, register, reset
│   │   └── (app)/                  # dashboard, transactions, analytics, budgets, goals,
│   │                               # subscriptions, accounts, calendar, reports, ai, receipts, settings
│   ├── components/{ui,dashboard,transactions,budgets,goals,analytics,subscriptions,accounts,receipts,ai,charts}
│   ├── lib/                        # api client, money.ts, hooks, query client
│   ├── types/
│   └── tests/
├── backend/
│   ├── app/
│   │   ├── api/v1/                 # thin routers per resource
│   │   ├── models/                 # SQLAlchemy ORM
│   │   ├── schemas/                # Pydantic request/response
│   │   ├── services/               # business logic, money math, authorization
│   │   ├── repositories/           # DB access, ownership-scoped queries
│   │   ├── auth/
│   │   ├── ai/{provider,tools}/    # provider abstraction + fixed tool catalog
│   │   ├── analytics/              # single aggregation engine for dashboard/reports/AI
│   │   ├── jobs/                   # recurring generator, OCR, notifications
│   │   ├── storage/                # object storage abstraction
│   │   └── core/                   # config, security, db session, rate limiting
│   ├── migrations/                 # Alembic
│   └── tests/
└── scripts/
```

New top-level directories require a documented reason. New parallel implementations of something
that already exists (a second HTTP client, a second date-formatting util, a second money type)
are not permitted — extend or reuse what's there.

---

## 6. Coding Conventions

- Add types everywhere (TypeScript on the frontend, full type hints + Pydantic on the backend).
  No `any`, no untyped `dict` payloads for domain data.
- Validate all external input at the boundary (API request bodies, form input, imported files,
  query params) — never trust client-supplied data, including amounts and IDs.
- Keep files and components small and single-purpose. Split a component/service before it becomes
  a "god file."
- No dead code, no commented-out blocks, no speculative abstractions for features not yet built.
- **Inspect existing code before modifying it.** Understand why it's structured the way it is
  before changing it.
- **Never unnecessarily rewrite working code.** Prefer the smallest correct change over a
  rewrite; a rewrite requires an explicit reason (bug, requirement change, real duplication).
- **Reuse existing components/services/utilities.** Search before writing something new.
- No comments that restate what code does. Only comment the non-obvious *why* (a constraint, a
  workaround, an invariant a reader could otherwise violate).

---

## 7. Frontend Rules

- Mobile-first, but desktop is a first-class target — no "shrink the desktop layout" responsive
  design. Build layouts per breakpoint intentionally (see §17).
- Server components for initial data fetch; client components for interactive tables/forms/charts.
- All server state (fetching, caching, mutation, invalidation) goes through one data-fetching
  layer (React Query or equivalent) — no ad hoc `fetch` calls scattered through components.
- All money formatting/parsing goes through one shared utility (`lib/money.ts`). No component
  hand-rolls currency math or string formatting.
- Forms validate with a schema (Zod) that mirrors the backend Pydantic schema's constraints —
  client-side validation is a UX convenience, never a substitute for backend validation.
- Empty states, loading states (skeletons, not blank flashes or spinner overuse), and error states
  are mandatory for every data view — never ship a bare "No data" or a raw error string.
- Respect the component folder boundaries in §5 (`dashboard/`, `transactions/`, `budgets/`, …) —
  don't dump unrelated components into `ui/`.
- Accessibility is a requirement, not a nice-to-have: keyboard navigation, semantic HTML, labeled
  inputs, visible focus states, sufficient contrast, accessible modals and charts.

---

## 8. Backend Rules

- Business logic lives in `services/`, never in route handlers.
- One repository function = one clearly-scoped query. No building ad hoc queries inline in
  services when a repository method would express intent more clearly.
- Every service function that touches user-owned data takes an authenticated `user_id` and
  enforces ownership at the repository layer (see §10) — never trust a resource ID alone.
- Pydantic schemas (`schemas/`) are distinct from ORM models (`models/`) — never return an ORM
  object directly from an endpoint.
- Background work (OCR, AI summary generation, recurring-transaction generation, notification
  dispatch) runs through the job abstraction in `jobs/`, not inline in a request handler.
- If a required external integration (email provider, OAuth, SMS, object storage backend, AI
  provider) is not configured, implement a clean interface plus an explicit mock/demo
  implementation. Never pretend an unconfigured integration works.

---

## 9. Database Rules

- Fully normalized schema; every user-owned table has a `user_id` foreign key.
- Foreign keys are real FKs, not just convention. Cascade/restrict behavior is chosen deliberately
  per relationship (e.g., restrict category deletion while transactions reference it, or use
  `is_active` soft-delete — decide per entity and document it in `DATABASE.md`).
- Index every foreign key and every commonly filtered/sorted column (`transactions(user_id, date)`,
  `(user_id, category_id)`, `(user_id, account_id)`, `recurring_transactions.next_run_date`, etc.).
- All money columns are integer minor units (paise), e.g. `amount_minor BIGINT`. Never a `FLOAT`
  or `REAL` column for a money value.
- Schema changes go through Alembic migrations only — never hand-edit the schema or apply
  unmanaged DDL against a running database.
- Migrations must be reversible where feasible, and must not silently discard user data.

---

## 10. API Rules

- REST, versioned under `/api/v1/...`, resources grouped as in `PRODUCT_SPEC.md` §47.
- Consistent response envelope (`{ data, error, meta }`) and consistent error shape (`{ code,
  message, field_errors }`) across all endpoints.
- Every endpoint returning or mutating user-owned data must authenticate the caller and scope the
  query/mutation to that caller's `user_id`. This check happens at the repository layer so it
  cannot be forgotten per-endpoint — it is not acceptable to rely on every route handler
  remembering to filter correctly.
- Proper HTTP status codes (400 validation, 401 unauthenticated, 403 unauthorized, 404 not found,
  409 conflict, 422 unprocessable, 429 rate-limited, 5xx only for genuine server faults).
- Pagination on all list endpoints with an enforced max page size.
- `POST /transactions` (and other create endpoints used by offline/PWA sync) must accept an
  `Idempotency-Key` to make retried writes safe.
- Money fields are serialized as integers (minor units) or exact decimal strings in JSON — never
  as JSON floating-point numbers.

---

## 11. Authentication Rules

- Passwords hashed with a strong adaptive algorithm (Argon2id preferred, bcrypt acceptable) — never
  stored in plaintext, never logged.
- Access tokens are short-lived JWTs; refresh tokens are long-lived, stored httpOnly + secure,
  and backed by a `sessions` table so they can be individually revoked ("logout from all
  devices" must actually invalidate server-side state, not just clear a client cookie).
- Refresh tokens rotate on use; reuse of a rotated-out token is treated as a possible compromise.
- Email verification and password-reset tokens are single-use and time-limited.
- Google OAuth (or any other provider) is only wired up when actually configured — otherwise the
  option is hidden, never fake.
- Rate-limit login, registration, and password-reset endpoints.

---

## 12. Security Rules

- **Users can only ever access their own financial data.** No exceptions, no debug bypass, no
  "admin" shortcut without its own explicit authorization model.
- **Never hardcode secrets** — API keys, DB credentials, JWT signing keys, OAuth secrets, storage
  keys. All secrets come from environment variables (see §16). `.env` is never committed.
- **Never store passwords in plaintext.**
- Validate and sanitize all input; parameterize all queries (the ORM already does this — never
  drop to raw string-interpolated SQL).
- File uploads (receipts, imports) are validated by actual content, not just filename/extension,
  size-limited, and stored non-executable; served via signed URLs, not raw filesystem paths.
- CSRF protection on any cookie-authenticated mutating endpoint.
- Rate limiting on authentication and AI endpoints.
- Audit-log sensitive actions (login, password change, data export, account deletion) without
  ever logging secrets or full payloads of sensitive data.
- Treat all user-supplied text that will ever reach an LLM prompt (descriptions, merchant names,
  OCR output) as untrusted data, not instructions — see §14.
- Data export and account-deletion features must be fully and correctly scoped to the requesting
  user, with complete cascade on deletion.

---

## 13. Financial Calculation Rules

- **Never use floating-point numbers for money.** Store and compute in integer minor units
  (paise) or an exact `DECIMAL` type — end to end: database → backend → API → frontend.
- **Transfers between the user's own accounts must never count as income or expense** in any
  total, chart, budget, or AI answer. This is enforced by the `type='transfer'` model in §4, not
  by remembering to filter it out in each new query.
- Guard every division (budget %, savings rate, credit utilization, goal pacing) against
  divide-by-zero and negative/degenerate inputs.
- The **Financial Health Score is never randomly generated.** It is a deterministic function of
  documented factors (savings rate, budget adherence, debt burden, emergency fund, recurring
  ratio, spending consistency) computed from real stored data, and every score must be explainable
  (the "+ / -" reasons shown to the user must be the literal factors used in the calculation).
- Subscriptions/recurring costs use exactly **one** canonical monthly-equivalent normalization
  formula, reused everywhere that figure appears (subscription totals, health-score recurring
  ratio, dashboard) — never two different approximations of the same number.
- Expense-split remainder allocation (e.g., ₹2,401 ÷ 4) follows one documented deterministic rule
  — never silently drop or duplicate paise.
- Smart budget predictions and similar projections are explicitly labeled as estimates and never
  presented as guaranteed outcomes.
- Any new money-related calculation must be covered by a unit test before being considered done
  (see §18).

---

## 14. AI Rules

- **The AI must never have unrestricted database access** and must never execute arbitrary
  AI-generated SQL. All data access goes through a fixed, read-only, user-scoped **tool catalog**
  (`get_monthly_spending`, `get_category_spending`, `get_transactions`, `get_budget_status`,
  `get_savings_goals`, `get_recurring_expenses`, `get_account_balances`, `compare_periods`, …).
- Every tool function is backed by the **same service-layer function** used by the corresponding
  REST endpoint — the AI must never have its own divergent calculation path.
- Natural-language search compiles user phrasing into a **validated, allow-listed filter object**,
  which is then executed by the normal repository query builder. It never becomes free-text SQL.
- The AI must construct answers only from verified tool output. If the data needed to answer isn't
  available, it must say so explicitly ("I don't have enough data to answer that") rather than
  guess or fabricate a transaction, number, or trend.
- The AI must never present itself as a licensed financial advisor. For significant financial
  decisions it must show its assumptions and calculations, state its limitations, and avoid
  guaranteed-return language or unsafeguarded personalized investment advice.
- Treat all user-generated text that reaches an LLM prompt (transaction descriptions, merchant
  names, OCR-extracted text) as data, never as instructions — guard against prompt injection when
  assembling context.
- Respect the per-user AI setting: when a user disables AI access to their data, the tool layer
  itself must refuse tool calls for that user — not just hide the chat UI.
- When no AI provider is configured, use the mock/demo provider and say so clearly. Never
  fabricate an AI response to look real.

---

## 15. Testing Rules

- Every important business-logic path needs a test before the feature is considered done:
  authentication, transactions, budgets, goals, recurring expenses, transfers, analytics,
  authorization, and all money calculations.
- Money-calculation tests are mandatory for: totals, budget percentages, savings rate, net worth,
  credit utilization, recurring/subscription normalization, and split remainder allocation.
- Authorization tests must include a negative case per user-owned entity: user A must not be able
  to read, modify, or delete user B's data via the API.
- Frontend tests cover forms, navigation, transaction creation, filters, and responsive layout at
  minimum for critical flows.
- Run the relevant test suite (and type checks) before declaring any task complete. Fix failures
  before moving on — do not ship a task with known-broken tests.

---

## 16. Environment-Variable Rules

- All secrets and environment-specific config (DB URL, JWT signing key, AI provider API keys,
  OAuth client secrets, object-storage credentials) come from environment variables, loaded via
  `.env` locally.
- `.env` is never committed. `.env.example` is kept up to date with every variable the app needs,
  with placeholder (non-real) values and a comment on what each one is for.
- Code must fail with a clear startup error if a required variable is missing — never silently
  fall back to a hardcoded secret or a production credential baked into source.

---

## 17. Error-Handling Rules

- Never surface raw exceptions, stack traces, or bare HTTP status text to the user
  (e.g. no "500 Internal Server Error" in the UI).
- User-facing errors are specific and actionable: "Amount must be greater than ₹0," not "Invalid
  input." "Something went wrong while loading your transactions. Please try again," not a raw
  error code.
- Backend errors are logged with enough context to debug (request id, user id, operation) without
  logging secrets or full sensitive payloads.
- Distinguish validation errors (4xx, field-level messages) from genuine server faults (5xx) —
  don't collapse both into the same generic message.
- Every network/async operation on the frontend has a defined loading state and a defined error
  state; neither is optional.

---

## 18. Responsive-Design Rules

- Build real responsive layouts per breakpoint (mobile, tablet, laptop, desktop, large monitor) —
  not a single desktop layout that shrinks.
- Mobile: bottom navigation (Home, Transactions, Add, Analytics, More), with the Add action always
  immediately reachable — recording an expense must take a few seconds.
- Desktop: sidebar navigation, multi-column dashboard, keyboard shortcuts, richer analytics.
- Every screen in `PRODUCT_SPEC.md` §6 must be verified at mobile and desktop widths before being
  considered done.

---

## 19. Git Rules

- Meaningful, conventional commit messages (`feat: add transaction management`,
  `fix: correct transfer calculations`, `refactor: improve transaction service`) — no
  meaningless or placeholder commit messages.
- Commit at the granularity of a coherent unit of work, not every file save.
- Never force-push or rewrite shared history without explicit user approval.
- Never commit `.env` or any file containing real secrets.

---

## 20. Absolute Rules (repeated for emphasis — never violate)

- Never hardcode secrets.
- Never store passwords in plaintext.
- Never use floating-point numbers for money.
- Users must only access their own financial data.
- Transfers must not count as income or expenses.
- AI must not have unrestricted database access.
- AI must use controlled tools/functions — never execute arbitrary AI-generated SQL.
- Never create fake functionality. If an integration isn't configured, build a clean abstraction
  with an explicit mock/demo mode instead of pretending it works.
- Never unnecessarily rewrite working code.
- Always inspect existing code before modifying it.
- Keep files modular — no god files, no god components.
- Keep the application runnable after every major phase.

---

## 21. Development Phases

Work through these phases sequentially. Only implement the phase currently requested; do not
jump ahead. The application must remain runnable at the end of every phase.

1. **Foundation** — repo scaffolding, environment configuration, Postgres + Alembic setup,
   `users` / `sessions` / `audit_logs` / `user_settings` tables, full authentication
   (register, login, logout, email verification, password reset, session management), base
   layout + theme + landing page shell.
2. **Core ledger** — accounts (including credit card extension), categories (seeded defaults +
   custom), transactions CRUD with correct transfer handling, dashboard v1 built on real
   aggregates only.
3. **Planning** — budgets + smart budget prediction, savings goals, recurring-transaction engine,
   subscriptions (built on the recurring engine), notifications for budget/renewal/goal events.
4. **Insight** — analytics (all charts backed by real queries), financial health score + spending
   insights, financial calendar, reports (PDF/CSV/Excel export), net worth tracking, CSV/Excel
   import with dedup.
5. **AI & documents** — receipt OCR + storage, AI financial assistant + tool catalog, natural-
   language search, AI-generated financial summaries.
6. **Hardening** — full security pass (rate limiting, CSRF, audit-log review, cross-user-access
   tests for every entity), complete test suite, performance work (query/index review, caching
   only where justified, pagination), PWA/offline queue, expense splitting, gamification,
   financial calculator toolbox, deployment documentation.

---

*This file should be updated whenever a durable engineering decision is made — a new architectural
invariant, a reversed decision, a newly adopted convention. It should not be updated with
transient task status; use the conversation/plan for that.*
