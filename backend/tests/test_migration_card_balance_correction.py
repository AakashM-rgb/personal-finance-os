"""Migration c8e4a1f6b2d9 (F-001 credit-card balance correction) against the
test database, with ledger rows seeded as the pre-fix backend booked them.

What must hold: nothing changes without `-x card_balance_correction=apply`
unless there is nothing to correct; cards the formula can't describe block the
upgrade unless skipped by id; every change is audit-logged; transactions are
never touched; downgrade reverts exactly the recorded correction, needs
`=revert`, and refuses a balance set by hand after the correction; and a
re-upgrade refuses any card the fixed backend has booked a leg on since the
previous run, whose balance the old-sign formula no longer describes.

Runs Alembic in a subprocess because env.py drives its own event loop. Always
leaves the database at head, and drops pooled connections afterwards."""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.alembic_runner import run_alembic as _run_alembic
from tests.f001_ledger_seed import (
    IMPACT_SQL_PATH,
    SCENARIO_BANK_BALANCE,
    SCENARIO_CORRECTED,
    SCENARIO_STORED,
    Scenario,
    as_json,
    backdate_ledger,
    balance,
    book_fixed_code,
    book_old_code,
    insert_account,
    insert_user,
    seed_scenario,
    sql_queries,
)

REVISION = "c8e4a1f6b2d9"
PREVIOUS_REVISION = "a3f9c1d2e7b4"
RUN_TABLE = "data_correction_runs"
APPLY = ("-x", "card_balance_correction=apply")
REVERT = ("-x", "card_balance_correction=revert")


def _alembic(*args: str) -> None:
    # Only the exit status is surfaced: Alembic's output can include the URL.
    assert _run_alembic(*args).returncode == 0, f"alembic {' '.join(args)} failed"


def _alembic_refuses(*args: str, reason: str) -> None:
    result = _run_alembic(*args)
    assert result.returncode != 0, f"alembic {' '.join(args)} unexpectedly succeeded"
    assert "CardBalanceCorrectionRefused" in result.stderr, "failed for another reason"
    assert reason in result.stderr, f"refusal did not mention {reason!r}"


def _skip(*account_ids: uuid.UUID) -> tuple[str, str]:
    return ("-x", "card_balance_correction_skip=" + ",".join(str(i) for i in account_ids))


async def _clear_data(db: AsyncSession) -> None:
    await db.execute(text("DELETE FROM audit_logs"))
    await db.execute(text("DELETE FROM login_failures"))
    await db.execute(text("DELETE FROM users"))
    await db.commit()
    await _clear_run_rows(db)


async def _clear_run_rows(db: AsyncSession) -> None:
    # Created by the revision under test, so it is absent before its first run.
    if await db.scalar(text(f"SELECT to_regclass('{RUN_TABLE}')")) is not None:
        await db.execute(text(f"DELETE FROM {RUN_TABLE}"))
    await db.commit()


async def _run_rows(db: AsyncSession) -> list[tuple[str, str]]:
    rows = await db.execute(
        text(f"SELECT direction, mode FROM {RUN_TABLE} WHERE revision = :r ORDER BY ran_at"),
        {"r": REVISION},
    )
    result = [(row.direction, row.mode) for row in rows]
    await db.commit()
    return result


async def _audit_row_count(db: AsyncSession) -> int:
    value = await db.scalar(text("SELECT count(*) FROM audit_logs"))
    await db.commit()
    return int(value or 0)


async def _purge_audit_logs(db: AsyncSession) -> None:
    """What a retention job, a manual cleanup or a partial restore would do."""
    await db.execute(text("DELETE FROM audit_logs"))
    await db.commit()


