-- F-001 credit-card ledger impact check. READ ONLY: only SELECTs, inside a READ ONLY
-- transaction that ends in ROLLBACK. Output: account UUIDs (Part 2 only) and integer
-- amounts and counts (no names, emails, merchants or descriptions).
--
-- Cash-flow convention per ledger leg: income +amount, expense -amount,
-- transfer source -amount, transfer destination +amount.
-- Old code stored card balance = opening + D; correct is opening - D; so correction = -2*D.
-- Migration c8e4a1f6b2d9 applies exactly these per-card figures.
--
-- Only meaningful BEFORE the liability-aware ledger code is deployed: card
-- transactions booked by the fixed code are already correct and must not be
-- counted into D.
--
-- Review signals (Part 2 columns, Part 1 counts):
--   currency_mismatch_legs > 0    the account's currency was edited after legs were booked,
--                                 so D would mix currencies. Blocks the migration.
--   has_balance_audit             an account.balance_updated row exists; only the fixed code
--                                 writes those, so the old-sign formula doesn't describe this
--                                 card. Blocks the migration.
--   legs_since_previous_correction > 0
--                                 a leg was written from 60s before this revision's FIRST
--                                 run onward, so the fixed code booked it and D would
--                                 double-count it. Blocks the migration. This is the
--                                 downgrade-then-re-upgrade case; on a database where the
--                                 revision has never run it is always 0.
--                                 This script dates the run from audit_logs alone. The
--                                 migration itself also reads data_correction_runs and takes
--                                 whichever record is earlier, so it can still refuse a card
--                                 this script reports as clean if the audit rows were purged.
--                                 The migration is the authority; this script is advisory.
--   updated_after_last_ledger_write
--                                 the account row changed more than 60s after its last ledger
--                                 write: possibly a hand-entered balance under the old code
--                                 (or a rename, or a deleted transaction). Review, not a block.
--   negative or over limit after correction: review, not a block.
--
-- Limits of detection. Two edits under the old code leave nothing to find:
--   * a balance typed in through PUT /accounts before this fix shipped (the
--     account.balance_updated audit row is part of the same fix), and
--   * a card transaction deleted by the old code.
-- Both silently shift the stored balance away from opening + D, and this script cannot
-- tell either from a correct balance. updated_after_last_ledger_write is the only hint
-- and it is noisy in both directions: a rename or a deleted transaction trips it, while an
-- edit made within 60s of a ledger write does not. Treat a clean report as "no evidence
-- of a manual edit", never as proof there was none. See docs/DEPLOYMENT.md,
-- "Limits of detection", for what to do about it.
--
-- Usage (URL from an environment variable, never typed on the command line):
--   psql "$DB_URL" -X -v ON_ERROR_STOP=1 -f scripts/sql/f001_card_ledger_impact_check.sql
-- Guarded by backend/tests/test_f001_card_ledger_impact_check_sql.py.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '120s';

