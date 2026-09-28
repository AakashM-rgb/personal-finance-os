# Testing

What the test suites cover, how they're organized, and how to run them. Counts come from actual
runs on 2026-09-28 (see [Current results](#current-results)), not estimates.

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

### Unit tests (pure functions, no API/DB fixture): 475 tests

Money, date, and parsing rules are kept in DB-free modules so they can be tested with plain
values. For example:

| Module | Test file | What's pinned down |
|---|---|---|
| `services/budget_calculations.py` | `test_budget_calculations.py` (17) | Exact status thresholds at 69.9/70/89.9/90/99.9/100%; projection rounding; divide-by-zero guard on 0 days elapsed |
| `services/savings_goal_calculations.py` | `test_savings_goal_calculations.py` (18) | Progress rounding; remaining never negative; required pace is `None` (not a guess) when the target date is today or past; completed goal gives 0 |
| `services/recurrence.py` | `test_recurrence.py` (18) | Jan 31 → Feb 28/29; stays anchored to the 31st after February; Feb 29 yearly schedule across leap and non-leap years; year rollover |
| `services/subscription_calculations.py` | `test_subscription_calculations.py` (21) | The canonical monthly/yearly normalization for every frequency, with rounding; unused-subscription evidence at the exact 60-day and 90-day boundaries |
| `services/analytics_calculations.py` | `test_analytics_calculations.py` (30) | Range presets across year boundaries; day/month granularity at exactly the threshold; trend direction with zero and negative baselines |
| `services/health_score.py` | `test_health_score.py` (17) | Deterministic score; `None` with no data; weights redistributed when a factor doesn't apply; worst card (not average) for debt; 0–100 bounds |
| `services/calendar_calculations.py`, `quick_add_parser.py`, `export_formatting`/`export_service.py`, `merchant_normalization.py` | respective files | Calendar projection, quick-add amount/category parsing, CSV/XLSX/PDF rendering, merchant key normalization |
| `search/*` | `test_search_interpreter.py` (43), `test_search_schema_validation.py` (29), `test_search_period_phrases.py` (24), `test_search_query_builder.py` (11), `test_search_category_resolution.py` (8) | Natural-language text compiles only into the allow-listed filter schema; invalid or out-of-range filters are rejected |
| `ai/*` | `test_ai_classifier.py` (79), `test_ai_period_resolution.py` (19), `test_ai_mock_intents.py` (17), `test_ai_calculations.py` (8) | Classifier output validation, period resolution, mock-provider intents |
| `sync/provider/*` | `test_sync_provider.py` (31) | Mock/sandbox provider contract |
| `core/security.py`, `core/logging.py` | `test_security.py` (5), `test_core_logging.py` (4) | Argon2 hashing and verification, JWT type checks, log formatting |

### Integration tests (real HTTP → service → PostgreSQL): 591 tests

Each resource has a `test_<resource>.py` that drives the real endpoints and checks the JSON
envelope and the resulting database state. For example:

- `test_transactions.py` (48): balance effects of create, edit, delete, and duplicate; transfers
  move money between accounts and are excluded from income/expense; idempotency keys, including
  a **concurrent** double-submit and a forced race on the DB constraint; filters, sort, and
  pagination.
- `test_recurring_transactions.py` (39): catch-up generation, running twice is a no-op, archived
  accounts, and the system-wide sweep.
- `test_reports.py` (16) and `test_report_exports.py` (8): hand-calculated monthly and yearly
  figures, leap-year February, net-worth reconstruction including transfers into a credit card,
  and real CSV/XLSX/PDF output.
- `test_sync_service.py` (70), `test_notifications.py` (45), `test_ai_tools.py` (25),
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
(`test_accounts.py::test_credit_card_utilization_*`), subscription normalization
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

## Frontend tests: 256 tests in 41 files

| Area | Files |
|---|---|
| Money utility | `money.test.ts` (paise ⇄ display formatting and parsing) |
| Transaction entry | `add-expense-sheet`, `transaction-form`, `transaction-row` |
| Feature helpers (`lib/`) | `analytics`, `goals`, `receipts`, `recurring-transactions`, `subscriptions`, `theme` |
| Calendar and reports | `calendar-grid`, `day-detail-modal`, `month-navigator`, `report-controls`, `report-type-tabs`, `category-items-list`, `export-buttons` |
| AI and search | `ai-assistant-page`, `chat-input`, `chat-message-bubble`, `suggested-questions`, `natural-language-search` |
| Settings, sync, notifications | `settings-page`, `preferences-section`, `security-section`, `notifications-section`, `connected-accounts-page`, `linked-account-card`, `merchant-rules-page`, `notification-bell` |
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
| Accounts / credit cards | ◐³ | ✅ | ✅ | ✅ utilization edges, archive | — | — |
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
3. Credit-utilization edge cases are pure assertions inside `test_accounts.py`.
4. `test_report_exports.py::test_export_never_leaks_another_users_data` covers exports, but the
   eight JSON `GET /reports/*` endpoints have no cross-user test of their own. They call the same
   service functions the export test exercises.

## Current results

Run on 2026-09-28, branch `feat/automatic-transaction-sync`, Windows 11, Python 3.13.13,
Node 24.14.0, local PostgreSQL:

| Check | Result |
|---|---|
| Backend pytest | **1066 passed**, 0 failed, 1 warning (third-party `passlib` argon2 deprecation), 99 s |
| Frontend vitest | **256 passed**, 0 failed, 41 files |
| mypy (`app`) | Success: no issues in 172 source files |
| ruff check (`app tests`) | All checks passed |
| `tsc --noEmit` | no errors |
| ESLint | no errors or warnings |
| `next build` (Turbopack) | compiled; 24 static pages generated |
| `alembic heads` / `current` / `check` | single head `43b64866b554`; dev DB at head; "No new upgrade operations detected" (models match migrations) |

`ruff format` isn't part of the project's checks. Running `ruff format --check app` reports 16
pre-existing files that would be reformatted, so it isn't a gate today.

## Known testing gaps

- No E2E/browser test suite. Critical flows (sign up, add an expense, see it on the dashboard)
  are covered only in pieces, by API integration tests and component tests.
- No frontend tests for the login/register pages, accounts, categories, budgets, or dashboard
  components.
- No cross-user test for the JSON report endpoints (see note 4 above).
- No coverage measurement is configured (neither `pytest-cov` nor Vitest coverage), so there are
  no coverage percentages to report.
- Responsive layout is checked only through component tests of the nav, not at real
  breakpoints.
