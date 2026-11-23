# Testing

What the test suites cover, how they're organized, and how to run them. Counts come from actual
runs, not estimates. The per-section breakdowns were counted on 2026-09-28; files added since then
are listed with their own counts, and [Current results](#current-results) is the latest full run.

## Test stack

| Layer | Tools | Location |
|---|---|---|
| Backend | pytest, pytest-asyncio (`asyncio_mode=auto`), httpx `AsyncClient` over `ASGITransport` (no network), real PostgreSQL test database | `backend/tests/` (52 files) |
| Frontend | Vitest 5, jsdom, React Testing Library, `@testing-library/jest-dom`, `fake-indexeddb` | `frontend/tests/` (41 files) |
| Static checks | mypy (`disallow_untyped_defs`), ruff (E, F, I, UP, B, SIM), `tsc --noEmit`, ESLint (`eslint-config-next`) | configured in `backend/pyproject.toml` and `frontend/` |
| E2E / browser | **None committed.** `playwright` is a devDependency and was used for one-off screenshot checks of the landing page (`frontend/playwright-artifacts/`, gitignored), but there's no Playwright config or E2E test suite in the repo. | none |

## Commands

```bash
# Backend. Needs PostgreSQL and TEST_DATABASE_URL in backend/.env, migrated to head.
cd backend
ALEMBIC_DATABASE_URL="<test db url>" .venv/Scripts/alembic upgrade head   # one-time, and after new migrations
.venv/Scripts/python -m pytest                        # full suite
.venv/Scripts/python -m pytest tests/test_transactions.py -k transfer   # one area
.venv/Scripts/python -m ruff check app tests
.venv/Scripts/python -m mypy app
.venv/Scripts/alembic check                           # models vs. migrations drift check (uses DATABASE_URL)

# Frontend
cd frontend
npm run test          # vitest run
npx vitest run tests/money.test.ts   # one file
npm run typecheck     # tsc --noEmit
npm run lint          # eslint
npm run build         # production build
```

## How the backend suite is built

`backend/tests/conftest.py` provides:

- **An isolated test database.** `TEST_DATABASE_URL` is a separate database from dev. `get_db` is
  overridden for the whole app.
- **Cleanup after every test (autouse).** It runs `DELETE FROM audit_logs` and
  `DELETE FROM users`, and the `ON DELETE CASCADE` foreign keys remove all user-owned rows. It
  deletes rather than truncates on purpose: `TRUNCATE ... CASCADE` would also wipe the
  migration-seeded system categories. Because this fixture is autouse, **every** backend test,
  including the pure unit tests, needs the test database to be reachable.
- **Rate-limiter reset (autouse)**, so limits from one test don't leak into the next.
- `client`: an httpx client that calls the real ASGI app, going through middleware, routing,
  validation, services, and SQL.
- `db_session`: a raw session for calling services or jobs that have no endpoint (e.g. the
  system-wide recurring sweep).
- `auth_headers` / `other_auth_headers`: two independently registered users, used for
  authorization tests.

### Unit tests (pure functions, no API/DB fixture)

Money, date, and parsing rules are kept in DB-free modules so they can be tested with plain
values. For example:

| Module | Test file | What's pinned down |
|---|---|---|
| `services/budget_calculations.py` | `test_budget_calculations.py` (17) | Exact status thresholds at 69.9/70/89.9/90/99.9/100%; projection rounding; divide-by-zero guard on 0 days elapsed |
| `services/savings_goal_calculations.py` | `test_savings_goal_calculations.py` (18) | Progress rounding; remaining never negative; required pace is `None` (not a guess) when the target date is today or past; completed goal gives 0 |
| `services/recurrence.py` | `test_recurrence.py` (18) | Jan 31 → Feb 28/29; stays anchored to the 31st after February; Feb 29 yearly schedule across leap and non-leap years; year rollover |
| `services/subscription_calculations.py` | `test_subscription_calculations.py` (21) | The canonical monthly/yearly normalization for every frequency, with rounding; unused-subscription evidence at the exact 60-day and 90-day boundaries |
| `services/analytics_calculations.py` | `test_analytics_calculations.py` (30) | Range presets across year boundaries; day/month granularity at exactly the threshold; trend direction with zero and negative baselines |
| `services/ledger_calculations.py` | `test_ledger_calculations.py` (101) | Every account type × leg (income, expense, transfer source/destination): assets store the cash-flow delta, credit cards store the amount owed; card purchases cut net worth, refunds raise it, and every transfer (repayment, cash advance, card → card, asset → asset) is net-worth neutral |
| `services/health_score.py` | `test_health_score.py` (18) | Deterministic score; `None` with no data; weights redistributed when a factor doesn't apply; worst card (not average) for debt; an over-limit card (120%) floors the debt factor at 0 and reports the literal 120%; 0–100 bounds |
| `services/calendar_calculations.py`, `quick_add_parser.py`, `export_formatting`/`export_service.py`, `merchant_normalization.py` | respective files | Calendar projection, quick-add amount/category parsing, CSV/XLSX/PDF rendering, merchant key normalization |
| `search/*` | `test_search_interpreter.py` (43), `test_search_schema_validation.py` (43), `test_search_period_phrases.py` (24), `test_search_query_builder.py` (11), `test_search_category_resolution.py` (8) | Natural-language text compiles only into the allow-listed filter schema; invalid or out-of-range filters are rejected |
| `ai/*` | `test_ai_classifier.py` (79), `test_ai_period_resolution.py` (19), `test_ai_mock_intents.py` (18), `test_ai_calculations.py` (8) | Classifier output validation, period resolution, mock-provider intents |
| `sync/provider/*` | `test_sync_provider.py` (31) | Mock/sandbox provider contract |
| `core/security.py`, `core/logging.py`, `core/config.py` | `test_security.py` (8), `test_core_logging.py` (4) | Argon2 hashing and verification, JWT type checks, log formatting; a `*` in `CORS_ORIGINS` is refused in production |
| `services/account_service.py` card figures | `test_credit_card_figures.py` (21) | Utilization (0% for a credit balance, 120% reported unclamped when over the limit, divide-by-zero guard); available credit never negative and above the limit for an overpaid card; over-limit amount only the overshoot; available and over-limit never both non-zero |
| `docs/DEPLOYMENT.md` (F-001 runbook) | `test_f001_deployment_runbook.py` (9) | The lockstep runbook still carries every safeguard the migration depends on: each of the migration's three blocker names is documented; the resume gate names the live-commit, deploy-status and health checks and refuses an unconditional resume; the limits of manual-edit detection and the reconciliation procedure for skipped cards are present; and the verified Render facts (free plan, maintenance mode paid-only, the ~90 s old-instance overlap) replace the claim they corrected |

### Integration tests (real HTTP → service → PostgreSQL)

Each resource has a `test_<resource>.py` that drives the real endpoints and checks the JSON
envelope and the resulting database state. For example:

- `test_transactions.py` (48): balance effects of create, edit, delete, and duplicate; transfers
  move money between accounts and are excluded from income/expense; idempotency keys, including
  a **concurrent** double-submit and a forced race on the DB constraint; filters, sort, and
  pagination.
- `test_recurring_transactions.py` (39): catch-up generation, running twice is a no-op, archived
  accounts, and the system-wide sweep.
- `test_credit_card_ledger.py` (20, added 2026-11): a card expense raises the amount owed,
  utilization and the net-worth drop; a refund lowers what is owed; a bank → card repayment lowers
  both balances, leaves net worth unchanged and is neither income nor expense; cash advances and
  card → card transfers are neutral; overpayment leaves a credit balance; edits (amount, bank ↔
  card, expense ↔ transfer, expense → refund), deletes (including on an archived card),
  duplicates, idempotent replay, recurring and receipt transactions on a card; cross-user
  repayment is rejected.
- `test_account_balance_audit.py` (6, added 2026-11): a `PUT /accounts` balance change writes an
  `account.balance_updated` audit row with the previous and new value; unchanged balances, other
  field edits and ledger writes don't.
- `test_reports.py` (17) and `test_report_exports.py` (8): hand-calculated monthly and yearly
  figures, leap-year February, net-worth reconstruction in which a card repayment is neutral and
  card spending and refunds move the trend in the month they happen, and real CSV/XLSX/PDF output.
- `test_f001_card_ledger_impact_check_sql.py` (12): both operator scripts
  (`scripts/sql/f001_card_ledger_impact_check.sql`, `f001_card_ledger_post_migration_check.sql`)
  contain only `SELECT`s, transaction control and `SET LOCAL` timeouts, and run cleanly against
  the migrated schema; the impact check's summary and per-card parts share one definition; Part 1
  matches hand-computed figures (distinct transactions vs legs, per-currency correction totals,
  positive/negative counts) and counts the cards the migration would refuse or flag, including
  cards the fixed code has touched since the revision's first run (and zero of them on a database
  where it has never run).