@pytest_asyncio.fixture
async def at_previous_revision(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    await _clear_data(db_session)
    await db_session.close()
    _alembic("downgrade", PREVIOUS_REVISION)
    # That downgrade records its own (no-op) run row; drop it so each test
    # starts from a database on which this revision has never run.
    await _clear_run_rows(db_session)
    await db_session.close()
    try:
        yield
    finally:
        # Data a test left uncorrected would make the upgrade back to head refuse.
        await _clear_data(db_session)
        await db_session.close()
        _alembic("upgrade", "head")
        assert db_session.bind is not None
        await db_session.bind.dispose()  # type: ignore[union-attr]


async def _owner(db: AsyncSession, account_id: uuid.UUID) -> uuid.UUID:
    value = await db.scalar(
        text("SELECT user_id FROM accounts WHERE id = :id"), {"id": account_id}
    )
    assert value is not None
    return uuid.UUID(str(value))


async def _version(db: AsyncSession) -> str:
    value = await db.scalar(text("SELECT version_num FROM alembic_version"))
    await db.commit()
    return str(value)


async def _audit_rows(db: AsyncSession, action: str) -> list[dict]:
    rows = await db.execute(
        text(
            "SELECT user_id, entity_type, entity_id, metadata_json FROM audit_logs "
            "WHERE action = :action ORDER BY entity_id"
        ),
        {"action": action},
    )
    result = [{**row._mapping, "metadata_json": as_json(row.metadata_json)} for row in rows]
    await db.commit()
    return result


async def _transactions_snapshot(db: AsyncSession) -> list[tuple]:
    rows = await db.execute(
        text(
            "SELECT id, account_id, transfer_account_id, type, amount_minor, currency, "
            "updated_at FROM transactions ORDER BY id"
        )
    )
    result = [tuple(row) for row in rows]
    await db.commit()
    return result


async def _balances(db: AsyncSession, scenario: Scenario) -> dict[str, int]:
    result = {
        name: await balance(db, getattr(scenario, name))
        for name in ("card_a", "card_b", "card_c", "usd_card")
    }
    await db.commit()
    return result


async def test_no_card_to_correct_upgrades_without_a_flag_and_records_a_summary(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    user = await insert_user(db_session)
    bank = await insert_account(db_session, user, account_type="bank_account", balance_minor=5_000)
    await book_old_code(db_session, user, bank, "expense", 1_000)
    idle_card = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=2_500, credit_limit_minor=9_000
    )
    await db_session.commit()
    await db_session.close()

    _alembic("upgrade", REVISION)

    assert await _version(db_session) == REVISION
    assert await balance(db_session, bank) == 4_000
    assert await balance(db_session, idle_card) == 2_500
    assert await _audit_rows(db_session, "account.balance_corrected") == []
    [summary] = await _audit_rows(db_session, "ledger.card_balance_correction")
    assert summary["user_id"] is None
    assert summary["entity_type"] == "migration"
    assert summary["entity_id"] == REVISION
    assert summary["metadata_json"] == {
        "mode": "none",
        "cards_checked": 1,
        "cards_corrected": 0,
        "cards_skipped": 0,
        "correction_minor_by_currency": {},
    }


async def test_refuses_without_the_apply_flag_and_changes_nothing(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    scenario = await seed_scenario(db_session)
    before = await _transactions_snapshot(db_session)
    await db_session.close()

    _alembic_refuses("upgrade", REVISION, reason="3 credit card(s) need a balance correction")

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await _balances(db_session, scenario) == SCENARIO_STORED
    assert await _transactions_snapshot(db_session) == before
    assert await _audit_rows(db_session, "ledger.card_balance_correction") == []


async def test_apply_corrects_each_card_by_minus_two_d_and_audits_it(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    scenario = await seed_scenario(db_session)
    before = await _transactions_snapshot(db_session)
    await db_session.close()

    _alembic(*APPLY, "upgrade", REVISION)

    assert await _version(db_session) == REVISION
    assert await _balances(db_session, scenario) == SCENARIO_CORRECTED
    assert await balance(db_session, scenario.bank) == SCENARIO_BANK_BALANCE
    assert await _transactions_snapshot(db_session) == before

    corrected = {
        row["entity_id"]: row for row in await _audit_rows(db_session, "account.balance_corrected")
    }
    assert set(corrected) == {str(scenario.card_a), str(scenario.card_b), str(scenario.usd_card)}
    card_a = corrected[str(scenario.card_a)]["metadata_json"]
    assert card_a == {
        "revision": REVISION,
        "currency": "INR",
        "previous_balance_minor": 66_000,
        "cash_flow_delta_minor": 16_000,
        "correction_minor": -32_000,
        "new_balance_minor": 34_000,
        "ledger_legs": 5,
        "review_signals": [],
    }
    card_b = corrected[str(scenario.card_b)]["metadata_json"]
    assert card_b["correction_minor"] == -2_000
    assert card_b["review_signals"] == ["credit_balance_after_correction"]
    assert corrected[str(scenario.usd_card)]["metadata_json"]["correction_minor"] == 1_000

    [summary] = await _audit_rows(db_session, "ledger.card_balance_correction")
    assert summary["metadata_json"] == {
        "mode": "apply",
        "cards_checked": 4,
        "cards_corrected": 3,
        "cards_skipped": 0,
        "correction_minor_by_currency": {"INR": -34_000, "USD": 1_000},
    }


async def test_applies_exactly_what_the_impact_check_reported(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    await seed_scenario(db_session)
    part2 = sql_queries(IMPACT_SQL_PATH)[1]
    reported = {
        str(row.account_id): (row.stored_balance_minor, row.correction_minor)
        for row in await db_session.execute(text(part2))
    }
    await db_session.commit()
    await db_session.close()

    _alembic(*APPLY, "upgrade", REVISION)

    applied = {
        row["entity_id"]: (
            row["metadata_json"]["previous_balance_minor"],
            row["metadata_json"]["correction_minor"],
        )
        for row in await _audit_rows(db_session, "account.balance_corrected")
    }
    assert applied == reported


async def test_card_with_a_currency_mismatch_blocks_until_skipped(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    user = await insert_user(db_session)
    card = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=9_000
    )
    await book_old_code(db_session, user, card, "expense", 700)
    await db_session.execute(
        text("UPDATE accounts SET currency = 'USD' WHERE id = :id"), {"id": card}
    )
    await db_session.commit()
    await db_session.close()

    _alembic_refuses(*APPLY, "upgrade", REVISION, reason="currency_mismatch")
    assert await _version(db_session) == PREVIOUS_REVISION

    _alembic(*APPLY, *_skip(card), "upgrade", REVISION)

    assert await balance(db_session, card) == -700
    [skipped] = await _audit_rows(db_session, "account.balance_correction_skipped")
    assert skipped["entity_id"] == str(card)
    assert skipped["metadata_json"]["unapplied_correction_minor"] == 1_400
    assert skipped["metadata_json"]["blockers"] == ["currency_mismatch"]
    [summary] = await _audit_rows(db_session, "ledger.card_balance_correction")
    assert summary["metadata_json"]["cards_skipped"] == 1
    assert summary["metadata_json"]["cards_corrected"] == 0


async def test_card_with_a_post_fix_balance_edit_blocks_the_upgrade(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    user = await insert_user(db_session)
    card = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=9_000
    )
    await book_old_code(db_session, user, card, "expense", 700)
    await db_session.execute(
        text(
            "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id) "
            "VALUES (gen_random_uuid(), :user_id, 'account.balance_updated', 'account', :entity)"
        ),
        {"user_id": user, "entity": str(card)},
    )
    await db_session.commit()
    await db_session.close()

    _alembic_refuses(*APPLY, "upgrade", REVISION, reason="balance_set_after_ledger_fix")

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await balance(db_session, card) == -700


async def test_rejects_unknown_options_and_skip_ids_that_need_no_correction(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    scenario = await seed_scenario(db_session)
    await db_session.close()

    _alembic_refuses(
        "-x", "card_balance_correction=yes", "upgrade", REVISION, reason="must be 'apply'"
    )
    _alembic_refuses(
        "-x", "card_balance_correction_skp=x", "upgrade", REVISION, reason="Unknown option"
    )
    _alembic_refuses(*APPLY, *_skip(scenario.card_c), "upgrade", REVISION, reason="nothing to skip")
    _alembic_refuses(
        *APPLY, "-x", "card_balance_correction_skip=not-a-uuid", "upgrade", REVISION,
        reason="Invalid account id",
    )

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await _balances(db_session, scenario) == SCENARIO_STORED


async def test_downgrade_reverts_exactly_the_recorded_correction(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    scenario = await seed_scenario(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    # A purchase booked by the fixed backend after the correction raises the
    # amount owed; reverting the correction must keep it.
    await db_session.execute(
        text("UPDATE accounts SET balance_minor = balance_minor + 7000 WHERE id = :id"),
        {"id": scenario.card_a},
    )
    await db_session.commit()
    await db_session.close()

    _alembic_refuses("downgrade", PREVIOUS_REVISION, reason="card_balance_correction=revert")
    assert await _version(db_session) == REVISION

    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await _balances(db_session, scenario) == {
        **SCENARIO_STORED,
        "card_a": SCENARIO_STORED["card_a"] + 7_000,
    }
    reverted = await _audit_rows(db_session, "account.balance_correction_reverted")
    assert {row["entity_id"] for row in reverted} == {
        str(scenario.card_a), str(scenario.card_b), str(scenario.usd_card)
    }
    card_a = next(r for r in reverted if r["entity_id"] == str(scenario.card_a))
    assert card_a["metadata_json"]["previous_balance_minor"] == 41_000
    assert card_a["metadata_json"]["reverted_correction_minor"] == -32_000
    assert card_a["metadata_json"]["new_balance_minor"] == 73_000


async def test_downgrade_refuses_a_balance_set_by_hand_after_the_correction(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    scenario = await seed_scenario(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    await db_session.execute(
        text("UPDATE accounts SET balance_minor = 12345 WHERE id = :id"), {"id": scenario.card_a}
    )
    await db_session.execute(
        text(
            "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id) "
            "SELECT gen_random_uuid(), user_id, 'account.balance_updated', 'account', id::text "
            "FROM accounts WHERE id = :id"
        ),
        {"id": scenario.card_a},
    )
    await db_session.commit()
    await db_session.close()

    _alembic_refuses(*REVERT, "downgrade", PREVIOUS_REVISION, reason="set by hand")
    assert await _version(db_session) == REVISION

    _alembic(*REVERT, *_skip(scenario.card_a), "downgrade", PREVIOUS_REVISION)

    assert await balance(db_session, scenario.card_a) == 12_345
    assert await _balances(db_session, scenario) == {**SCENARIO_STORED, "card_a": 12_345}
    [skipped] = await _audit_rows(db_session, "account.balance_correction_revert_skipped")
    assert skipped["entity_id"] == str(scenario.card_a)


async def test_downgrade_with_nothing_corrected_needs_no_flag(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    _alembic("upgrade", REVISION)

    _alembic("downgrade", PREVIOUS_REVISION)

    assert await _version(db_session) == PREVIOUS_REVISION


async def test_reapplying_after_a_downgrade_never_reverts_twice(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    scenario = await seed_scenario(db_session)
    # As in a real deploy, every leg predates the correction run, so the
    # re-upgrade's "activity since the previous run" guard stays quiet.
    await backdate_ledger(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)
    _alembic(*APPLY, "upgrade", REVISION)
    assert await _balances(db_session, scenario) == SCENARIO_CORRECTED

    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    assert await _balances(db_session, scenario) == SCENARIO_STORED


async def test_re_upgrade_refuses_a_card_the_fixed_backend_booked_since_the_correction(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """H1: after a downgrade, D is no longer the old code's error for a card the
    fixed backend has touched. Folding that leg into D would move the balance by
    twice its amount, so the card must block the re-upgrade until it is skipped."""
    scenario = await seed_scenario(db_session)
    await backdate_ledger(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    assert await balance(db_session, scenario.card_a) == 34_000

    owner = await _owner(db_session, scenario.card_a)
    await book_fixed_code(db_session, owner, scenario.card_a, "expense", 7_000)
    await db_session.commit()
    await db_session.close()
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)
    assert await balance(db_session, scenario.card_a) == 73_000
    await db_session.close()

    _alembic_refuses(
        *APPLY, "upgrade", REVISION, reason="ledger_activity_since_previous_correction"
    )

    assert await _version(db_session) == PREVIOUS_REVISION
    # Unguarded, D would be 16,000 - 7,000 = 9,000 and the balance would land on
    # 73,000 - 18,000 = 55,000 instead of the correct 34,000 + 7,000.
    assert await balance(db_session, scenario.card_a) == 73_000
    await db_session.close()

    _alembic(*APPLY, *_skip(scenario.card_a), "upgrade", REVISION)

    assert await balance(db_session, scenario.card_a) == 73_000
    assert await balance(db_session, scenario.card_b) == SCENARIO_CORRECTED["card_b"]
    assert await balance(db_session, scenario.usd_card) == SCENARIO_CORRECTED["usd_card"]
    [skipped] = await _audit_rows(db_session, "account.balance_correction_skipped")
    assert skipped["entity_id"] == str(scenario.card_a)
    assert skipped["metadata_json"]["blockers"] == ["ledger_activity_since_previous_correction"]
    assert skipped["metadata_json"]["unapplied_correction_minor"] == -18_000


async def test_re_upgrade_refuses_a_card_first_used_after_a_no_op_correction(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """H1, the shape production is actually in: the revision runs with nothing to
    correct, so the fixed backend goes live; cards created afterwards are booked
    correctly. A later downgrade and re-upgrade must not "correct" them."""
    _alembic("upgrade", REVISION)
    [summary] = await _audit_rows(db_session, "ledger.card_balance_correction")
    assert summary["metadata_json"]["mode"] == "none"

    user = await insert_user(db_session)
    card = await insert_account(
        db_session, user, account_type="credit_card", balance_minor=0, credit_limit_minor=50_000
    )
    await book_fixed_code(db_session, user, card, "expense", 5_000)
    await db_session.commit()
    assert await balance(db_session, card) == 5_000
    await db_session.close()
    _alembic("downgrade", PREVIOUS_REVISION)

    _alembic_refuses(
        *APPLY, "upgrade", REVISION, reason="ledger_activity_since_previous_correction"
    )

    assert await _version(db_session) == PREVIOUS_REVISION
    # Unguarded, D would be -5,000 and the card would be "corrected" to 15,000.
    assert await balance(db_session, card) == 5_000
    await db_session.close()

    _alembic(*APPLY, *_skip(card), "upgrade", REVISION)

    assert await balance(db_session, card) == 5_000
    [skipped] = await _audit_rows(db_session, "account.balance_correction_skipped")
    assert skipped["metadata_json"]["blockers"] == ["ledger_activity_since_previous_correction"]
    assert skipped["metadata_json"]["unapplied_correction_minor"] == 10_000


async def test_the_run_record_survives_a_downgrade_and_notes_both_directions(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """The durable record exists so the re-upgrade guard does not depend on
    audit_logs. A downgrade records the revert in it and never drops it."""
    await seed_scenario(db_session)
    await backdate_ledger(db_session)
    await db_session.close()

    _alembic(*APPLY, "upgrade", REVISION)
    assert await _run_rows(db_session) == [("upgrade", "apply")]
    await db_session.close()

    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await _run_rows(db_session) == [("upgrade", "apply"), ("downgrade", "revert")]


async def test_re_upgrade_still_refuses_after_the_audit_rows_are_purged(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """H1's residual risk: the guard must not depend on audit_logs alone. Purge
    every audit row between the downgrade and the re-upgrade -- the only thing
    left saying the fixed backend ever went live is data_correction_runs -- and
    the card the fixed code touched must still be refused."""
    scenario = await seed_scenario(db_session)
    await backdate_ledger(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    owner = await _owner(db_session, scenario.card_a)
    await book_fixed_code(db_session, owner, scenario.card_a, "expense", 7_000)
    await db_session.commit()
    await db_session.close()
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    await _purge_audit_logs(db_session)
    assert await _audit_row_count(db_session) == 0
    assert await _run_rows(db_session) == [("upgrade", "apply"), ("downgrade", "revert")]
    assert await balance(db_session, scenario.card_a) == 73_000
    await db_session.close()

    _alembic_refuses(
        *APPLY, "upgrade", REVISION, reason="ledger_activity_since_previous_correction"
    )

    assert await _version(db_session) == PREVIOUS_REVISION
    # Without the durable record this would have "corrected" 73,000 to 55,000.
    assert await balance(db_session, scenario.card_a) == 73_000
    await db_session.close()

    _alembic(*APPLY, *_skip(scenario.card_a), "upgrade", REVISION)

    assert await balance(db_session, scenario.card_a) == 73_000
    assert await balance(db_session, scenario.card_b) == SCENARIO_CORRECTED["card_b"]
    [skipped] = await _audit_rows(db_session, "account.balance_correction_skipped")
    assert skipped["metadata_json"]["blockers"] == ["ledger_activity_since_previous_correction"]


async def test_re_upgrade_still_refuses_after_the_run_rows_are_deleted(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """The mirror image: lose the durable record instead, and the audit summary
    row still dates the first run. Either source alone is enough."""
    scenario = await seed_scenario(db_session)
    await backdate_ledger(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    owner = await _owner(db_session, scenario.card_a)
    await book_fixed_code(db_session, owner, scenario.card_a, "expense", 7_000)
    await db_session.commit()
    await db_session.close()
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    await db_session.execute(text(f"DELETE FROM {RUN_TABLE}"))
    await db_session.commit()
    assert await _run_rows(db_session) == []
    await db_session.close()

    _alembic_refuses(
        *APPLY, "upgrade", REVISION, reason="ledger_activity_since_previous_correction"
    )

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await balance(db_session, scenario.card_a) == 73_000


async def test_downgrade_recreates_the_run_record_table_if_it_is_missing(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """A database upgraded by an earlier build of this revision has no run
    table. Both directions must create it rather than fail on it."""
    await seed_scenario(db_session)
    await backdate_ledger(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    await db_session.execute(text(f"DROP TABLE {RUN_TABLE}"))
    await db_session.commit()
    assert await db_session.scalar(text(f"SELECT to_regclass('{RUN_TABLE}')")) is None
    await db_session.commit()
    await db_session.close()

    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    assert await _version(db_session) == PREVIOUS_REVISION
    assert await _run_rows(db_session) == [("downgrade", "revert")]


async def test_guard_is_blind_only_if_every_record_of_the_run_is_destroyed(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    """The irreducible limit, pinned deliberately: with both the audit rows and
    the run rows gone there is nothing left that says the fixed backend ever
    ran, so the re-upgrade double-counts the fixed-code leg (73,000 -> 55,000
    instead of 41,000). Documented in docs/DEPLOYMENT.md; if a future change
    closes this, update this test rather than deleting the guarantee."""
    scenario = await seed_scenario(db_session)
    await backdate_ledger(db_session)
    await db_session.close()
    _alembic(*APPLY, "upgrade", REVISION)
    owner = await _owner(db_session, scenario.card_a)
    await book_fixed_code(db_session, owner, scenario.card_a, "expense", 7_000)
    await db_session.commit()
    await db_session.close()
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    await _purge_audit_logs(db_session)
    await db_session.execute(text(f"DELETE FROM {RUN_TABLE}"))
    await db_session.commit()
    await db_session.close()

    _alembic(*APPLY, "upgrade", REVISION)

    assert await balance(db_session, scenario.card_a) == 55_000


def test_the_run_record_table_matches_its_model() -> None:
    """The migration creates the run table with raw `CREATE TABLE IF NOT
    EXISTS` (it must be idempotent, since the downgrade deliberately keeps the
    table), so app/models/data_correction_run.py is the only thing stopping a
    future autogenerated migration from proposing to drop it. `alembic check`
    is what notices if the two drift apart."""
    result = _run_alembic("check")
    assert result.returncode == 0, "schema drift between the model and the migration DDL"
