"""Recurring transaction business logic: ownership enforcement, the
deterministic date math that drives generation, and idempotent creation
of the real Transaction rows a due occurrence materializes into.

Generation never trusts a stored "next occurrence" pointer. Instead, for
each recurring transaction, it asks the ledger itself (via
TransactionRepository.get_latest_occurrence_date_for_recurring) what the
most recently generated occurrence date was, and computes the next one
from that - so calling generation twice in a row is naturally a no-op
the second time (there is nothing new to catch up on), and the schedule
can never drift out of sync with what has actually been recorded. Every
generated Transaction goes through transaction_service.create_transaction
- the exact same path a manually-created transaction takes - so it gets
the same account/category validation and balance-effect application;
there is no second, divergent way a recurring occurrence's amount ends up
on the ledger.
"""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.account import Account
from app.models.category import Category
from app.models.recurring_transaction import RecurringTransaction
from app.repositories.account_repository import AccountRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.recurring_transaction import (
    RecurringTransactionCreate,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)
from app.schemas.transaction import TransactionCreate, TransactionRead
from app.services import account_service, transaction_service
from app.services.recurrence import next_occurrence_date


async def _accounts_by_id(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, Account]:
    accounts = await AccountRepository(db).list_for_user(user_id, include_inactive=True)
    return {a.id: a for a in accounts}


async def _categories_by_id(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, Category]:
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    return {c.id: c for c in categories}


async def _validate_category(
    db: AsyncSession, *, user_id: uuid.UUID, category_id: uuid.UUID
) -> None:
    category = await CategoryRepository(db).get_visible_by_id(category_id, user_id)
    if category is None:
        raise ValidationAppError("Category not found.", field_errors={"category_id": "not found"})


async def _compute_next_occurrence(db: AsyncSession, recurring: RecurringTransaction) -> date:
    """The date the next occurrence will be generated for - the date
    immediately after the most recently generated one, or start_date if
    none has ever been generated yet. This can be in the past (generation
    is simply overdue), today, or in the future - all three are valid,
    real states, never guessed."""
    latest = await TransactionRepository(db).get_latest_occurrence_date_for_recurring(recurring.id)
    if latest is None:
        return recurring.start_date
    return next_occurrence_date(latest, recurring.frequency, day_of_month=recurring.day_of_month)


def _to_read(
    recurring: RecurringTransaction,
    account: Account,
    category: Category | None,
    next_occurrence: date,
) -> RecurringTransactionRead:
    return RecurringTransactionRead(
        id=recurring.id,
        name=recurring.name,
        account_id=recurring.account_id,
        account_name=account.name,
        category_id=recurring.category_id,
        category_name=category.name if category is not None else None,
        category_icon=category.icon if category is not None else None,
        category_color=category.color if category is not None else None,
        type=recurring.type,
        amount_minor=recurring.amount_minor,
        currency=recurring.currency,
        frequency=recurring.frequency,
        start_date=recurring.start_date,
        next_occurrence_date=next_occurrence,
        is_active=recurring.is_active,
        created_at=recurring.created_at,
        updated_at=recurring.updated_at,
    )


async def list_recurring_transactions(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[RecurringTransactionRead]:
    recurring_list = await RecurringTransactionRepository(db).list_for_user(user_id)
    if not recurring_list:
        return []

    accounts_by_id = await _accounts_by_id(db, user_id)
    categories_by_id = await _categories_by_id(db, user_id)

    reads = []
    for recurring in recurring_list:
        next_occurrence = await _compute_next_occurrence(db, recurring)
        reads.append(
            _to_read(
                recurring,
                accounts_by_id[recurring.account_id],
                categories_by_id.get(recurring.category_id) if recurring.category_id else None,
                next_occurrence,
            )
        )
    return reads


async def get_recurring_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, recurring_id: uuid.UUID
) -> RecurringTransactionRead:
    recurring = await RecurringTransactionRepository(db).get_by_id_for_user(recurring_id, user_id)
    if recurring is None:
        raise NotFoundError("Recurring transaction not found.")

    account = await AccountRepository(db).get_by_id_for_user(recurring.account_id, user_id)
    assert account is not None  # the FK guarantees this row exists
    category = (
        await CategoryRepository(db).get_visible_by_id(recurring.category_id, user_id)
        if recurring.category_id is not None
        else None
    )
    next_occurrence = await _compute_next_occurrence(db, recurring)
    return _to_read(recurring, account, category, next_occurrence)


