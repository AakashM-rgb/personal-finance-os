# Database Schema

PostgreSQL, managed only through Alembic (`backend/migrations/`). This page was written from
`backend/app/models/*.py` and `backend/migrations/versions/*.py` at migration head
`d7a1e4c9b3f2`. Where it disagrees with the code, the code wins.

## Conventions (every table)

| Convention | Where it's enforced |
|---|---|
| UUID primary key `id` | `UUIDPrimaryKeyMixin` (`app/models/base.py`) |
| `created_at` / `updated_at` (timestamptz) | `TimestampMixin`. `audit_logs` and `login_failures` have `created_at` only. |
| Money is `BIGINT` integer minor units (paise), named `*_minor` | Every money column. No float/real money columns exist. |
| Transaction amounts are always positive. The sign comes from `type`. | `CHECK (amount_minor > 0)` |
| Enums are stored as strings (`native_enum=False`), not Postgres enum types | `str_enum_column` in `app/models/base.py` |
| User-owned rows carry `user_id → users.id ON DELETE CASCADE` | Deleting a user removes all of their data. `audit_logs` is the exception (`SET NULL`), so the audit trail survives. |
| Every table in `public` has row level security enabled, with no policies | Migration `d7a1e4c9b3f2`; see "Access control and Supabase's Data API" below. A migration that creates a table must also `ENABLE ROW LEVEL SECURITY` on it. `tests/test_rls_hardening.py` fails otherwise. |
| Timestamps are `timestamptz`. Month and day bucketing is done in UTC. | `date_trunc(..., 'UTC')` in `transaction_repository.py`; `app/services/month_bounds.py` |

## Entity relationships

```
users 1─1 user_settings
users 1─* sessions                      (refresh-token hashes; revocable)
users 1─* audit_logs                    (SET NULL on user delete)
users 1─* accounts 1─0..1 credit_card_details
users 1─* categories (user_id NULL = system default) ─* categories (parent_id, self-ref)
users 1─1 budgets 1─* budget_items *─1 categories
users 1─* savings_goals
users 1─* recurring_transactions 1─0..1 subscriptions
users 1─* transactions
            ├─*─1 accounts               (account_id, RESTRICT)
            ├─*─0..1 accounts            (transfer_account_id, RESTRICT; transfers only)
            ├─*─0..1 categories          (SET NULL)
            ├─*─0..1 recurring_transactions (SET NULL: generated history survives)
            └─*─0..1 linked_accounts     (SET NULL)
users 1─* receipts ─0..1 transactions   (receipt can exist before its transaction)
users 1─* notifications
users 1─* linked_accounts 1─* sync_runs
users 1─* merchant_category_rules *─1 categories

login_failures                          (standalone: keyed by an email HMAC, no FK)
data_correction_runs                    (standalone: migration bookkeeping, no FK)
```

## Tables

### Identity and security

| Table | Key columns | Constraints / notes |
|---|---|---|
| `users` | `email` (unique, indexed), `password_hash` (Argon2 via passlib), `full_name`, `is_active`, `email_verified_at` | `email_verified_at` exists as a column, but no verification flow is implemented yet (see README, current status). |
| `user_settings` | `user_id` (unique), `currency` (default `INR`), `theme`, `ai_enabled` (default true), `ai_categorization_enabled` (default false), `notification_preferences` (JSONB) | 1:1 with `users`. `currency` is the base currency that every aggregate is computed in. |
| `sessions` | `user_id`, `family_id` (indexed), `refresh_token_hash`, `user_agent`, `ip_address`, `expires_at`, `revoked_at` | Backs refresh-token rotation and "log out everywhere". Only a hash is stored, never the raw token. `family_id` groups one login's chain of rotated rows; access tokens carry it as `sid` and stop working once the family has no live row. |
| `audit_logs` | `user_id` (nullable, SET NULL), `action` (indexed), `entity_type`, `entity_id`, `ip_address`, `user_agent`, `metadata_json` | Actions currently written: `user.register`, `user.login`, `user.login_failed`, `user.logout_all`, `session.reuse_detected`, `linked_account.link_initiated`, `linked_account.link_completed`, `linked_account.revoked`, `linked_account.sync_triggered`, `user.login_throttled`, `user.password_changed`, `user.password_change_failed`, `user.password_change_throttled`, `account.balance_updated` (metadata: `account_type`, `previous_balance_minor`, `new_balance_minor`). Written only by migration `c8e4a1f6b2d9`: `account.balance_corrected`, `account.balance_correction_skipped`, `account.balance_correction_reverted`, `account.balance_correction_revert_skipped` (per card, with the amounts involved), and the summary rows `ledger.card_balance_correction` / `ledger.card_balance_correction_reverted` (`user_id` NULL, `entity_type` `migration`). |
| `data_correction_runs` | `revision`, `direction` (`upgrade` / `downgrade`), `mode`, `ran_at`, `details` (JSONB) | One invocation of a data-correction migration. Written only by migrations (today `c8e4a1f6b2d9`) and read only by their own safeguards; no service or endpoint touches it. Deliberately **not user-owned and no FK** -- it holds no user data. It is the durable answer to "has this correction already run?", duplicating the `ledger.card_balance_correction` audit row so the guard survives a purge of `audit_logs`; the migration reads whichever record is older. **Nothing may prune it, and the downgrade does not drop it** -- a reverted correction still happened, and the next upgrade needs to know. Index `(revision, ran_at)`. |
| `login_failures` | `account_key` (HMAC-SHA256 of the normalized login email, 64 hex chars), `created_at` (indexed) | Backs the per-account login throttle (`app/services/login_throttle.py`). Deliberately **not user-owned and no FK**: attempts against unregistered emails are throttled the same way, so rows can't reference `users`. The email is never stored, only a keyed HMAC that can't be matched to guessed emails without the server secret. Composite index `(account_key, created_at)` serves the per-account count. Rows older than the throttle window are pruned on every recorded failure, and a successful login deletes that account's rows. |

