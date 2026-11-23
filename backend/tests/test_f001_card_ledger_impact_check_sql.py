"""Guards the operator SQL for the F-001 credit-card balance correction:
scripts/sql/f001_card_ledger_impact_check.sql (run before the migration) and
scripts/sql/f001_card_ledger_post_migration_check.sql (run after it). Both run
against shared (staging/production) databases, so they must stay provably
read-only: only SELECT/WITH queries, transaction control, and SET LOCAL
timeouts. The impact check's Part 1 aggregates are checked against
hand-computed figures."""

import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import test_engine
from tests.f001_ledger_seed import (
    IMPACT_SQL_PATH,
    POST_MIGRATION_SQL_PATH,
    PUBLIC_SCHEMA_SQL_PATH,
    as_json,
    backdate_ledger,
    book_old_code,
    insert_account,
    insert_user,
    seed_scenario,
    sql_body,
    sql_lines,
    sql_queries,
    sql_statements,
)

SCRIPTS = [
    pytest.param(IMPACT_SQL_PATH, 3, id="impact_check"),
    pytest.param(POST_MIGRATION_SQL_PATH, 3, id="post_migration_check"),
    # Not F-001, but held to the same read-only rules (migration d7a1e4c9b3f2).
    pytest.param(PUBLIC_SCHEMA_SQL_PATH, 2, id="public_schema_exposure_check"),
]

_ALLOWED_META_COMMAND = re.compile(r"^\\echo\s")
_ALLOWED_SET_LOCAL = re.compile(
    r"^SET LOCAL (statement_timeout|lock_timeout|idle_in_transaction_session_timeout) = '\d+s'$"
)
# Word-bounded, so column names such as updated_at never match UPDATE.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|COPY|CALL|DO|"
    r"VACUUM|ANALYZE|REINDEX|CLUSTER|LOCK|COMMIT|PREPARE|EXECUTE|NOTIFY|LISTEN|REFRESH|"
    r"nextval|setval|set_config|pg_sleep|pg_advisory_\w+|pg_terminate_backend|pg_cancel_backend|"
    r"dblink\w*|lo_\w+|pg_read_\w+)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize(("path", "queries"), SCRIPTS)
def test_psql_meta_commands_are_echo_only(path: Path, queries: int) -> None:
    meta = [line.strip() for line in sql_lines(path) if line.lstrip().startswith("\\")]
    assert len(meta) == queries, "expected one \\echo header per section"
    assert all(_ALLOWED_META_COMMAND.match(m) for m in meta), meta


@pytest.mark.parametrize(("path", "queries"), SCRIPTS)
def test_contains_only_read_only_statements(path: Path, queries: int) -> None:
    statements = [" ".join(s.split()) for s in sql_statements(path)]
    assert statements[0] == "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert statements[-1] == "ROLLBACK"
    for statement in statements[1:-1]:
        is_query = statement.upper().startswith(("SELECT ", "WITH "))
        assert is_query or _ALLOWED_SET_LOCAL.match(statement), statement
        assert _FORBIDDEN.search(statement) is None, statement
    assert len(sql_queries(path)) == queries


@pytest.mark.parametrize(("path", "queries"), SCRIPTS)
async def test_runs_cleanly_against_the_current_schema(path: Path, queries: int) -> None:
    async with test_engine.connect() as conn:
        raw = await conn.get_raw_connection()
        # Simple-query protocol runs the whole script, BEGIN ... ROLLBACK
        # included; PostgreSQL itself rejects any write inside READ ONLY.
        await raw.driver_connection.execute(sql_body(path))  # type: ignore[union-attr]


def test_summary_and_per_card_parts_share_one_definition() -> None:
    part1, part2, _ = sql_queries(IMPACT_SQL_PATH)
    marker = "\n)\nSELECT "
    assert marker in part1 and marker in part2
    assert part1.split(marker)[0] == part2.split(marker)[0]


async def _part1(db: AsyncSession) -> dict:
    row = (await db.execute(text(sql_queries(IMPACT_SQL_PATH)[0]))).mappings().one()
    return dict(row)