- `test_migration_card_balance_correction.py` (19, added 2026-11-22): migration `c8e4a1f6b2d9`
  on data seeded as the pre-fix backend booked it. With nothing to correct it runs without a flag
  and only writes a summary row; otherwise it refuses without `apply` and changes nothing;
  `apply` corrects each card by `−2·D`, matching the impact check, audits it and never touches
  transactions; a currency mismatch or a post-fix balance edit blocks until skipped; bad options
  are refused; downgrade needs `revert`, reverts exactly the recorded correction, refuses a
  balance set by hand afterwards, and never reverts twice. A re-upgrade after a downgrade refuses
  any card the fixed backend has booked a leg on since the first run (otherwise D would absorb it
  and move the balance by twice its amount), including a card first used after a `mode: none` run
  on a database with no cards. That guard reads two independent records, so it still refuses with
  `audit_logs` purged and still refuses with the `data_correction_runs` rows deleted; with both
  destroyed it is blind, which one test pins deliberately. The run record survives a downgrade,
  is recreated if missing, and `alembic check` must stay clean because the table is created with
  raw idempotent DDL and declared by `app/models/data_correction_run.py`.
- `test_duplicate_write_recovery.py` (6): a duplicate notification, or a racing
  `Idempotency-Key`, rolls back only its own SAVEPOINT, so rows created earlier in the same
  request survive and balances stay consistent. The tests fail against the old full `rollback()`.