\echo '== Part 1: summary =='
WITH previous_run AS (
    SELECT MIN(created_at) AS ran_at FROM audit_logs
    WHERE action = 'ledger.card_balance_correction'
      AND entity_type = 'migration' AND entity_id = 'c8e4a1f6b2d9'
),
legs AS (
    SELECT t.id AS transaction_id, t.account_id AS account_id, t.type AS tx_type, 'source' AS leg,
           CASE t.type WHEN 'income' THEN t.amount_minor ELSE -t.amount_minor END AS cash_flow_minor,
           t.currency, t.created_at, t.updated_at
    FROM transactions t
    UNION ALL
    SELECT t.id, t.transfer_account_id, t.type, 'destination', t.amount_minor, t.currency,
           t.created_at, t.updated_at
    FROM transactions t
    WHERE t.type = 'transfer' AND t.transfer_account_id IS NOT NULL
),
impact AS (
    SELECT a.id AS account_id, a.user_id, a.is_active, a.currency AS account_currency,
           a.balance_minor AS stored_balance_minor, ccd.credit_limit_minor,
           COALESCE(SUM(l.cash_flow_minor), 0) AS cash_flow_delta_minor,
           -2 * COALESCE(SUM(l.cash_flow_minor), 0) AS correction_minor,
           a.balance_minor - 2 * COALESCE(SUM(l.cash_flow_minor), 0) AS corrected_balance_minor,
           COUNT(l.account_id) AS legs,
           COUNT(*) FILTER (WHERE l.tx_type = 'expense') AS expenses,
           COUNT(*) FILTER (WHERE l.tx_type = 'income') AS incomes,
           COUNT(*) FILTER (WHERE l.tx_type = 'transfer' AND l.leg = 'source') AS transfers_out,
           COUNT(*) FILTER (WHERE l.tx_type = 'transfer' AND l.leg = 'destination') AS transfers_in,
           COUNT(*) FILTER (WHERE l.account_id IS NOT NULL AND l.currency <> a.currency) AS currency_mismatch_legs,
           COUNT(*) FILTER (WHERE l.account_id IS NOT NULL
                              AND l.updated_at >= (SELECT ran_at FROM previous_run)
                                                  - INTERVAL '60 seconds') AS legs_since_previous_correction,
           MIN(l.created_at) AS first_leg_at, MAX(l.created_at) AS last_leg_at,
           MAX(l.updated_at) AS last_leg_write_at,
           a.updated_at AS account_updated_at,
           COALESCE(a.updated_at > MAX(l.updated_at) + INTERVAL '60 seconds', false)
               AS updated_after_last_ledger_write,
           EXISTS (SELECT 1 FROM audit_logs al
                   WHERE al.action = 'account.balance_updated'
                     AND al.entity_type = 'account' AND al.entity_id = a.id::text) AS has_balance_audit
    FROM accounts a
    LEFT JOIN credit_card_details ccd ON ccd.account_id = a.id
    LEFT JOIN legs l ON l.account_id = a.id
    WHERE a.type = 'credit_card'
    GROUP BY a.id, a.user_id, a.is_active, a.currency, a.balance_minor, ccd.credit_limit_minor, a.updated_at
)
SELECT COUNT(*)                                                    AS credit_card_accounts,
       COUNT(*) FILTER (WHERE legs > 0)                            AS cards_with_ledger_activity,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0)          AS cards_needing_correction,
       COUNT(*) FILTER (WHERE correction_minor > 0)                AS cards_with_positive_correction,
       COUNT(*) FILTER (WHERE correction_minor < 0)                AS cards_with_negative_correction,
       COUNT(DISTINCT user_id) FILTER (WHERE cash_flow_delta_minor <> 0) AS users_affected,
       (SELECT COUNT(DISTINCT l.transaction_id) FROM legs l
          JOIN accounts ca ON ca.id = l.account_id AND ca.type = 'credit_card')
                                                                   AS distinct_card_transactions,
       COALESCE(SUM(legs), 0)                                      AS total_card_legs,
       COALESCE(SUM(expenses), 0)                                  AS card_expenses,
       COALESCE(SUM(incomes), 0)                                   AS card_incomes,
       COALESCE(SUM(transfers_out), 0)                             AS card_transfers_out,
       COALESCE(SUM(transfers_in), 0)                              AS card_transfers_in,
       (SELECT COALESCE(jsonb_object_agg(account_currency, total_minor), '{}'::jsonb)
          FROM (SELECT account_currency, SUM(correction_minor) AS total_minor FROM impact
                 WHERE correction_minor <> 0 GROUP BY account_currency) per_currency)
                                                                   AS correction_minor_by_currency,
       COUNT(*) FILTER (WHERE currency_mismatch_legs > 0)          AS cards_with_currency_mismatch,
       COALESCE(SUM(currency_mismatch_legs), 0)                    AS currency_mismatch_legs,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND has_balance_audit)
                                                                   AS cards_with_post_fix_balance_edit,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND legs_since_previous_correction > 0)
                                                                   AS cards_with_activity_since_previous_correction,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0
                          AND (currency_mismatch_legs > 0 OR has_balance_audit
                               OR legs_since_previous_correction > 0))
                                                                   AS cards_blocking_migration,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND updated_after_last_ledger_write)
                                                                   AS cards_possibly_edited_by_hand,
       COUNT(*) FILTER (WHERE stored_balance_minor < 0)            AS cards_negative_now,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND corrected_balance_minor < 0)
                                                                   AS cards_negative_after_correction,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND credit_limit_minor > 0
                          AND corrected_balance_minor > credit_limit_minor)
                                                                   AS cards_over_limit_after_correction
FROM impact;

