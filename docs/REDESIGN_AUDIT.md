# Redesign Audit — Phase 00

**Date:** 2026-10-09 · **Branch:** `feat/automatic-transaction-sync` @ `367dc9f` · **Scope:** audit only, no
application behavior changed.

This document records the current state of the product's design, functionality, and architecture before
the Apple-inspired redesign begins. Every finding labelled **Confirmed** was verified against the code
(file and line references given). Findings labelled **Recommendation** are design or product judgements,
not defects.

Priority scale: **P0** security, data integrity, or a broken core workflow · **P1** major UX/visual
problem · **P2** high-value feature or refinement · **P3** optional polish.

---

## 1. Executive summary

The backend is in strong shape. It has a strict layered architecture, integer-paise money end to end,
transfers excluded by construction, user-scoped repositories, 76 cross-user isolation tests, and clean
ruff and mypy runs. The redesign does **not** need backend restructuring.

The frontend works, but it is closer to a well-built prototype than a premium product:

1. **There is no design system.** `globals.css` defines exactly two tokens (`--background`,
   `--foreground`). Every component hard-codes `zinc-*` utilities and 28 hex colors. The Geist font is
   loaded but **never applied**: `body { font-family: Arial }` overrides it (Confirmed, visible in the
   committed screenshots).
2. **Three foundation libraries mandated by CLAUDE.md are absent:** shadcn/ui (Radix), React Query, and
   Zod. `docs/ARCHITECTURE.md` documents the React Query omission as a decision. That contradicts
   CLAUDE.md §7 and needs an explicit reconciliation (CLAUDE.md's own preamble requires that).
3. **Several core workflows fail silently or break:**
   - The access token expires after 15 minutes with no refresh, so every page then fails until the
     user reloads.
   - Delete, archive, and duplicate errors are swallowed in 9 components.
   - Form validation errors for unmapped fields show nothing at all.
   - The mobile Add sheet hangs on "Loading…" when opened offline, which defeats the offline-entry
     feature.
4. **Navigation is a flat list of 13 links** with no active state, emoji icons on mobile, and no
   search or keyboard shortcuts, although PRODUCT_SPEC §39–40 asks for both.
5. **Several spec features are missing:**
   - Spending insights (§25)
   - Voice entry (§12)
   - Ctrl+K global search (§39)
   - Keyboard shortcuts (§40)
   - Import (§33)
   - Data export and deletion (§34, §58)
   - Password reset and email verification (§41)
   - Expense splitting (§22)
   - Emergency fund (§37)
   - Calculators (§36)
   - Automatic recurring generation (§18)

**Recommended next step:** Phase 01, "Stabilize core workflows" (§10). It fixes the five P0 defects with
no visual change, so the redesign starts on a reliable base. Section 9 lists three decisions to make
before Phase 02 starts.

---

## 2. Current architecture and routes

### 2.1 Stack (as installed, not as specified)

| Layer | Specified (CLAUDE.md §3) | Actually installed | Gap |
|---|---|---|---|
| Framework | Next.js App Router + TS | `next@16.3.5`, `react@19.2.8`, TS 5 | — (note `frontend/AGENTS.md`: Next 16 has breaking changes; read `node_modules/next/dist/docs/` before writing code) |
| Styling | Tailwind | Tailwind v4 (`@tailwindcss/postcss`), class-based `dark` variant | No token layer |
| Components | **shadcn/ui** | Hand-rolled `components/ui/` (9 files) | **Missing** |
| Server state | **React Query or equivalent** | `useState` + `useEffect` + `reloadToken` per page | **Missing** (documented deviation) |
| Form schema | **Zod** | Ad hoc checks in each form | **Missing** |
| Charts | Recharts | `recharts@^3.10.1` (7 chart components) | — |
| Icons | — | Emoji literals | No icon library |
| Animation | — | None (Tailwind `animate-pulse` only) | Fine; add only purposeful motion |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic | Same | — |

The runtime dependencies are only `next`, `react`, `react-dom`, and `recharts`. The dependency footprint
is very small, so adding the mandated libraries is low-risk.

### 2.2 Frontend routes

| Group | Route | Notes |
|---|---|---|
| Marketing | `/` | Landing page with labelled demo data |
| Auth | `/login`, `/register` | No forgot-password route (backend lacks it) |
| App | `/dashboard`, `/transactions`, `/accounts`, `/budgets`, `/goals`, `/recurring-transactions`, `/subscriptions`, `/analytics`, `/calendar`, `/reports`, `/receipts`, `/ai`, `/settings` | All `"use client"` pages that fetch in `useEffect` |
| App, nested | `/settings/categories`, `/settings/connected-accounts`, `/settings/merchant-rules` | Reachable only from the Settings page |
| System | `/offline`, `not-found`, `error`, `(app)/error`, `global-error`, `manifest.ts` | Error boundaries are well built |

**Shell:** `app/(app)/layout.tsx` provides a client-side auth guard, a 13-item sidebar at `md` and up, a
header (sync status, notification bell, name, Log out), and `MobileBottomNav` below `md`
(Home / Transactions / **Add** / Analytics / More).

### 2.3 Backend

There are 20 routers and 94 endpoints under `/api/v1`, 18 tables, and 14 linear migrations (head
`43b64866b554`). The layering `api → services → repositories → models` is respected. Pure calculation
modules (`*_calculations.py`, `health_score.py`, `recurrence.py`, `month_bounds.py`) hold every money
and date rule. Side ports are `ai/`, `search/`, `ocr/` (mock only), `storage/` (local or S3), `sync/`
(mock, plus an unimplemented Setu stub), and `jobs/` (generators exist but no scheduler runs them).

---

## 3. Findings from the supplied AI report

**No standalone AI-generated audit report exists in the repository.** I searched for `*report*`,
`*audit*`, `*.md`, `*.pdf`, `*.docx`, and `*.html` outside `node_modules`, `.next`, `.venv`, and
`backend/var`. I also checked `.claude/` (empty) and the user's Downloads, Documents, and Desktop
folders. If the report lives somewhere else (a chat export, cloud drive, or attachment), please share
it and this section will be updated.

The closest artifact is the AI-written **phase report** that commit `13e5b02` ("docs: improve phase
report technical documentation") put into `README.md` ("Features", "Current project status") and the
"Known gaps" sections of `docs/TESTING.md`, `docs/ERROR_HANDLING.md`, and `docs/DEPLOYMENT.md`. Its
claims, checked against the code:

| Report claim | Verdict |
|---|---|
| Backend 1066 tests, frontend 256 tests passing; tsc, ESLint, ruff, and mypy clean | **Frontend and static checks re-verified today** (§11). Backend pytest was deliberately not run (§11). |
| "Every data view has loading (skeleton), empty, and error states" | **Mostly true, with exceptions.** The transactions and reports pages load accounts and categories with no `.catch` (§4, P0-4). The Add sheet shows text "Loading…", not a skeleton. The app shell shows text "Loading your account…". |
| Access token not refreshed mid-session (known gap) | **Confirmed, and under-prioritised.** It breaks every page after 15 minutes, so this audit rates it **P0** (P0-1). |
| No scheduler; recurring generation needs the "Generate" button | **Confirmed.** Subscriptions inherit this, so renewals never post on their own (P1-9). |
| Health score uses 4 factors; budget adherence and emergency fund not wired | **Confirmed.** However, the **landing page demo shows a "Budget adherence" factor** (`components/marketing/demo-data.ts:69-73`) that the real score never computes (P1-7). |
| Inline page error panels aren't live regions | **Confirmed** (P1-10). |
| No E2E suite, no coverage, login/register/accounts/budgets/dashboard have no component tests | **Confirmed.** |
| UTC month boundaries (in `month_bounds.py` docstring) | **Confirmed, and it reaches further than the report says.** The frontend mixes UTC "today" with local month (P1-8). |
| Not reported | Font override, missing design tokens, missing mandated libraries, swallowed mutation errors, silent field errors, offline Add sheet hang, float math in the amount filter, stale views after mobile Add, no sidebar active state, missing spec features (insights, shortcuts, Ctrl+K, voice). All are below. |

---

## 4. Confirmed issues (with evidence)

### P0 — security, data integrity, broken core workflows

No cross-user data exposure, plaintext secrets, or float money storage was found. The backend isolation
and money model are sound. The P0 items are broken core workflows.

**P0-1. The session silently dies after 15 minutes.**
- **Evidence:** `lib/api-client.ts` has no 401 handling. `lib/auth-context.tsx` refreshes only once, on
  mount. `ACCESS_TOKEN_EXPIRE_MINUTES` is 15 in the template.
- **Failure:** After 15 minutes, every fetch and mutation returns "Invalid or expired session. Please log
  in again." The user is never redirected, and an unsaved form submission fails.
- **Fix:** Single-flight refresh on 401 with one retry. Refresh tokens rotate and reuse revokes every
  session (`session.reuse_detected`), so concurrent 401s must share one refresh promise.

**P0-2. Errors from destructive and secondary actions are swallowed.**
- **Evidence:** `handleConfirmDelete` uses `try { await onDelete() } finally {…}` with no `catch` in
  `account-card`, `budget-card`, `category-row`, `goal-card`, `merchant-rule-row`,
  `recurring-transaction-card`, `subscription-card`, `transaction-details`, and `transaction-row`.
  `transaction-row.tsx:128` calls `void onDuplicate()` with no handling at all.
- **Failure:** A failed delete or archive (network drop, expired token per P0-1, a 409 or 422) resets the
  button with no message. It becomes an unhandled promise rejection, and the user believes the action
  happened or can't tell why it didn't.

**P0-3. Validation errors for unmapped fields render nothing.**
- **Evidence:** All 8 forms use `if (!err.fieldErrors) setError(err.message)` (for example
  `transaction-form.tsx:131`, `account-form.tsx:109`). Each form renders only some field keys. For
  example, `transaction-form` renders `amount` (client-side) and `transfer_account_id` only.
- **Failure 1:** A merchant longer than 200 characters (`schemas/transaction.py:45`, and the input has no
  `maxLength`) returns a 422 with `field_errors.merchant`. Nothing is shown and the button just
  re-enables. The same happens for `account_id` (archived account), `category_id`, `description`, and
  `occurred_at`.
- **Failure 2:** Where a key *is* mapped, the raw machine string shows instead of the friendly message.
  A transfer with no destination shows "required". A cross-currency transfer shows "currency mismatch"
  instead of "Transfers between accounts in different currencies aren't supported yet."
  (`transaction_service.py:71-90`).

**P0-4. Offline expense entry hangs.**
- **Evidence:** `components/expense-entry/add-expense-sheet.tsx:63-95` uses `Promise.all([listAccounts,
  listCategories, listTransactions])` with no `.catch`. Line 246 renders "Loading…" until `accounts`
  is non-null. Accounts and categories are never cached in IndexedDB (`lib/offline/db.ts`). The service
  worker never caches `/api/`, which is correct.
- **Failure:** If the sheet is opened while offline, it shows "Loading…" forever, so the offline queue
  (PRODUCT_SPEC §63, "Do NOT silently lose data") can't be reached. The test
  `add-expense-sheet.test.tsx:138` mocks `listAccounts` as *resolving* while `navigator.onLine=false`,
  so it doesn't reproduce real offline behavior.
- **Same pattern elsewhere:** `app/(app)/transactions/page.tsx:69` and `app/(app)/reports/page.tsx:84`
  have no `.catch`. On the transactions page, a failed accounts or categories call leaves the skeleton
  up forever, because `isLoading` requires both.

**P0-5. The amount filter uses floating-point money math and breaks typing.**
- **Evidence:** `components/transactions/transaction-filters.tsx:100-112` uses
  `Math.round(Number(value) * 100)` and displays `String(amount_min / 100)`.
- **Problems:**
  - It violates CLAUDE.md §13 and §7, which say money is parsed only through `lib/money.ts`.
  - It hard-codes 100, which is wrong for JPY.
  - Because the input is controlled, typing "12." re-renders as "12", so **you can't type a decimal
    amount**.
  - Typing a letter sends `amount_min=NaN`, which returns a 422 and the generic "One or more fields are
    invalid."

### P1 — major UX and visual problems

**P1-1. The Geist font is never applied.** `app/globals.css` sets `body { font-family: Arial,
Helvetica, sans-serif; }`, which overrides the `--font-sans: var(--font-geist-sans)` theme value. No
element uses `font-sans`. The committed screenshots (`frontend/playwright-artifacts/screenshots/*`)
render in Arial.

**P1-2. There are no design tokens.**
- Only `--background` and `--foreground` exist.
- Colors are hard-coded `zinc-*` across about 100 files, plus 28 hex literals (`#2563eb` ×5, `#059669`
  ×4, `#dc2626` ×3, and others). Each chart file defines its own `LINE_COLOR`.
- There is no semantic layer (surface, muted, border, accent, positive, negative, warning), no radius,
  shadow, or spacing scale, and no type scale.
- A visual change today means editing every file.

**P1-3. Money values break mid-number on mobile.**
- `components/dashboard/stat-card.tsx` uses `text-2xl break-words` inside a `p-6` card in a
  `grid-cols-2` mobile grid. The landing page reuses it.
- The 390px screenshot shows "₹4,82,65 / 0.00".
- `proportional-nums` is used where tabular numerals are standard for financial figures.
- Always showing ".00" on large rupee amounts adds noise.

**P1-4. Navigation and information architecture.**
- The desktop sidebar (`app/(app)/layout.tsx:15-29, 63-71`) is a flat list of 13 links with **no active
  state** (no `usePathname`, no `aria-current`) and no icons.
- The order is odd: Transactions is 6th, after AI, Analytics, Calendar, and Reports.
- Categories, Connected accounts, and Merchant rules can only be reached from inside Settings.
- On mobile, the bottom nav and More menu use emoji as icons, and Reports and Receipts share the same
  🧾 (`more-menu.tsx:12-13`).
- The header always shows a bordered "Log out" button, which is a low-frequency, destructive action
  given prime placement.

**P1-5. Mutations don't refresh visible data.**
- `MobileBottomNav` → `onExpenseCreated` calls only `offlineSync.refresh` (`layout.tsx:96`,
  `mobile-bottom-nav.tsx:113-116`).
- Adding an expense from the bottom nav on `/dashboard` or `/transactions` leaves the balance, totals,
  and list stale until navigation.
- Each page refetches accounts and categories independently, with no shared cache.
- This is the main practical argument for adopting a query cache (Decision D1).

**P1-6. Modal and dialog quality.**
- `components/ui/modal.tsx` has these gaps:
  - no body scroll lock
  - focus is not restored to the trigger on close
  - the focusable selector includes disabled controls
  - no portal
  - fixed `max-w-md` for every dialog
  - always centered, including on mobile, where the Add flow should be a bottom sheet
- The transaction form inside it scrolls inside `max-h-[70vh]`, which nests a scroll region in a
  dialog.
- Delete confirmation is an inline button swap rather than a confirm dialog with consequences explained
  (for example "Archive account — past transactions are kept").

**P1-7. The landing page shows a health-score factor that doesn't exist.**
`components/marketing/demo-data.ts:69-73` shows "Budget adherence — Most categories are within budget
this month." The real score (`backend/app/services/health_score.py`) has no such factor. CLAUDE.md §13
requires the "+/-" reasons to be the literal factors. It is labelled "Example data", but it still
advertises behavior the product doesn't have.

**P1-8. Timezone inconsistency for IST users (documented v1 limitation, wider than documented).**
- The backend buckets by UTC (`month_bounds.py`).
- The frontend computes "today" as `new Date().toISOString().slice(0,10)` (UTC) in
  `calendar-grid.tsx:10`, `subscription-form.tsx:48`, and `recurring-transaction-form.tsx:53`, but
  uses the local month in `calendar/page.tsx:19-20`.
- Transaction date filters send `T00:00:00Z` (`transaction-filters.tsx:83-88`).
- Between 00:00 and 05:29 IST:
  - the calendar highlights yesterday
  - new subscriptions and recurring schedules default to yesterday
  - an expense entered at 01:00 IST on the 1st counts toward last month's budget
- For an INR-first product this is a real user-visible correctness issue, not an edge case.

**P1-9. Recurring transactions and subscriptions never post automatically.** There is no scheduler
(`app/jobs/` generators exist; `main.py` registers no lifespan or scheduler). PRODUCT_SPEC §18 says
"Automatically generate upcoming transactions." Until a user visits `/recurring-transactions` and
clicks Generate, rent and subscriptions are missing from balances, budgets, the dashboard, and the
health score.

**P1-10. Accessibility gaps (Confirmed).**
- Page-level error panels are plain `<div>`s, not `role="alert"` (every page).
- The transaction-type segmented buttons have no `aria-pressed` or radio semantics
  (`transaction-form.tsx:150-163`).
- Budget and goal progress bars have no accessible name.
- Charts have no text alternative or summary table.
- Recharts tooltips use fixed white styling in dark mode.
- Only 3 ARIA tab, selected, or pressed attributes exist in all components.
- The "Add" FAB removes its focus outline (`focus-visible:outline-none`) with no replacement ring
  (`mobile-bottom-nav.tsx:51-53`).

**P1-11. Transaction list ergonomics.**
- Each row renders three text buttons (Edit, Duplicate, Delete), which wrap to a second line on mobile.
- There is no grouping by date and no daily subtotal.
- Search fires a request on every keystroke (no debounce).
- There is no "Needs review" filter even though synced rows carry the flag.

### P2 — functional gaps and refinements (Confirmed missing in code)

| ID | Gap | Spec |
|---|---|---|
| P2-1 | No spending insights ("Food up 28% vs last month"). `grep -ri insight` finds only marketing copy. | §25, §72 |
| P2-2 | No Ctrl+K global search or command palette, and no keyboard shortcuts or help panel | §39, §40 |
| P2-3 | Budgets are current-month only, with no month navigation or history. Smart budget suggestions exist but can only be used inside the create form. | §15–16 |
| P2-4 | No password reset, email verification, password change, data export (JSON/CSV of everything), or account deletion. Settings has no Privacy or Data section. | §34, §41, §58–59 |
| P2-5 | No CSV/Excel import | §33 |
| P2-6 | No voice entry | §12 |
| P2-7 | No expense splitting, emergency fund, calculators, or gamification | §22, §36–38 |
| P2-8 | No weekly or monthly AI summary | §27 |
| P2-9 | The health-score "recurring ratio" uses this month's `is_recurring`-flagged actual spend, not the canonical monthly normalization CLAUDE.md §13 names for that figure. Defensible, but it diverges from the written rule. Reconcile one or the other. | CLAUDE.md §13 |
| P2-10 | `lib/api-client.ts:12` defaults `API_BASE_URL` to `http://127.0.0.1:8000`, which `.env.example` and README say must never be used (cookie host mismatch breaks session restore). If `.env.local` is missing, the default is wrong. | — |
| P2-11 | The dashboard and transactions empty states use `<a href>` instead of `<Link>`. This forces a full reload, which re-runs `/auth/refresh` and rotates the token. | — |
| P2-12 | `ApiError` construction assumes `envelope.error` exists. A non-OK JSON body without `error` (for example a proxy 502 JSON) throws a `TypeError` inside the client. | — |
| P2-13 | Buttons replace their label with "Please wait…" while loading, which changes their width and loses context. Prefer spinner plus the label. | — |

### P3 — polish

- Leftover create-next-app assets in `frontend/public/` (`file.svg`, `globe.svg`, `next.svg`,
  `vercel.svg`, `window.svg`).
- The product name is the placeholder "Finance App" in metadata, the sidebar, the auth layout, and the
  PWA title.
- The app-shell loading state is plain text, not a skeleton shell.
- Greeting uses `full_name.split(" ")[0]`. Fine, but consider a preferred-name field later.
- `vitest` creates jsdom 41 times (about 280 s cumulative). `pool: 'vmThreads'` would speed up CI.

---

## 5. Recommended visual direction

**"Calm ledger."** Apple-inspired restraint: content first, chrome recedes, numbers are the hero.

- **Typography:** Keep Geist, which is already loaded, and fix the override. Optionally fall back to
  `-apple-system`/SF on Apple devices. Use a type scale of 12, 13, 15, 17, 20, 28, and 34 with large
  page titles (34/28) and 15px body text. Apply **tabular numerals** (`font-variant-numeric:
  tabular-nums`) to every amount. Show amounts with a smaller, muted currency symbol and decimals
  (₹ **4,82,650**.00).
- **Color:** A neutral grey surface system with a single accent (a calm blue) used for interactive
  elements only. Semantic colors are reserved for meaning: positive (income, healthy), negative
  (overspend; expenses themselves stay neutral, not red), warning, and info. Never colour every expense
  red. Dark mode uses true elevated greys, not pure black cards.
- **Surfaces and depth:** Grouped, inset lists in the style of iOS Settings for settings, accounts, and
  details. Cards use a 1px hairline border and *either* a very soft shadow *or* a border, not both.
  Radius scale 8, 12, 16, 20 (sheets and large cards).
- **Layout:**
  - Desktop: sidebar with grouped sections (Overview · Money · Planning · Insights · Tools) and a
    content max-width of about 1200px.
  - Tablet: collapsible rail.
  - Mobile: large-title header, bottom tab bar with real icons, bottom sheets for create and edit.
- **Iconography:** One icon set (lucide-react) for all chrome. Category icons stay user content
  (emoji are stored in the DB today), rendered in a uniform tinted rounded-square container.
- **Motion:** 150–250 ms ease-out for sheet and dialog enter/exit, list insert or remove, and progress
  fill. No decorative motion. The existing `prefers-reduced-motion` rule stays.
- **Data viz:** One chart theme module (axis, grid, tooltip, palette from tokens, dark-mode aware). Use
  compact currency ticks (₹1.2L, ₹45K) instead of clipped full amounts. Each chart has a one-line
  question title (already a good habit in the codebase) and an accessible summary.

---

## 6. Proposed reusable component system

Build bottom-up in `components/ui/`. Where a primitive needs complex accessibility (dialog, menu,
popover, tabs, select, toast), use **shadcn/ui on Radix**, as CLAUDE.md §3 already mandates.

| Layer | Components | Replaces or fixes |
|---|---|---|
| **Tokens** | CSS variables in `globals.css` mapped via Tailwind v4 `@theme`: color (semantic), radius, shadow, spacing, type scale, motion durations; light and dark | P1-1, P1-2 |
| **Primitives** | `Button` (primary/secondary/ghost/**destructive**, sizes, `loading` keeps label), `IconButton`, `Input`, `Textarea`, `Select` (native on mobile), `Checkbox`, `Switch`, `SegmentedControl` (radio-group semantics), `Badge`, `Kbd` | P1-10, P2-13 |
| **Money** | `Amount` (format, sign, tone, tabular, de-emphasized decimals, compact mode), `MoneyInput` (wraps `parseMoneyToMinorUnits`, currency adornment) | P1-3, P0-5, every hand-rolled amount input |
| **Overlays** | `Dialog`, `Sheet` (bottom on mobile, side on desktop), `ResponsiveDialog`, `ConfirmDialog` (destructive, with consequence copy and its own error state), `DropdownMenu` (row actions), `Popover`, `Tooltip`, `Toast` | P1-6, P0-2, P1-11 |
| **Feedback** | `EmptyState` (icon, title, body, action), `ErrorState` (`role="alert"`, retry), `Skeleton` presets, `InlineFieldError` | P1-10, duplicated error-panel markup on 15+ pages |
| **Layout** | `AppShell`, `SidebarNav` (grouped, active state), `MobileTabBar`, `PageHeader` (title, subtitle, actions), `Section`, `ListGroup` and `ListRow` (inset grouped list) | P1-4 |
| **Data display** | `StatTile`, `ProgressMeter` (labelled, status tone), `TransactionList` (date-grouped, row menu), `ChartCard` and `chartTheme`, `DataTable` (desktop reports) | P1-3, P1-11, chart duplication (`components/reports/stat-tile.tsx` duplicates `dashboard/stat-card.tsx`) |
| **Forms** | Zod schemas in `lib/schemas/` mirroring Pydantic limits, plus one `applyApiErrors(form, err)` helper that maps known fields and **always** falls back to `err.message` for unmapped ones | P0-3 |
| **Commands** | `CommandPalette` (Ctrl+K), `useShortcut` hook and shortcuts help sheet | P2-2 |

---

## 7. Functional improvements ranked by impact and effort

| Rank | Item | Impact | Effort | Priority |
|---|---|---|---|---|
| 1 | Single-flight token refresh plus retry in `api-client` | Very high | S | P0-1 |
| 2 | Mutation error surfacing (confirm dialogs, toasts) and the form-error fallback | Very high | S–M | P0-2, P0-3 |
| 3 | Offline Add sheet: cache accounts and categories in IndexedDB, handle load failure | High | S–M | P0-4 |
| 4 | Amount filter through `lib/money.ts`, plus debounced search | Medium | S | P0-5, P1-11 |
| 5 | Shared query cache with invalidation after any create or edit | High | M–L | P1-5 |
| 6 | Design tokens, font fix, `Amount` component | High | M | P1-1–3 |
| 7 | Grouped navigation with active state, icons, mobile sheet | High | M | P1-4, P1-6 |
| 8 | Per-user timezone (setting plus backend boundaries plus frontend "today") | High for IST users | M–L (backend, migration, tests) | P1-8 |
| 9 | In-process scheduler for recurring and notifications (through the existing `jobs/` abstraction) | High | M | P1-9 |
| 10 | Spending insights from existing analytics aggregates | High | M | P2-1 |
| 11 | Ctrl+K palette and keyboard shortcuts | Medium | M | P2-2 |
| 12 | Budget month navigation and history | Medium | M | P2-3 |
| 13 | Data export and account deletion (privacy promise) | Medium–High | M | P2-4 |
| 14 | Password reset and email verification (needs an email provider abstraction plus mock) | Medium | M–L | P2-4 |
| 15 | CSV import with mapping and dedup | Medium | L | P2-5 |
| 16 | Voice, splits, calculators, emergency fund, gamification | Low–Medium | L each | P2-6/7 |

---

## 8. Risks, dependencies, and test requirements

**Risks**
- **Token refresh concurrency.** Rotation plus reuse detection means two parallel refreshes revoke
  every session. This needs a single shared in-flight promise, and a test that fires N concurrent 401s
  and asserts exactly one `/auth/refresh`.
- **Big-bang restyle.** About 100 component files hard-code classes. Migrate behind tokens first, then
  page by page, keeping existing component APIs where tests depend on them (256 frontend tests use
  role and text queries, which is good and survives restyling if labels are preserved).
- **Next.js 16 differences.** Per `frontend/AGENTS.md`, consult `node_modules/next/dist/docs/` before
  touching routing, layouts, or metadata.
- **Category icons are DB data (emoji).** Do not migrate them to icon keys in the redesign. Render them
  in a uniform container.
- **Timezone change touches every aggregate.** It needs its own phase, a user setting, a migration, and
  updates to all date-boundary tests. Do not mix it with visual work.
- **New dependencies** (Radix via shadcn, TanStack Query, Zod, lucide-react) need approval (Decision
  D1). Each is mainstream and tree-shakeable.

**Test requirements for the redesign**
- Every P0 fix ships with a regression test that reproduces the failure first. One example: the
  offline Add sheet with `listAccounts` *rejecting*.
- Component tests for the new primitives, including keyboard behavior for Dialog, Sheet, Menu, and
  SegmentedControl.
- Commit a Playwright E2E smoke suite (sign up → add account → add expense → see it on the dashboard
  → delete) against the **test** database only, at 390, 768, 1280, and 1440px, with screenshot
  baselines.
- An axe accessibility check in the E2E suite for each main route.
- Keep all existing 256 frontend tests and 1066 backend tests green after every phase.

---

## 9. Decisions needed before Phase 02

| # | Decision | Recommendation |
|---|---|---|
| D1 | Adopt shadcn/ui (Radix), TanStack Query, Zod, and lucide-react. The first three are already in CLAUDE.md §3 and §7; the current code deviates. | **Yes.** Update `docs/ARCHITECTURE.md` to remove the "doesn't use React Query" deviation. |
| D2 | Product name and wordmark to replace "Finance App" | Needed before the landing and shell redesign |
| D3 | Accent color and light/dark default | Calm blue accent, system theme default |

---

## 10. Phased implementation plan

Each phase leaves the app runnable with all checks green (CLAUDE.md §20–21).

### Phase 01 — Stabilize core workflows (P0, no visual redesign)
- **Scope:** P0-1 to P0-5, plus P2-10, P2-12, and the `.catch` gaps on the transactions and reports
  pages.
- **Acceptance criteria:**
  - After the access token expires, the next request transparently refreshes once and succeeds.
    Concurrent requests trigger exactly one refresh. A failed refresh redirects to `/login` with a
    "Your session expired" message.
  - Every delete, archive, and duplicate failure shows a specific, user-readable message, and no
    unhandled rejections remain.
  - Every form shows `err.message` whenever a field error has no matching input. Transfer errors show
    the backend's sentence, not "required" or "currency mismatch".
  - Opened offline, the Add sheet shows the form using cached accounts and categories and queues the
    expense. With no cache, it shows a clear message instead of "Loading…".
  - The amount filter accepts "12.50", rejects letters inline, and uses `lib/money.ts`.
  - New regression tests cover each item, and vitest, tsc, ESLint, ruff, mypy, and pytest all pass.

### Phase 02 — Design foundation
- **Scope:** Decision D1 dependencies; tokens (light and dark); font fix; `Amount`, `MoneyInput`,
  `Button` variants, `Dialog`, `Sheet`, `ConfirmDialog`, `Toast`, `EmptyState`, `ErrorState`,
  `ProgressMeter`, `chartTheme`; Playwright screenshot baseline.
- **Acceptance criteria:**
  - No raw hex in components.
  - Geist renders.
  - Amounts never wrap mid-number at 360px.
  - Primitives have keyboard and axe tests.
  - Existing pages look the same or better with no behavior change.

### Phase 03 — App shell and navigation
- **Scope:** Grouped sidebar with active state and icons; tablet rail; mobile large-title header; icon
  tab bar; More as a sheet; Log out moved to the account menu; Ctrl+K palette; shortcuts (N, G D,
  G T, …, ?).
- **Acceptance criteria:**
  - `aria-current` is set on the active route.
  - Every route is reachable in two interactions or fewer on mobile and desktop.
  - The shortcut help panel lists only working shortcuts.
  - E2E navigation passes at all four widths.

### Phase 04 — Data layer
- **Scope:** TanStack Query provider; migrate pages one at a time, with shared `accounts` and
  `categories` queries; invalidate after every mutation, including the mobile Add sheet.
- **Acceptance criteria:**
  - Adding an expense from any screen updates the dashboard and list without navigation.
  - Accounts and categories are fetched once per session, not once per page.

### Phase 05 — Screen redesigns (one PR per group)
1. Dashboard ("What should I know about my money right now?", §72)
2. Transactions (date-grouped list, row menu, filter sheet, debounced search)
3. Add or edit transaction sheet
4. Budgets and Goals
5. Accounts, Subscriptions, and Recurring
6. Analytics, Reports, and Calendar
7. Settings (inset grouped lists), AI, and Receipts
8. Auth and landing (fix P1-7)

- **Acceptance criteria per screen:**
  - Verified at 390, 768, 1280, and 1440px, light and dark.
  - Loading, empty, error, and success states all designed.
  - axe-clean.
  - Existing tests are updated, not deleted.

### Phase 06 — Functional gaps (backend and frontend)
- **Scope:** P1-8 timezone, P1-9 scheduler, P2-1 insights, P2-3 budget history, P2-4 export and
  deletion, then reset and verification.
- **Acceptance criteria:** Each item gets a backend unit and integration test per CLAUDE.md §15, plus
  cross-user negative tests for new endpoints.

### Phase 07 — Polish and optional features (P3, remaining P2)

---

## 11. Checks performed in this audit

| Check | Result |
|---|---|
| `npm run typecheck` (tsc --noEmit) | Pass, no errors |
| `npm run lint` (ESLint) | Pass, no output |
| `npx vitest run` | **256 / 256 passed** (41 files) |
| `ruff check app tests` | All checks passed |
| `mypy app` | Success, no issues in 175 source files |
| `pytest` | **Not run, deliberately.** `tests/conftest.py` runs `DELETE FROM users` / `DELETE FROM audit_logs` after every test. It targets the separate test DB, but this phase was scoped to make no destructive database changes. |
| `next build`, `alembic check` | Not run (not needed for an audit; `alembic check` connects to the dev DB) |
| Live browser review | Not done. Dev servers weren't running, and a signed-in review would need a user created in the dev DB. The visual findings come from code plus the existing landing-page screenshots in `frontend/playwright-artifacts/`. |

No application code, configuration, dependency, or database state was changed. This file is the only
addition.

---

## 12. Phase 01 status (2026-10-09)

Frontend-only changes. No backend code, API contract, migration, or database state changed.

| Item | Status | Root cause, as verified in the code |
|---|---|---|
| P0-1 Session expiry | **Fixed** | `api-client` never handled a 401, and `AuthProvider` refreshed only on mount. The mount refresh could also fire twice under React Strict Mode, which risked refresh-token reuse detection. |
| P0-2 Swallowed action errors | **Fixed** | Nine components used `try { await action() } finally {…}` with no `catch`. The transaction row and details also had an unhandled "Duplicate". |
| P0-3 Silent validation errors | **Fixed** | Forms showed `message` only when `field_errors` was absent, and rendered only some keys. Several keys were also misnamed (`balance` vs `balance_minor`, `amount` vs `amount_minor`), so even schema errors vanished. Service rules put machine codes in `field_errors`. |
| P0-4 Offline Add sheet hang | **Fixed** | No `.catch` on the initial load, and no locally saved accounts or categories. The existing "offline" test mocked the network as *succeeding*. |
| P0-5 Amount filter | **Fixed** | The input's displayed value was re-derived from paise on every keystroke (`String(minor / 100)`), and parsing used `Number(x) * 100`. |
| P1-5 Stale views after a change | **Fixed (interim)** | Each page held its own state, and nothing told it the ledger changed. Fixed with a one-line signal (`lib/ledger-events.ts`) that a query cache can later replace. |
| P1-7 Demo health factor | **Fixed** | The demo listed "Budget adherence" and used weights and labels that differ from `health_score.py`. |
| P1-8 IST dates | **Partly fixed** | The transaction date filter now uses local-day bounds. Backend aggregation is still UTC-day based (see below). |
| P1-9 Recurring generation | **Not changed (investigated)** | `run_for_all_users` exists but no scheduler calls it, and its "today" is the UTC date. Deferred to the scheduling work in Phase 5. |
| P1-3 Mobile currency wrap | **Not changed (investigated)** | `StatCard` uses `text-2xl break-words` in a `p-6` card inside a two-column mobile grid. Deferred to Phase 2's `Amount` component. |

Also fixed:
- Report exports bypassed the shared API client with their own `fetch`.
- The API client's fallback URL used `127.0.0.1`.
- A non-envelope JSON error could crash `ApiError` construction.
- The Add sheet parsed every amount as INR, so a JPY account's amounts were 100× too large.