async def create_recurring_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, data: RecurringTransactionCreate
) -> RecurringTransactionRead:
    account = await account_service.resolve_active_account(
        db, user_id=user_id, account_id=data.account_id
    )
    if data.category_id is not None:
        await _validate_category(db, user_id=user_id, category_id=data.category_id)

    repo = RecurringTransactionRepository(db)
    recurring = RecurringTransaction(
        user_id=user_id,
        account_id=data.account_id,
        category_id=data.category_id,
        name=data.name,
        type=data.type,
        amount_minor=data.amount_minor,
        currency=account.currency,
        frequency=data.frequency,
        start_date=data.start_date,
        day_of_month=data.start_date.day,
        is_active=True,
    )
    repo.add(recurring)
    await repo.flush()

    return await get_recurring_transaction(db, user_id=user_id, recurring_id=recurring.id)


async def update_recurring_transaction(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    recurring_id: uuid.UUID,
    data: RecurringTransactionUpdate,
) -> RecurringTransactionRead:
    repo = RecurringTransactionRepository(db)
    recurring = await repo.get_by_id_for_user(recurring_id, user_id)
    if recurring is None:
        raise NotFoundError("Recurring transaction not found.")

    if data.account_id is not None:
        account = await account_service.resolve_active_account(
            db, user_id=user_id, account_id=data.account_id
        )
        recurring.account_id = data.account_id
        recurring.currency = account.currency

    if data.category_id is not None:
        await _validate_category(db, user_id=user_id, category_id=data.category_id)
        recurring.category_id = data.category_id
    elif data.clear_category:
        recurring.category_id = None

    if data.name is not None:
        recurring.name = data.name
    if data.type is not None:
        recurring.type = data.type
    if data.amount_minor is not None:
        recurring.amount_minor = data.amount_minor
    if data.frequency is not None:
        recurring.frequency = data.frequency

    await repo.flush()
    return await get_recurring_transaction(db, user_id=user_id, recurring_id=recurring_id)


async def deactivate_recurring_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, recurring_id: uuid.UUID
) -> None:
    repo = RecurringTransactionRepository(db)
    recurring = await repo.get_by_id_for_user(recurring_id, user_id)
    if recurring is None:
        raise NotFoundError("Recurring transaction not found.")
    recurring.is_active = False
    await repo.flush()


async def _generate_due_occurrences(
    db: AsyncSession, recurring: RecurringTransaction, *, today: date
) -> list[TransactionRead]:
    """Generates every occurrence up to and including `today` that hasn't
    been generated yet - one call catches up an arbitrarily long gap
    (including one that has never generated anything, e.g. a past
    start_date), and calling it again with nothing new due is a no-op:
    _compute_next_occurrence will already point past `today`."""
    generated: list[TransactionRead] = []
    current = await _compute_next_occurrence(db, recurring)

    while current <= today:
        transaction = await transaction_service.create_transaction(
            db,
            user_id=recurring.user_id,
            data=TransactionCreate(
                account_id=recurring.account_id,
                type=recurring.type,
                amount_minor=recurring.amount_minor,
                category_id=recurring.category_id,
                description=recurring.name,
                occurred_at=datetime.combine(current, time.min, tzinfo=UTC),
            ),
            idempotency_key=None,
            recurring_transaction_id=recurring.id,
        )
        generated.append(transaction)
        current = next_occurrence_date(
            current, recurring.frequency, day_of_month=recurring.day_of_month
        )

    return generated


async def generate_due_for_user(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[TransactionRead]:
    """The user-scoped entry point a manual "generate now" API call uses -
    never called directly by app.jobs, which goes through
    generate_due_for_all_users instead."""
    today = datetime.now(UTC).date()
    active = await RecurringTransactionRepository(db).list_active_for_user(user_id)

    generated: list[TransactionRead] = []
    for recurring in active:
        generated.extend(await _generate_due_occurrences(db, recurring, today=today))
    return generated


async def generate_due_for_all_users(db: AsyncSession) -> list[TransactionRead]:
    """The system-wide sweep app.jobs.recurring_transaction_generator calls
    - never exposed through any user-facing API."""
    today = datetime.now(UTC).date()
    active = await RecurringTransactionRepository(db).list_active_all()

    generated: list[TransactionRead] = []
    for recurring in active:
        generated.extend(await _generate_due_occurrences(db, recurring, today=today))
    return generated
