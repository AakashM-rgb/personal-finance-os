-- F-001 post-migration check, run after migration c8e4a1f6b2d9 (credit-card balance
-- correction). READ ONLY: only SELECTs, inside a READ ONLY transaction that ends in
-- ROLLBACK. Output: counts, amounts and timestamps only (no account or user ids).
--
-- Part 1 is the migration's own summary audit row: NULL columns mean the revision hasn't
-- run. Part 2 counts per-card audit rows. Part 3 catches card ledger writes around and
-- after the correction. The fixed backend books those correctly, but a write by a
-- still-running OLD backend (a deploy whose old and new instances overlapped) carries the
-- old sign and isn't covered by the correction. With the backend stopped (or in
-- maintenance mode) for the whole deploy, there must be no card ledger write between one
-- minute before correction_ran_at and the moment the new backend went live (for Render,
-- the new deploy's finish time). Any write in that span means the cards it touched need
-- review. The window opens a minute early because a request blocked by the migration's
-- lock stamps its rows with its own, earlier start time. Deletes by the old backend leave
-- no row, so this check can't see them.
--
-- Usage (URL from an environment variable, never typed on the command line):
--   psql "$DB_URL" -X -v ON_ERROR_STOP=1 -f scripts/sql/f001_card_ledger_post_migration_check.sql
-- Guarded by backend/tests/test_f001_card_ledger_impact_check_sql.py.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '120s';

\echo '== Part 1: migration summary =='
SELECT (SELECT string_agg(version_num, ',') FROM alembic_version) AS alembic_version,
       run.created_at                                             AS correction_ran_at,
       run.metadata_json ->> 'mode'                               AS mode,
       (run.metadata_json ->> 'cards_checked')::int               AS cards_checked,
       (run.metadata_json ->> 'cards_corrected')::int             AS cards_corrected,
       (run.metadata_json ->> 'cards_skipped')::int               AS cards_skipped,
       run.metadata_json -> 'correction_minor_by_currency'        AS correction_minor_by_currency
FROM (SELECT 1) AS one
LEFT JOIN LATERAL (
    SELECT al.created_at, al.metadata_json FROM audit_logs al
    WHERE al.action = 'ledger.card_balance_correction' AND al.entity_id = 'c8e4a1f6b2d9'
    ORDER BY al.created_at DESC
    LIMIT 1
) AS run ON true;

\echo '== Part 2: per-card audit rows =='
SELECT COUNT(*) FILTER (WHERE al.action = 'account.balance_corrected')          AS cards_corrected,
       COUNT(*) FILTER (WHERE al.action = 'account.balance_correction_skipped') AS cards_skipped,
       COUNT(*) FILTER (WHERE al.action = 'account.balance_corrected'
                          AND al.metadata_json -> 'review_signals' <> '[]'::jsonb)
                                                                                AS corrected_with_review_signals,
       COUNT(*) FILTER (WHERE a.id IS NULL)                                     AS rows_for_deleted_accounts
FROM audit_logs al
LEFT JOIN accounts a ON a.id::text = al.entity_id
WHERE al.action IN ('account.balance_corrected', 'account.balance_correction_skipped')
  AND al.metadata_json ->> 'revision' = 'c8e4a1f6b2d9';

\echo '== Part 3: card ledger writes around and after the correction =='
WITH run AS (
    SELECT MAX(created_at) AS ran_at FROM audit_logs
    WHERE action = 'ledger.card_balance_correction' AND entity_id = 'c8e4a1f6b2d9'
),
card_legs AS (
    SELECT t.updated_at AS written_at
    FROM transactions t
    JOIN accounts a ON a.id IN (t.account_id, t.transfer_account_id) AND a.type = 'credit_card'
)
SELECT run.ran_at                                                          AS correction_ran_at,
       COUNT(card_legs.written_at)                                         AS card_legs_written_in_window,
       MIN(card_legs.written_at)                                           AS first_card_leg_write_in_window,
       MAX(card_legs.written_at)                                           AS last_card_leg_write_in_window
FROM run
LEFT JOIN card_legs ON card_legs.written_at >= run.ran_at - INTERVAL '1 minute'
GROUP BY run.ran_at;

ROLLBACK;