async def test_summary_aggregates_match_hand_computed_figures(db_session: AsyncSession) -> None:
    await seed_scenario(db_session)

    summary = await _part1(db_session)

    assert summary["credit_card_accounts"] == 4
    assert summary["cards_with_ledger_activity"] == 3
    assert summary["cards_needing_correction"] == 3
    assert summary["cards_with_positive_correction"] == 1
    assert summary["cards_with_negative_correction"] == 2
    assert summary["users_affected"] == 2
    # The A -> B transfer is one transaction but a leg on each card.
    assert summary["distinct_card_transactions"] == 6
    assert summary["total_card_legs"] == 7
    assert summary["card_expenses"] == 2
    assert summary["card_incomes"] == 1
    assert summary["card_transfers_out"] == 2
    assert summary["card_transfers_in"] == 2
    assert as_json(summary["correction_minor_by_currency"]) == {"INR": -34_000, "USD": 1_000}
    assert summary["cards_with_currency_mismatch"] == 0
    assert summary["currency_mismatch_legs"] == 0
    assert summary["cards_with_activity_since_previous_correction"] == 0
    assert summary["cards_blocking_migration"] == 0
    assert summary["cards_possibly_edited_by_hand"] == 0
    assert summary["cards_negative_now"] == 1
    assert summary["cards_negative_after_correction"] == 1
    assert summary["cards_over_limit_after_correction"] == 0


async def test_summary_is_all_zero_without_credit_cards(db_session: AsyncSession) -> None:
    user = await insert_user(db_session)
    bank = await insert_account(db_session, user, account_type="bank_account", balance_minor=0)
    await book_old_code(db_session, user, bank, "expense", 1_000)
    await db_session.commit()

    summary = await _part1(db_session)

    assert summary["credit_card_accounts"] == 0
    assert summary["distinct_card_transactions"] == 0
    assert summary["total_card_legs"] == 0
    assert as_json(summary["correction_minor_by_currency"]) == {}
    assert summary["cards_with_positive_correction"] == 0
    assert summary["cards_with_negative_correction"] == 0


async def test_summary_counts_cards_the_migration_would_refuse_or_flag(
    db_session: AsyncSession,
) -> None:
    user = await insert_user(db_session)
    currency_edited = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=10_000
    )
    await book_old_code(db_session, user, currency_edited, "expense", 100)
    await book_old_code(db_session, user, currency_edited, "expense", 200)
    edited_after_fix = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=10_000
    )
    await book_old_code(db_session, user, edited_after_fix, "expense", 300)
    edited_by_hand = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=10_000
    )
    await book_old_code(db_session, user, edited_by_hand, "expense", 400)
    await db_session.execute(
        text("UPDATE accounts SET currency = 'USD' WHERE id = :id"), {"id": currency_edited}
    )
    await db_session.execute(
        text(
            "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id) "
            "VALUES (gen_random_uuid(), :user_id, 'account.balance_updated', 'account', :entity)"
        ),
        {"user_id": user, "entity": str(edited_after_fix)},
    )
    await db_session.execute(
        text(
            "UPDATE accounts SET balance_minor = 5000, updated_at = now() + INTERVAL '2 minutes' "
            "WHERE id = :id"
        ),
        {"id": edited_by_hand},
    )
    await db_session.commit()

    summary = await _part1(db_session)

    assert summary["cards_with_currency_mismatch"] == 1
    assert summary["currency_mismatch_legs"] == 2
    assert summary["cards_with_post_fix_balance_edit"] == 1
    assert summary["cards_with_activity_since_previous_correction"] == 0
    assert summary["cards_blocking_migration"] == 2
    assert summary["cards_possibly_edited_by_hand"] == 1


async def test_summary_counts_cards_touched_since_a_previous_correction_run(
    db_session: AsyncSession,
) -> None:
    """H1: once the revision has run, a leg written from 60 s before that run
    onward was booked by the fixed code, so D no longer describes the card and
    the migration must refuse it. Mirrors the migration's own blocker."""
    user = await insert_user(db_session)
    settled = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=10_000
    )
    await book_old_code(db_session, user, settled, "expense", 100)
    await backdate_ledger(db_session)
    touched_since = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=10_000
    )
    await book_old_code(db_session, user, touched_since, "expense", 200)
    await db_session.execute(
        text(
            "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, created_at) "
            "VALUES (gen_random_uuid(), NULL, 'ledger.card_balance_correction', 'migration', "
            "'c8e4a1f6b2d9', now() - INTERVAL '5 minutes')"
        )
    )
    await db_session.commit()

    summary = await _part1(db_session)

    assert summary["cards_needing_correction"] == 2
    assert summary["cards_with_activity_since_previous_correction"] == 1
    assert summary["cards_blocking_migration"] == 1


async def test_summary_ignores_activity_when_the_revision_has_never_run(
    db_session: AsyncSession,
) -> None:
    user = await insert_user(db_session)
    card = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=10_000
    )
    await book_old_code(db_session, user, card, "expense", 300)
    await db_session.commit()

    summary = await _part1(db_session)

    assert summary["cards_needing_correction"] == 1
    assert summary["cards_with_activity_since_previous_correction"] == 0
    assert summary["cards_blocking_migration"] == 0