### Core ledger

| Table | Key columns | Constraints / notes |
|---|---|---|
| `accounts` | `user_id`, `name`, `type` (`bank_account`, `cash`, `credit_card`, `upi`, `savings_account`, `wallet`), `balance_minor`, `currency`, `institution_name`, `is_active` | Soft-deleted (archived) through `is_active`. Transactions reference accounts with `RESTRICT`, so an account with history is never hard-deleted. For `credit_card`, `balance_minor` is the amount owed (a liability in net worth): purchases raise it, refunds and repayments lower it, and a negative value is a credit balance (overpaid card). Every other type stores what the user holds. The per-type ledger rule lives in `app/services/ledger_calculations.py` (see ARCHITECTURE.md, Balances). A balance set directly through `PUT /accounts` writes an `account.balance_updated` audit row. |
| `credit_card_details` | `account_id` (unique, CASCADE), `credit_limit_minor`, `statement_day`, `payment_due_day`, `minimum_payment_minor` | 1:1 extension of `accounts`. Credit-card fields never live on the base account row. |
| `categories` | `user_id` (nullable), `parent_id` (self-ref, SET NULL), `name`, `icon`, `color`, `budget_minor`, `is_active` | Rows with `user_id IS NULL` are the 14 system defaults seeded by migration `fe9868ef4632` (Food, Transport, Shopping, Bills, Entertainment, Education, Health, Travel, Subscriptions, Rent, Utilities, Insurance, Investment, Other). The partial unique index `uq_categories_user_name_active (user_id, name) WHERE user_id IS NOT NULL AND is_active` prevents duplicate active custom names but frees a name once it's archived. |
| `transactions` | `user_id`, `account_id`, `transfer_account_id`, `category_id`, `recurring_transaction_id`, `type` (`income`, `expense`, `transfer`), `amount_minor`, `currency`, `merchant`, `description`, `notes`, `payment_method`, `tags` (text[]), `occurred_at`, `is_recurring`, `idempotency_key`, `linked_account_id`, `external_transaction_id`, `needs_review` | See the invariants below. |

**Transaction invariants** (database-enforced, backed up by service validation):

- `ck_transactions_amount_positive`: `amount_minor > 0`.
- `ck_transactions_transfer_shape`: a transfer has a `transfer_account_id` and no `category_id`.
  A non-transfer has no `transfer_account_id`. Every income/expense aggregate filters on `type`,
  so transfers are excluded by how the query is built, not by per-query discipline.
- `uq_transactions_user_idempotency_key (user_id, idempotency_key)`: a retried
  `POST /transactions` with the same `Idempotency-Key` returns the original row. NULL keys never
  collide. Keys starting with `server:` are written only by the server (receipt bookings) and
  are refused from clients; see ARCHITECTURE.md, "Idempotent writes".
- `uq_transactions_recurring_occurrence (recurring_transaction_id, occurred_at)`: the
  database-level guarantee that recurring generation is idempotent.
- `uq_transactions_linked_account_external_id` (partial, `WHERE linked_account_id IS NOT NULL`):
  a synced transaction can't be imported twice.
- Indexes: `(user_id, occurred_at)`, `(user_id, account_id)`, `(user_id, category_id)`,
  `recurring_transaction_id`, `linked_account_id`, and a partial
  `(user_id) WHERE needs_review = true`.
- `currency` is copied from the account when the transaction is created. It's never
  client-supplied.

