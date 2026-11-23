# Feature matrix: PRODUCT_SPEC.md against the code

Assessed 2026-11-22 on branch `fix/credit-card-ledger-semantics` (uncommitted). Each status was
checked against the code (the 96 API operations in the generated OpenAPI schema, the frontend
routes and components, and the tests), not against what the UI appears to offer.

- **Complete:** works end to end against real data, with backend and frontend tests.
- **Partial:** the core works, but part of the spec's behaviour is missing.
- **Demo:** a clearly labelled mock stands in for an external provider that isn't configured
  (CLAUDE.md: never fake an integration).
- **Missing:** no code.

| § | Feature | Backend | Frontend | Tests | Status | What's left |
|---|---|---|---|---|---|---|
| 7 | Dashboard | `GET /dashboard` (real aggregates) | `/dashboard` | `test_dashboard.py` | Complete | — |
| 8 | Financial health score | `services/health_score.py`, 4 factors | health meter | `test_health_score.py` | Partial | Budget adherence and emergency fund aren't factors yet (documented in the module) |
| 9–10 | Monthly spending, category breakdown | dashboard + analytics | dashboard cards | yes | Complete | — |
| 11 | Fast expense entry | quick-add parse, `POST /transactions` + `Idempotency-Key` | mobile Add sheet, offline queue | yes | Complete | — |
| 12 | Voice expense entry | — | — | — | Missing | Browser speech API → existing quick-add parser |
| 13–14 | Transactions list and details | CRUD, filters, sort, pagination, duplicate | `/transactions` | yes | Complete | — |
| 15 | Budgets | CRUD, status thresholds | `/budgets` | yes | Complete | — |
| 16 | Smart budget prediction | `GET /budgets/suggestions` (labelled estimate) | budgets page | yes | Complete | — |
| 17 | Savings goals | CRUD, pacing | `/goals` | yes | Complete | — |
| 18 | Recurring expenses | schedules + idempotent generation | `/recurring-transactions` | yes | Partial | Generation runs on `POST …/generate`; no scheduler |
| 19 | Subscription manager | extension of recurring, one normalization | `/subscriptions` | yes | Complete | — |
| 20 | Multiple accounts | CRUD, archive | `/accounts` | yes | Complete | — |
| 21 | Credit-card tracking | owed / credit balance, available credit ≥ 0, over-limit, utilization, dues | account card | `test_credit_card_*`, ledger tests | Complete locally | Production needs migration `c8e4a1f6b2d9` (lockstep deploy) |
| 22 | Expense splitting | — | — | — | Missing | Split model, remainder rule (CLAUDE.md §13), UI |
| 23 | Calendar | `GET /calendar` | `/calendar` | yes | Complete | — |
| 24 | Analytics | `GET /analytics` | `/analytics` | yes | Complete | — |
| 25 | Spending insights | — | marketing copy only | — | Missing | Insight rules over existing analytics |
| 26 | AI assistant | 8 read-only user-scoped tools | `/ai` | yes | Demo unless `ANTHROPIC_API_KEY` is set | Real provider needs the key; the mock is labelled |
| 27 | AI financial summary | — | — | — | Missing | Job + prompt over the tool catalog |
| 28–29 | Receipt scanner and storage | upload (magic-byte check, 10 MB), confirm, book | `/receipts` | yes | Partial / Demo | OCR is the labelled mock; storage is local disk unless S3 is configured (Render's disk is ephemeral) |
| 30 | Natural-language search | allow-listed filter, bounded amounts | search box | yes | Complete | — |
| 31 | Net worth | dashboard + net-worth report and trend | reports | yes | Complete | — |
| 32 | Reports | 8 reports | `/reports` | yes | Complete | — |
| 33 | Import (CSV/Excel) | — | — | — | Missing | Parser, dedup, preview UI |
| 34 | Export | CSV/XLSX/PDF for each report | export buttons | yes | Partial | No whole-account personal-data export |
| 35 | Notifications | 5 detectors, in-app list | bell | yes | Partial | Generated when read; no email or push delivery; no scheduler |
| 36 | Calculator toolbox | — | — | — | Missing | Phase 6 |
| 37 | Emergency fund | — | — | — | Missing | Not modelled |
| 38 | Gamification | — | — | — | Missing | Phase 6 |
| 39 | Search-first UX | NL search | search box | yes | Partial | No global command palette |
| 40 | Keyboard shortcuts | — | modal Escape only | — | Missing | Global shortcut layer |
| 41 | Auth: register, login, sessions, refresh rotation, logout-all, change password | yes | yes | `test_auth.py` | Complete | — |
| 41 | Auth: email verification, password reset | `users.email_verified_at` column only | — | — | Missing | Blocked on an email provider; build the provider interface + labelled mock first |
| 41 | Auth: Google OAuth | — | hidden | — | Missing | Needs OAuth credentials |
| 41, 59 | Account deletion | `POST /auth/delete-account` | Settings → Security | `test_account_deletion.py`, `delete-account-form.test.tsx`, browser smoke | Complete (2026-11-22) | — |
| 42 | Security | user-scoped repositories, CSRF, rate limits, headers, body cap, RLS | CSP, in-memory tokens | many | Partial | See the security findings in DEPLOYMENT.md: CSP allows inline scripts; `/docs` is public; per-IP limits are in memory |
| 46 | Currency | one base currency per user, INR first | yes | yes | Complete for v1 | — |
| 53–55 | Empty, error, loading states | — | every data view (checked per page) | yes | Complete | — |
| 57 | Dark mode | settings | theme sync | yes | Complete | — |
| 58 | Settings | `GET/PATCH /settings` | `/settings` | yes | Complete | — |
| 61 | Demo mode | mock AI, OCR and sync providers, labelled | landing demo data, labelled | yes | Complete | — |
| 62–63 | Mobile UX, PWA | — | bottom nav, offline queue, service worker | yes; 13 pages smoke-tested at 390 px and 1440 px | Complete | — |
| 64 | Testing | 1,534 backend tests | 427 frontend tests | — | Partial | No committed browser end-to-end suite |
| 65 | Seed data | default categories (migration) | — | — | Partial | No demo-account seed script |
| — | Connected accounts / Setu AA | consent-based link + sync with a labelled mock | `/settings/connected-accounts` | yes | Demo | `setu_sandbox` is an unimplemented stub; needs Setu sandbox credentials and their API contract |
| — | Error monitoring | request ids in logs and headers | console only | — | Missing | Sentry (or similar) needs an account and DSN |