- `test_receipts.py` (33): includes
  `test_a_racing_receipt_transaction_books_the_expense_only_once`; a client `Idempotency-Key` in
  the reserved `server:` namespace (any letter case) is a 422 and books nothing; the pre-fix
  `receipt:<id>` spelling no longer hijacks the receipt; a key past the 100-character column is
  a 422, not a 500; an ordinary client key still replays; and deleting a receipt's transaction
  lets the receipt book again, once.
- `test_money_limits.py` (35): every money field on every request model has an upper bound (the
  models are discovered automatically, and a guard test fails if discovery finds none), and the
  API returns 422 rather than storing or overflowing a transaction, balance (both directions),
  credit limit or goal target past `MAX_MONEY_MINOR`; the ceiling itself is accepted.
- `test_request_id.py` (27): every response carries an `X-Request-Id`: success, 401, validation
  errors, an unhandled 500 (with the security headers too), and allowed and refused CORS
  preflights. Each request gets its own id; a well-formed proxy id is reused, including on a 500;
  the 500's logged traceback carries the same id as its header; hostile inbound ids are dropped
  and never echoed; `app.*` log records carry the current id.
- `test_ai_assistant_service.py` (16): includes the mock balances answer describing a card as
  owed or credit balance, with available credit and any over-limit amount, never a negative figure.
