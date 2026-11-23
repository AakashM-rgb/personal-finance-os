"""A unique-constraint collision must undo only the statement that collided.

Both writes covered here recover from an IntegrityError and then keep using
the same session. They used to do that by rolling back the whole
transaction, which also threw away everything the caller had already written
-- silently, because the recovery looks identical either way. These tests pin
the SAVEPOINT behaviour that replaced it.
"""

import uuid
from collections.abc import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationCategory
from app.models.transaction import TransactionType
from app.repositories.notification_repository import NotificationRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import TransactionCreate
from app.services import transaction_service
from tests.f001_ledger_seed import insert_account, insert_user


async def _dedupe_keys(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await db.execute(
        text("SELECT dedupe_key FROM notifications WHERE user_id = :u"), {"u": user_id}
    )
    return {row.dedupe_key for row in rows}


async def test_a_duplicate_notification_keeps_the_rest_of_the_transaction(
    db_session: AsyncSession,
) -> None:
    """F-002. The detectors run five in a row on one session and re-attempt
    every notification they have already created, so a duplicate is the
    normal case. A whole-transaction rollback on the duplicate discarded the
    genuinely new notifications created before it in the same request."""
    user_id = await insert_user(db_session)
    await db_session.commit()
    repo = NotificationRepository(db_session)

    async def create(dedupe_key: str) -> object | None:
        return await repo.create_if_not_exists(
            user_id=user_id,
            category=NotificationCategory.BUDGET_WARNING,
            title="Title",
            message="Message",
            dedupe_key=dedupe_key,
        )

    assert await create("already-exists") is not None
    await db_session.commit()

    # One transaction: a new notification, then a duplicate, then another new
    # one -- the shape a second generation run produces.
    assert await create("new-before-the-duplicate") is not None
    assert await create("already-exists") is None, "a duplicate must be a no-op"
    assert await create("new-after-the-duplicate") is not None
    await db_session.commit()

    assert await _dedupe_keys(db_session, user_id) == {
        "already-exists",
        "new-before-the-duplicate",
        "new-after-the-duplicate",
    }


async def test_a_duplicate_notification_leaves_no_pending_insert_behind(
    db_session: AsyncSession,
) -> None:
    """Rolling back to the savepoint must also undo the `add`, or the outer
    commit would re-attempt the insert that just failed and raise."""
    user_id = await insert_user(db_session)
    await db_session.commit()
    repo = NotificationRepository(db_session)
    first = await repo.create_if_not_exists(
        user_id=user_id,
        category=NotificationCategory.GOAL_MILESTONE,
        title="Title",
        message="Message",
        dedupe_key="key",
    )
    assert first is not None
    await db_session.commit()

    assert (
        await repo.create_if_not_exists(
            user_id=user_id,
            category=NotificationCategory.GOAL_MILESTONE,
            title="Title",
            message="Message",
            dedupe_key="key",
        )
        is None
    )
    await db_session.commit()  # must not raise a second unique violation

    count = await db_session.scalar(
        text("SELECT count(*) FROM notifications WHERE user_id = :u"), {"u": user_id}
    )
    assert count == 1


async def test_generation_run_keeps_new_notifications_after_a_duplicate(
    client: AsyncClient, auth_headers: dict
) -> None:
    """F-002 end to end: generation runs inline on every list request, so the
    second call re-attempts the first call's notifications. Anything new that
    run produces has to survive them."""
    account = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Card",
            "type": "credit_card",
            "balance_minor": 5_000_00,
            "currency": "INR",
            "credit_card": {
                "credit_limit_minor": 100_000_00,
                "statement_day": 5,
                "payment_due_day": 20,
            },
        },
    )
    assert account.status_code == 201, account.text

    first = await client.get("/api/v1/notifications", headers=auth_headers)
    assert first.status_code == 200, first.text
    first_keys = {n["title"] for n in first.json()["data"]}

    second = await client.get("/api/v1/notifications", headers=auth_headers)
    assert second.status_code == 200, second.text
    second_keys = {n["title"] for n in second.json()["data"]}

    # Re-running must never lose what the previous run produced.
    assert first_keys <= second_keys


async def test_an_idempotency_key_race_keeps_the_callers_earlier_transaction(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-011. The recovery path is only reachable when another request commits
    the same idempotency key between our pre-check and our insert, so the
    pre-check is forced to miss once. Before the fix this rolled back the
    whole transaction, losing the transaction the caller had already created
    in it -- the shape
    recurring_transaction_service._generate_due_occurrences has when it
    materializes several occurrences at once."""
    user_id = await insert_user(db_session)
    account_id = await insert_account(
        db_session, user_id, account_type="bank_account", balance_minor=1_000_000
    )
    await db_session.commit()

    def _expense(amount_minor: int) -> TransactionCreate:
        return TransactionCreate(
            account_id=account_id, type=TransactionType.EXPENSE, amount_minor=amount_minor
        )

    # The row the "other request" already committed.
    await transaction_service.create_transaction(
        db_session, user_id=user_id, data=_expense(111), idempotency_key="shared-key"
    )
    await db_session.commit()

    # Work the caller does before the collision, in one transaction.
    earlier = await transaction_service.create_transaction(
        db_session, user_id=user_id, data=_expense(222), idempotency_key="earlier"
    )

    real_lookup = TransactionRepository.get_by_idempotency_key
    calls: list[int] = []

    async def _miss_once(
        self: TransactionRepository, user: uuid.UUID, key: str
    ) -> object | None:
        calls.append(1)
        if len(calls) == 1:
            return None  # the pre-check loses the race
        return await real_lookup(self, user, key)

    monkeypatch.setattr(TransactionRepository, "get_by_idempotency_key", _miss_once)

    replayed = await transaction_service.create_transaction(
        db_session, user_id=user_id, data=_expense(333), idempotency_key="shared-key"
    )

    assert len(calls) == 2, "the insert should have collided and re-looked-up"
    assert replayed.amount_minor == 111, "the replay returns the committed row, not a new one"

    monkeypatch.undo()
    await db_session.commit()

    amounts = [
        row.amount_minor
        for row in await db_session.execute(
            text("SELECT amount_minor FROM transactions WHERE user_id = :u ORDER BY amount_minor"),
            {"u": user_id},
        )
    ]
    assert amounts == [111, 222], "the earlier transaction must survive the collision"
    assert earlier.amount_minor == 222


@pytest.mark.parametrize("make_key", [lambda: "shared-key", lambda: str(uuid.uuid4())])
async def test_balances_stay_consistent_across_the_recovery(
    db_session: AsyncSession, make_key: Callable[[], str]
) -> None:
    """Whichever path create_transaction takes -- idempotent replay or a fresh
    insert -- the account balance must reflect exactly the transactions that
    actually exist."""
    user_id = await insert_user(db_session)
    account_id = await insert_account(
        db_session, user_id, account_type="bank_account", balance_minor=1_000
    )
    await db_session.commit()

    key = make_key()
    for _ in range(2):
        await transaction_service.create_transaction(
            db_session,
            user_id=user_id,
            data=TransactionCreate(
                account_id=account_id,
                type=TransactionType.EXPENSE,
                amount_minor=100,
            ),
            idempotency_key=key,
        )
    await db_session.commit()

    count = await db_session.scalar(
        text("SELECT count(*) FROM transactions WHERE user_id = :u"), {"u": user_id}
    )
    balance = await db_session.scalar(
        text("SELECT balance_minor FROM accounts WHERE id = :a"), {"a": account_id}
    )
    assert count == 1, "the same key must never book twice"
    assert balance == 900
