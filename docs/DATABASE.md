# Database Schema

PostgreSQL, managed only through Alembic (`backend/migrations/`). This page was written from
`backend/app/models/*.py` and `backend/migrations/versions/*.py` at migration head
`43b64866b554`. Where it disagrees with the code, the code wins.

## Conventions (every table)

| Convention | Where it's enforced |
|---|---|
| UUID primary key `id` | `UUIDPrimaryKeyMixin` (`app/models/base.py`) |
| `created_at` / `updated_at` (timestamptz) | `TimestampMixin`. `audit_logs` has `created_at` only. |
| Money is `BIGINT` integer minor units (paise), named `*_minor` | Every money column. No float/real money columns exist. |
| Transaction amounts are always positive. The sign comes from `type`. | `CHECK (amount_minor > 0)` |
| Enums are stored as strings (`native_enum=False`), not Postgres enum types | `str_enum_column` in `app/models/base.py` |
| User-owned rows carry `user_id → users.id ON DELETE CASCADE` | Deleting a user removes all of their data. `audit_logs` is the exception (`SET NULL`), so the audit trail survives. |
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
```

## Tables

### Identity and security

| Table | Key columns | Constraints / notes |
|---|---|---|
| `users` | `email` (unique, indexed), `password_hash` (Argon2 via passlib), `full_name`, `is_active`, `email_verified_at` | `email_verified_at` exists as a column, but no verification flow is implemented yet (see README, current status). |
| `user_settings` | `user_id` (unique), `currency` (default `INR`), `theme`, `ai_enabled` (default true), `ai_categorization_enabled` (default false), `notification_preferences` (JSONB) | 1:1 with `users`. `currency` is the base currency that every aggregate is computed in. |
| `sessions` | `user_id`, `refresh_token_hash`, `user_agent`, `ip_address`, `expires_at`, `revoked_at` | Backs refresh-token rotation and "log out everywhere". Only a hash is stored, never the raw token. |
| `audit_logs` | `user_id` (nullable, SET NULL), `action` (indexed), `entity_type`, `entity_id`, `ip_address`, `user_agent`, `metadata_json` | Actions currently written: `user.register`, `user.login`, `user.login_failed`, `user.logout_all`, `session.reuse_detected`, `linked_account.link_initiated`, `linked_account.link_completed`, `linked_account.revoked`, `linked_account.sync_triggered`. |

### Core ledger

| Table | Key columns | Constraints / notes |
|---|---|---|
| `accounts` | `user_id`, `name`, `type` (`bank_account`, `cash`, `credit_card`, `upi`, `savings_account`, `wallet`), `balance_minor`, `currency`, `institution_name`, `is_active` | Soft-deleted (archived) through `is_active`. Transactions reference accounts with `RESTRICT`, so an account with history is never hard-deleted. For `credit_card`, `balance_minor` is the amount owed (a liability in net worth). |
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
  collide.
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
| any `user_id → users` | CASCADE | Account deletion must remove all of the user's data. |
| `audit_logs.user_id` | SET NULL | The audit trail outlives the user row. |
| `transactions.account_id` / `transfer_account_id` | RESTRICT | Ledger history must never silently disappear. Accounts are archived instead. |
| `transactions.category_id` | SET NULL | The transaction survives and falls back to "Uncategorized". |
| `transactions.recurring_transaction_id` | SET NULL | Deleting a schedule detaches, but keeps, the transactions it already generated. |
| `recurring_transactions.account_id` | RESTRICT | A schedule can't point at a deleted account. |
| `subscriptions.recurring_transaction_id` | CASCADE | The marker has no meaning without its schedule. |
| `credit_card_details.account_id` | CASCADE | It's an extension row. |
| `budget_items.category_id`, `merchant_category_rules.category_id` | CASCADE | Rules and limits for a deleted category have nothing left to apply to. |
| `receipts.transaction_id`, `linked_accounts.account_id`, `transactions.linked_account_id` | SET NULL | Keep the document and the history. |

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
| 14 | `43b64866b554` | `user_settings.ai_categorization_enabled` (**head**) |

```bash
cd backend
.venv/Scripts/alembic heads      # expect exactly one head: 43b64866b554
.venv/Scripts/alembic current    # which revision DATABASE_URL is at
.venv/Scripts/alembic check      # fails if the models have drifted from the migrations
```