- `test_account_deletion.py` (8): deleting an account removes every row of every table with a
  `user_id` (found from the live schema, so new tables are covered) and nothing of another
  user's; audit rows keep their action and lose IP, user agent and metadata; a wrong password
  deletes nothing; the user is signed out everywhere; receipt files leave storage; the email can
  register again; the target is always the caller.
- `test_body_limit.py` (4): a declared oversized body is refused before it is read, a streamed one
  is cut off, both as a 413 envelope with a request id, and a maximum-size receipt still fits.
- `test_export_formatting.py` (34): `format_money` prints INR to the exact paisa at zero, one
  paisa, negatives and ±`MAX_MONEY_MINOR`, matching exact `Decimal` arithmetic across the whole
  accepted range.
- `test_search_api.py` (22): includes amount filters, where a normal amount still works, the
  `MAX_MONEY_MINOR` ceiling itself is searchable, anything past it (including past BIGINT) is a
  specific 422 rather than a 500, and a minus sign never becomes a negative filter.
- `test_sync_service.py` (70), `test_notifications.py` (45), `test_ai_tools.py` (26, including
  over-limit card figures in `get_account_balances`),
  `test_auth.py` (26), and the rest.

### Authorization and isolation tests

CLAUDE.md §15 requires a negative case per user-owned entity. **76 tests** take the
`other_auth_headers` fixture and check that user B gets a 404 (or an empty result) for user A's
accounts, categories, transactions, budgets, goals, recurring transactions, subscriptions,
receipts, notifications, settings, merchant rules, linked accounts, and search results. There are
also dedicated isolation tests written without the fixture:

- `test_ai_tools.py::test_cross_user_isolation_for_every_tool`: every AI tool, scoped to its caller.
- `test_dashboard.py::test_dashboard_is_isolated_per_user`,
  `test_analytics.py::test_analytics_never_leaks_another_users_data`,
  `test_report_exports.py::test_export_never_leaks_another_users_data`.
- Transfers: `test_transfer_destination_belonging_to_another_user_is_not_found` and
  `..._source_...`.
- `test_idempotency_key_is_scoped_per_user_never_shared`, and
  `test_quick_add_parse_never_matches_another_users_custom_category`.

### Financial calculation tests

Every money figure has a test with a hand-computed expected value: totals, budget percentages
(`test_budget_calculations.py`, `test_budgets.py`), savings rate
(`test_dashboard.py::test_income_expense_savings_and_savings_rate_this_month`,
`test_reports.py::test_savings_report_never_fabricates_a_rate_with_zero_income`), net worth
(`test_dashboard.py::test_total_balance_excludes_credit_card_and_net_worth_subtracts_debt`,
`test_reports.py::test_net_worth_report_*`), credit utilization
(`test_accounts.py::test_credit_card_utilization_*`, including 0% for a credit balance), available
credit and the over-limit amount (`test_credit_card_figures.py`), the
credit-card ledger (`test_ledger_calculations.py`, `test_credit_card_ledger.py`), card dues
(`test_dashboard.py::test_upcoming_credit_card_payment_amount`), subscription normalization
(`test_subscription_calculations.py`), goal pacing, and balance ledger effects
(`test_transactions.py`).

**Not covered, because the feature doesn't exist yet:** expense-split remainder allocation.
There's no split feature in the codebase.

### Edge-case tests

Examples, by category:

- **Zero and empty:** zero income gives a `None` savings rate, not 0% or ∞; a brand-new user's
  dashboard; an empty month's reports; an empty export has no fake rows.
- **Boundaries:** budget thresholds at exactly 70/90/100%; subscription lookback windows at
  exactly the boundary; analytics granularity at exactly 62 days.
- **Calendar:** month-end clamping, leap years, and year rollover (`test_recurrence.py`,
  `test_analytics_calculations.py`, `test_reports.py::test_monthly_report_handles_a_leap_year_february`).