\echo '== Part 2: cards the correction would change =='
WITH previous_run AS (
    SELECT MIN(created_at) AS ran_at FROM audit_logs
    WHERE action = 'ledger.card_balance_correction'
      AND entity_type = 'migration' AND entity_id = 'c8e4a1f6b2d9'
),
legs AS (
    SELECT t.id AS transaction_id, t.account_id AS account_id, t.type AS tx_type, 'source' AS leg,
           CASE t.type WHEN 'income' THEN t.amount_minor ELSE -t.amount_minor END AS cash_flow_minor,
           t.currency, t.created_at, t.updated_at
    FROM transactions t
    UNION ALL
    SELECT t.id, t.transfer_account_id, t.type, 'destination', t.amount_minor, t.currency,
           t.created_at, t.updated_at
    FROM transactions t
    WHERE t.type = 'transfer' AND t.transfer_account_id IS NOT NULL
),
impact AS (
    SELECT a.id AS account_id, a.user_id, a.is_active, a.currency AS account_currency,
           a.balance_minor AS stored_balance_minor, ccd.credit_limit_minor,
           COALESCE(SUM(l.cash_flow_minor), 0) AS cash_flow_delta_minor,
           -2 * COALESCE(SUM(l.cash_flow_minor), 0) AS correction_minor,
           a.balance_minor - 2 * COALESCE(SUM(l.cash_flow_minor), 0) AS corrected_balance_minor,
           COUNT(l.account_id) AS legs,
           COUNT(*) FILTER (WHERE l.tx_type = 'expense') AS expenses,
           COUNT(*) FILTER (WHERE l.tx_type = 'income') AS incomes,
           COUNT(*) FILTER (WHERE l.tx_type = 'transfer' AND l.leg = 'source') AS transfers_out,
           COUNT(*) FILTER (WHERE l.tx_type = 'transfer' AND l.leg = 'destination') AS transfers_in,
           COUNT(*) FILTER (WHERE l.account_id IS NOT NULL AND l.currency <> a.currency) AS currency_mismatch_legs,
           COUNT(*) FILTER (WHERE l.account_id IS NOT NULL
                              AND l.updated_at >= (SELECT ran_at FROM previous_run)
                                                  - INTERVAL '60 seconds') AS legs_since_previous_correction,
           MIN(l.created_at) AS first_leg_at, MAX(l.created_at) AS last_leg_at,
           MAX(l.updated_at) AS last_leg_write_at,
           a.updated_at AS account_updated_at,
           COALESCE(a.updated_at > MAX(l.updated_at) + INTERVAL '60 seconds', false)
               AS updated_after_last_ledger_write,
           EXISTS (SELECT 1 FROM audit_logs al
                   WHERE al.action = 'account.balance_updated'
                     AND al.entity_type = 'account' AND al.entity_id = a.id::text) AS has_balance_audit
    FROM accounts a
    LEFT JOIN credit_card_details ccd ON ccd.account_id = a.id
    LEFT JOIN legs l ON l.account_id = a.id
    WHERE a.type = 'credit_card'
    GROUP BY a.id, a.user_id, a.is_active, a.currency, a.balance_minor, ccd.credit_limit_minor, a.updated_at
)
SELECT account_id, is_active, account_currency,
       stored_balance_minor, cash_flow_delta_minor, correction_minor, corrected_balance_minor,
       credit_limit_minor, legs, expenses, incomes, transfers_out, transfers_in,
       currency_mismatch_legs, legs_since_previous_correction,
       has_balance_audit, updated_after_last_ledger_write,
       first_leg_at, last_leg_at, last_leg_write_at, account_updated_at
FROM impact
WHERE cash_flow_delta_minor <> 0
ORDER BY ABS(correction_minor) DESC, account_id;

\echo '== Part 3: other references to card accounts =='
SELECT
  (SELECT COUNT(*) FROM recurring_transactions r JOIN accounts a ON a.id = r.account_id
    WHERE a.type = 'credit_card') AS recurring_on_cards,
  (SELECT COUNT(*) FROM receipts rc JOIN transactions t ON t.id = rc.transaction_id
    JOIN accounts a ON a.id = t.account_id WHERE a.type = 'credit_card') AS receipt_txns_on_cards,
  (SELECT COUNT(*) FROM linked_accounts la JOIN accounts a ON a.id = la.account_id
    WHERE a.type = 'credit_card') AS linked_accounts_on_cards;

ROLLBACK;