### Planning

| Table | Key columns | Constraints / notes |
|---|---|---|
| `budgets` | `user_id` (unique) | One hidden container per user, created on first use. Never exposed through the API. |
| `budget_items` | `budget_id` (CASCADE), `category_id` (CASCADE), `amount_minor` | `CHECK amount_minor > 0`; `UNIQUE (budget_id, category_id)`, so one budget per category. Hard-deleted, since nothing references it. |
| `savings_goals` | `user_id`, `name`, `target_amount_minor`, `current_amount_minor`, `currency`, `target_date` | `CHECK target > 0`, `CHECK current >= 0`, `CHECK current <= target` (overfunding isn't supported). |
| `recurring_transactions` | `user_id`, `account_id` (RESTRICT), `category_id` (SET NULL), `name`, `type`, `amount_minor`, `currency`, `frequency` (`daily`, `weekly`, `monthly`, `quarterly`, `yearly`), `start_date`, `day_of_month`, `is_active` | `CHECK type IN ('income','expense')` (no recurring transfers); `CHECK amount > 0`; `CHECK day_of_month 1..31`. `day_of_month` is fixed from `start_date` so month-end schedules don't drift. There is no stored "next run" pointer. The next date is derived from the latest generated transaction. |
| `subscriptions` | `recurring_transaction_id` (unique, CASCADE) | 1:1 marker extension of `recurring_transactions`, not a parallel scheduler. |
| `notifications` | `user_id`, `category` (`budget_warning`, `budget_exceeded`, `subscription_reminder`, `credit_card_reminder`, `goal_milestone`, `unusual_spending`, `recurring_reminder`), `title`, `message`, `reference_type`, `reference_id`, `action_url`, `is_read`, `dedupe_key` | `UNIQUE (user_id, dedupe_key)` makes regeneration idempotent. Indexes on `(user_id, created_at)` and `(user_id, is_read)`. |

### Documents and sync

| Table | Key columns | Constraints / notes |
|---|---|---|
| `receipts` | `user_id`, `transaction_id` (nullable, SET NULL), `storage_key` (unique), `original_filename`, `content_type`, `file_size_bytes`, `status` (`pending`, `processed`, `confirmed`, `failed`), OCR fields (`ocr_provider`, `ocr_confidence`, `extracted_*`), user-confirmed fields (`confirmed_*`), `suggested_category_id`, `category_id` | A receipt can exist before any transaction (scan-first flow). `ocr_confidence` is a float, but it's a score, not money. All money fields are `*_minor` BIGINT. |
| `linked_accounts` | `user_id`, `account_id` (SET NULL), `provider`, `external_institution_name`, `external_account_id`, `fip_reference`, `consent_id`, `consent_status` (`pending`, `active`, `paused`, `revoked`, `expired`), `consent_expires_at`, `masked_account_ref`, `last_synced_at`, `last_sync_status` | `UNIQUE (consent_id, external_account_id)`. Read-only account-aggregator consent. No payment credentials are stored. |
| `sync_runs` | `linked_account_id` (CASCADE), `started_at`, `completed_at`, `status` (`success`, `partial`, `failed`), `transactions_fetched`, `transactions_created`, `transactions_skipped_duplicate`, `error_message` | Audit history of each sync attempt. |
| `merchant_category_rules` | `user_id`, `merchant_key`, `category_id` (CASCADE) | `UNIQUE (user_id, merchant_key)`. Created only when the user opts in by correcting a category and asking to remember it. |

## Delete behavior (chosen per relationship)

| Relationship | `ON DELETE` | Why |
|---|---|---|
| any `user_id → users` | CASCADE | Account deletion (`POST /auth/delete-account`) removes all of the user's data with one `DELETE FROM users`. |
| `audit_logs.user_id` | SET NULL | The audit trail outlives the user row. On account deletion the user's rows are first stripped of `ip_address`, `user_agent` and `metadata_json` (which can hold balances), keeping only the action and time, and the deletion is recorded as `user.account_deleted` without any of them. |
| `transactions.account_id` / `transfer_account_id` | RESTRICT | Ledger history must never silently disappear. Accounts are archived instead. |
| `transactions.category_id` | SET NULL | The transaction survives and falls back to "Uncategorized". |
| `transactions.recurring_transaction_id` | SET NULL | Deleting a schedule detaches, but keeps, the transactions it already generated. |
| `recurring_transactions.account_id` | RESTRICT | A schedule can't point at a deleted account. |
| `subscriptions.recurring_transaction_id` | CASCADE | The marker has no meaning without its schedule. |
| `credit_card_details.account_id` | CASCADE | It's an extension row. |
| `budget_items.category_id`, `merchant_category_rules.category_id` | CASCADE | Rules and limits for a deleted category have nothing left to apply to. |
| `receipts.transaction_id`, `linked_accounts.account_id`, `transactions.linked_account_id` | SET NULL | Keep the document and the history. |
| `login_failures` | none (no FK) | Short-lived throttle counters keyed by an email HMAC (login) or a user-id HMAC under a separate key (password change). Not user data; they expire within the throttle window. |
| `data_correction_runs` | none (no FK) | Migration bookkeeping, not user data. Never pruned and never dropped, including by `downgrade()`: it is what stops an already-applied data correction from being applied twice. |

## Migration chain

Linear, single head. Each file has both `upgrade()` and `downgrade()`.

| # | Revision | Adds |
|---|---|---|
| 1 | `9621dd83d616` | `users`, `sessions`, `audit_logs`, `user_settings` |
| 2 | `fe9868ef4632` | `accounts`, `credit_card_details`, `categories` (plus seeded defaults) |
| 3 | `2f31c6b220c0` | `transactions` |
| 4 | `141569826f73` | `budgets`, `budget_items` |
| 5 | `3ec63d03190b` | `savings_goals` |
| 6 | `8b4c4d101fb8` | `recurring_transactions` (plus `transactions.recurring_transaction_id`) |
| 7 | `7ba459b17a4e` | `subscriptions` |
| 8 | `83ee0ba75312` | `receipts` |
| 9 | `c2c554e0641a` | `notifications` |
| 10 | `540ba876a3c6` | `uq_categories_user_name_active` partial unique index |
| 11 | `c71bca4337ab` | `linked_accounts`, `sync_runs` (plus sync provenance on `transactions`) |
| 12 | `1b117abdc7f0` | `transactions.needs_review` and its partial index |
| 13 | `bf0fbd916161` | `merchant_category_rules` |
| 14 | `43b64866b554` | `user_settings.ai_categorization_enabled` |
| 15 | `5d7e1c2a9b30` | `login_failures` (per-account login throttle) |
| 16 | `a3f9c1d2e7b4` | `sessions.family_id` (backfilled to `id`; downgrade drops only the column) |
| 17 | `c8e4a1f6b2d9` | `data_correction_runs` (its own run record, kept by the downgrade). F-001 data correction: each credit card's `balance_minor` corrected by `−2·D` (gated by `-x card_balance_correction=apply`, audit-logged, relative downgrade, and refused for any card the fixed code has touched since the first run; see DEPLOYMENT.md, Lockstep deploy) |
| 18 | `d7a1e4c9b3f2` | No tables. Enables RLS on every `public` table and revokes every privilege of Supabase's `anon` and `authenticated` roles, including default privileges for future objects (see below). Downgrade keeps the protection unless `-x rls_hardening=revert`, and never re-grants (**head**) |

```bash
cd backend
.venv/Scripts/alembic heads      # expect exactly one head: d7a1e4c9b3f2
.venv/Scripts/alembic current    # which revision DATABASE_URL is at
.venv/Scripts/alembic check      # fails if the models have drifted from the migrations
```

## Access control and Supabase's Data API

Authorization lives in the application: every repository query is scoped to the authenticated
`user_id`. The database adds one boundary of its own, against Supabase's auto-generated REST
API (PostgREST). That API serves the exposed schemas (`public` by default) as the roles `anon`
and `authenticated` to anyone who has the project's publishable key. The app never uses it.

| Role | What it is | Access to app tables after `d7a1e4c9b3f2` |
|---|---|---|
| `postgres` (Supabase) / the migrating role (local, CI) | The role the backend connects as through `DATABASE_URL`. It owns every table and runs the migrations. On Supabase it is not a superuser but has `BYPASSRLS`. | Full. A table's owner is not subject to its RLS unless `FORCE ROW LEVEL SECURITY` is set, and it is not. |
| `anon`, `authenticated` | Supabase's Data API roles | None. Every table, sequence and function privilege is revoked, including the default privileges that used to grant them every new table. RLS with no policy also hides every row if a grant is ever restored by mistake. |
| `service_role` | Supabase's server-side key; bypasses RLS by design | Unchanged. Not used by this app; keep its key out of every client. |
| `supabase_admin` | Supabase's own role | Unchanged. Its default privileges can only be changed by itself, and apply only to objects it creates, never to tables these migrations create. |

Verified read-only against production on 2026-11-22: the backend's statements (Alembic's and the
app's) run as `postgres`, which owns all 20 tables, and every `anon`/`authenticated` grant on
them was made by `postgres`, so `postgres` can revoke them. The migration has **not** been
applied to production. Where the Supabase roles don't exist (local PostgreSQL, CI by default),
the migration only enables RLS.