- **Timezone:** `test_calendar.py::test_a_transaction_at_midnight_utc_stays_on_its_own_calendar_day`,
  and `test_search_results.py::test_weekend_day_of_week_filter_correct_under_non_utc_session_timezone`,
  which runs the query with the Postgres session set to UTC+14.
- **Concurrency:** `test_concurrent_idempotent_requests_never_create_two_transactions`,
  `test_service_handles_true_toctou_race_on_the_db_constraint`.
- **Invalid input:** zero or negative amounts, a transfer to the same account, currency
  mismatch, archived accounts, unknown categories, receipt file type checked by content, oversized
  uploads.

### Database testing

- Tests run against real PostgreSQL, not SQLite, so CHECK constraints, partial unique indexes,
  `timestamptz`, `date_trunc(..., 'UTC')`, and array overlap behave exactly as in production.
- The test DB schema comes from the real Alembic migrations (`alembic upgrade head`), so the
  migrations themselves get exercised.
- `alembic check` compares the ORM models against the migrated schema to catch drift.
- `test_rls_hardening.py` (26) covers migration `d7a1e4c9b3f2`. At head: RLS on every
  `public` table (so a future table without it fails), every model table included, no FORCE, no
  policies, the backend role owns every table and still reads and writes. Also: a single
  Alembic head, a plain downgrade that keeps the protection, `revert` that disables RLS but never
  re-grants, idempotent re-runs, mistyped flags refused, and offline SQL rendering refused. A
  lock held by another session makes the migration fail within its 10 s lock timeout and change
  nothing; no function may live in `public`; and `scripts/sql/public_schema_exposure_check.sql`
  reports a clean head.
  - **With Supabase's `anon`/`authenticated` roles** (9 tests): the fixture reproduces the
    production finding (every grant, default privileges, RLS off) and proves `anon` can read
    `users`. After the upgrade, every privilege is gone, both roles get "permission denied" on
    SELECT/UPDATE/TRUNCATE, RLS still hides rows if a grant is restored by mistake, new tables
    aren't granted, and a non-owner migrating role is refused before any change.
  - These need a role that can create roles. They skip on a local database where the test role
    can't, and **fail instead of skipping** when `REQUIRE_SUPABASE_ROLE_TESTS=1`, which CI sets
    (CI's PostgreSQL user is a superuser). Locally, run them against a throwaway cluster:
    `initdb -U ci_super --auth=trust`, start it on a spare port, `createdb finance_app_test`,
    then point `DATABASE_URL`/`TEST_DATABASE_URL`/`ALEMBIC_DATABASE_URL` at it with
    `REQUIRE_SUPABASE_ROLE_TESTS=1`.
- `tests/alembic_runner.py` is the one subprocess helper both migration test files use.

## Frontend tests: 427 tests in 57 files

| Area | Files |
|---|---|
| Money utility | `money.test.ts` (paise ⇄ display formatting and parsing; amounts above `MAX_MONEY_MINOR` rejected) |
| Transaction entry | `add-expense-sheet`, `transaction-form`, `transaction-row` |
| Feature helpers (`lib/`) | `analytics`, `goals`, `receipts`, `recurring-transactions`, `subscriptions`, `theme` |
| Calendar and reports | `calendar-grid`, `day-detail-modal`, `month-navigator`, `report-controls`, `report-type-tabs`, `category-items-list`, `export-buttons` |
| AI and search | `ai-assistant-page`, `chat-input`, `chat-message-bubble`, `suggested-questions`, `natural-language-search` |
| Settings, sync, notifications | `settings-page`, `preferences-section`, `security-section`, `notifications-section`, `connected-accounts-page`, `linked-account-card`, `merchant-rules-page`, `notification-bell` |
| Accounts | `credit-card-balance` (card balance shown as owed or credit balance, utilization bar clamped to 0–100%, "Amount owed" form label, credit balance in the net-worth report, zero available credit plus the overshoot for an over-limit card, never a negative available credit) |
| Navigation and responsive shell | `mobile-bottom-nav`, `landing-nav`, `landing-page`, `faq-section`, `button` |
| Offline / PWA | `offline-db`, `offline-sync-queue`, `sync-status-indicator`, `pwa-manifest` |
| Error states | `error-boundaries` (see below); inline error and empty states inside `connected-accounts-page`, `merchant-rules-page`, `notification-bell`, `ai-assistant-page`, and others |

### Error-state testing

- **Backend:** each resource test asserts the 422 `field_errors`, the 404 for missing or
  cross-user resources, and the 409 conflicts. `test_rate_limiting.py` produces real 429s.
  `test_auth.py` covers 401 paths.
- **Frontend:** `error-boundaries.test.tsx` checks that the route boundaries never display the
  raw error message, call `retry`, log the error, and link to a safe page. Component tests mock
  `lib/*` calls to reject and assert the friendly inline message. See
  [ERROR_HANDLING.md](ERROR_HANDLING.md).

## Testing matrix

✅ = verified present in the repository · ◐ = partial (details in the note) · — = none

"Unit" means pure-function backend tests. "Integration" means HTTP → DB tests. "Isolation" means
cross-user negative tests. "Frontend" means Vitest component or lib tests. **E2E is — for every
row**, because there's no committed browser test suite.

| Module | Unit | Integration | Isolation | Edge cases | Frontend | E2E |
|---|---|---|---|---|---|---|
| Auth / sessions | ✅ `test_security` | ✅ `test_auth` | ✅¹ | ✅ refresh-token reuse, rate limit | ◐² | — |
| Accounts / credit cards | ✅ `test_ledger_calculations`³ | ✅ | ✅ | ✅ utilization edges, credit balance, archive | ✅ | — |
| Categories | — | ✅ | ✅ | ✅ duplicates, concurrent create | — | — |
| Transactions / transfers | ✅ quick-add parser | ✅ | ✅ | ✅ races, idempotency, currency | ✅ | — |
| Dashboard / health score | ✅ `test_health_score` | ✅ | ✅ | ✅ | — | — |
| Budgets | ✅ | ✅ | ✅ | ✅ thresholds | — | — |
| Savings goals | ✅ | ✅ | ✅ | ✅ past/today target | ✅ `goals.test.ts` | — |
| Recurring transactions | ✅ `test_recurrence` | ✅ | ✅ | ✅ month-end, leap, race | ✅ lib | — |
| Subscriptions | ✅ | ✅ | ✅ | ✅ lookback boundaries | ✅ lib | — |
| Analytics | ✅ | ✅ | ✅ | ✅ ranges, trends | ✅ lib | — |
| Calendar | ✅ | ✅ | ✅ | ✅ midnight UTC | ✅ | — |
| Reports + exports | ✅ `test_export_service` | ✅ | ◐⁴ | ✅ leap Feb, empty | ✅ | — |
| Receipts / OCR | ✅ OCR text extraction | ✅ | ✅ | ✅ content/extension mismatch, oversized | ✅ | — |
| AI assistant + tools | ✅ | ✅ | ✅ every tool | ✅ | ✅ | — |
| NL search | ✅ | ✅ | ✅ | ✅ non-UTC session | ✅ | — |
| Notifications | — | ✅ | ✅ | ✅ | ✅ | — |
| User settings | — | ✅ | ✅ | ✅ | ✅ | — |
| Bank sync / linked accounts | ✅ provider | ✅ | ✅ | ✅ dedupe, consent | ✅ | — |
| Merchant rules | ✅ normalization | ✅ | ✅ | ✅ messy narrations, unknown merchants | ✅ | — |
| Security headers / rate limits | — | ✅ | n/a | ✅ | n/a | — |
| Error boundaries (frontend) | n/a | n/a | n/a | ✅ | ✅ | — |
| Offline queue / PWA | n/a | n/a | n/a | ✅ | ✅ | — |

1. `test_list_sessions_never_returns_another_users_sessions` and
   `test_logout_all_does_not_affect_another_users_sessions`. These build the second user inline
   rather than through the `other_auth_headers` fixture.
2. The login and register pages have no direct component tests. Only their links from the
   landing page and nav are tested.
3. Credit-utilization edge cases are assertions inside `test_accounts.py`; the per-type ledger
   rule has its own pure unit tests in `test_ledger_calculations.py`.
4. `test_report_exports.py::test_export_never_leaks_another_users_data` covers exports, but the
   eight JSON `GET /reports/*` endpoints have no cross-user test of their own. They call the same
   service functions the export test exercises.

## Current results

Run on 2026-11-22, branch `fix/credit-card-ledger-semantics` (uncommitted working tree),
Windows 11, Python 3.13, Node 24, local PostgreSQL 18. Alembic was checked against the local test
database. The dev database is deliberately left behind, at `a3f9c1d2e7b4`, until
`c8e4a1f6b2d9` and `d7a1e4c9b3f2` are approved. The backend suite was run twice: against the local
test database, and against a throwaway superuser cluster that mirrors CI, with
`REQUIRE_SUPABASE_ROLE_TESTS=1`, in an environment installed fresh from
`requirements.lock` (the dependency set CI and Render install). Each of the seven proposed
intermediate commits was also built from `git archive HEAD` plus its files and its suite run on
its own database: c1 1335, c2 1449, c3 1463, c4 1466, c5 1497, c6 1523 and c7 1534 passed, with
0 failures and 0 skips.

| Check | Result |
|---|---|
| Backend pytest, CI parity (superuser cluster, role tests required, lockfile environment) | **1534 passed**, 0 failed, 0 skipped, 1 warning (third-party `passlib` argon2 deprecation), 304 s |
| Backend pytest, local test DB | **1525 passed**, 9 skipped (exactly the Supabase-role RLS tests, which this test role can't run), 0 failed, 301 s |
| Frontend vitest | **427 passed**, 0 failed, 57 files |
| mypy (`app`) | Success: no issues in 184 source files |
| ruff check (`app tests migrations`) | All checks passed |
| `npm run typecheck` (`next typegen && tsc --noEmit`) | no errors, including on a clean checkout with no generated types |
| ESLint | no errors or warnings |
| `next build` (Turbopack, Next 16.4.6) | compiled; 24 static pages generated |
| `npm audit` | 0 vulnerabilities |
| `pip-audit` (installed backend environment, as in CI) | No known vulnerabilities (after raising the `pyjwt`, `pypdf`, `pillow`, `dnspython` and `certifi` floors, and upgrading pip itself) |
| Browser smoke (Playwright, production build, throwaway DB) | 13 app pages at 390 px and 1440 px: no console errors, page errors, 5xx responses or horizontal overflow; account deletion end to end |
| `alembic heads` / `current` / `check` | single head `d7a1e4c9b3f2`; test DB at head; "No new upgrade operations detected" (models match migrations) |

`ruff format` isn't part of the project's checks. Running `ruff format --check app` reports 16
pre-existing files that would be reformatted, so it isn't a gate today.

## Known testing gaps

- No E2E/browser test suite. Critical flows (sign up, add an expense, see it on the dashboard)
  are covered only in pieces, by API integration tests and component tests.
- No frontend tests for the login/register pages, categories, budgets, or dashboard components.
  Accounts are covered only for credit-card balance display and the account form's balance field.
- No cross-user test for the JSON report endpoints (see note 4 above).
- No coverage measurement is configured (neither `pytest-cov` nor Vitest coverage), so there are
  no coverage percentages to report.
- Responsive layout is checked only through component tests of the nav, not at real
  breakpoints.
