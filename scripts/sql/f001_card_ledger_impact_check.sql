-- F-001 credit-card ledger impact check. READ ONLY: only SELECTs, inside a READ ONLY
-- transaction that ends in ROLLBACK. Output: account UUIDs and integer amounts only
-- (no names, emails, merchants or descriptions).
--
-- Cash-flow convention per ledger leg: income +amount, expense -amount,
-- transfer source -amount, transfer destination +amount.
-- Old code stored card balance = opening + D; correct is opening - D; so correction = -2*D.
--
-- Only meaningful BEFORE the liability-aware ledger code is deployed: card
-- transactions booked by the fixed code are already correct and must not be
-- counted into D.
--
-- Usage (URL from an environment variable, never typed on the command line):
--   psql "$DB_URL" -X -v ON_ERROR_STOP=1 -f scripts/sql/f001_card_ledger_impact_check.sql
-- Guarded by backend/tests/test_f001_card_ledger_impact_check_sql.py.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '120s';

\echo '== Part 1: summary =='
WITH legs AS (
    SELECT t.account_id AS account_id, t.type AS tx_type, 'source' AS leg,
           CASE t.type WHEN 'income' THEN t.amount_minor ELSE -t.amount_minor END AS cash_flow_minor,
           t.currency, t.created_at
    FROM transactions t
    UNION ALL
    SELECT t.transfer_account_id, t.type, 'destination', t.amount_minor, t.currency, t.created_at
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
           MIN(l.created_at) AS first_leg_at, MAX(l.created_at) AS last_leg_at,
           a.updated_at AS account_updated_at
    FROM accounts a
    LEFT JOIN credit_card_details ccd ON ccd.account_id = a.id
    LEFT JOIN legs l ON l.account_id = a.id
    WHERE a.type = 'credit_card'
    GROUP BY a.id, a.user_id, a.is_active, a.currency, a.balance_minor, ccd.credit_limit_minor, a.updated_at
)
SELECT COUNT(*)                                                    AS credit_card_accounts,
       COUNT(*) FILTER (WHERE legs > 0)                            AS cards_with_ledger_activity,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0)          AS cards_needing_correction,
       COUNT(DISTINCT user_id) FILTER (WHERE cash_flow_delta_minor <> 0) AS users_affected,
       COALESCE(SUM(legs), 0)                                      AS total_card_legs,
       COALESCE(SUM(expenses), 0)                                  AS card_expenses,
       COALESCE(SUM(incomes), 0)                                   AS card_incomes,
       COALESCE(SUM(transfers_out), 0)                             AS card_transfers_out,
       COALESCE(SUM(transfers_in), 0)                              AS card_transfers_in,
       COUNT(*) FILTER (WHERE stored_balance_minor < 0)            AS cards_negative_now,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND corrected_balance_minor < 0)
                                                                   AS cards_negative_after_correction,
       COUNT(*) FILTER (WHERE cash_flow_delta_minor <> 0 AND credit_limit_minor > 0
                          AND corrected_balance_minor > credit_limit_minor)
                                                                   AS cards_over_limit_after_correction,
       COALESCE(SUM(currency_mismatch_legs), 0)                    AS currency_mismatch_legs
FROM impact;

\echo '== Part 2: cards the correction would change =='
WITH legs AS (
    SELECT t.account_id AS account_id, t.type AS tx_type, 'source' AS leg,
           CASE t.type WHEN 'income' THEN t.amount_minor ELSE -t.amount_minor END AS cash_flow_minor,
           t.currency, t.created_at
    FROM transactions t
    UNION ALL
    SELECT t.transfer_account_id, t.type, 'destination', t.amount_minor, t.currency, t.created_at
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
           MIN(l.created_at) AS first_leg_at, MAX(l.created_at) AS last_leg_at,
           a.updated_at AS account_updated_at
    FROM accounts a
    LEFT JOIN credit_card_details ccd ON ccd.account_id = a.id
    LEFT JOIN legs l ON l.account_id = a.id
    WHERE a.type = 'credit_card'
    GROUP BY a.id, a.user_id, a.is_active, a.currency, a.balance_minor, ccd.credit_limit_minor, a.updated_at
)
SELECT account_id, is_active, account_currency,
       stored_balance_minor, cash_flow_delta_minor, correction_minor, corrected_balance_minor,
       credit_limit_minor, legs, expenses, incomes, transfers_out, transfers_in,
       currency_mismatch_legs, first_leg_at, last_leg_at, account_updated_at
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
