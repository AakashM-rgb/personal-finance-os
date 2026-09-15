"""Subscription business logic: ownership enforcement (via the underlying
RecurringTransaction), deterministic cost calculations, and the
unused-subscription evidence check. Every subscription IS a recurring
transaction - creation, editing, deactivation, and the enriched
account/category/next-renewal fields all delegate to
app.services.recurring_transaction_service, never a second, divergent
implementation of scheduling or generation.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.subscription import Subscription
from app.models.transaction import TransactionType
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.recurring_transaction import (
    RecurringTransactionCreate,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)
from app.schemas.subscription import SubscriptionCreate, SubscriptionRead, SubscriptionUpdate
from app.services import recurring_transaction_service
from app.services.subscription_calculations import (
    LOOKBACK_DAYS,
    MIN_SUBSCRIPTION_AGE_DAYS,
    UnusedEvidence,
    calculate_monthly_cost_minor,
    calculate_yearly_cost_minor,
    evaluate_unused_evidence,
)


async def _evaluate_unused(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    category_id: uuid.UUID | None,
    recurring_transaction_id: uuid.UUID,
) -> UnusedEvidence:
    if category_id is None:
        return UnusedEvidence(
            None,
            "No category is set for this subscription, so there's no comparable "
            "spending activity to check against.",
        )

    txn_repo = TransactionRepository(db)
    own_dates = await txn_repo.list_occurrence_dates_for_recurring(recurring_transaction_id)
    today = datetime.now(UTC).date()

    if not own_dates or (today - min(own_dates)).days < MIN_SUBSCRIPTION_AGE_DAYS:
        # Not enough of the subscription's own billing history yet - skip
        # the second query entirely, evaluate_unused_evidence will already
        # return "insufficient data" from own_dates alone.
        return evaluate_unused_evidence(
            own_billing_dates=own_dates, other_category_activity_dates=[], today=today
        )

    lookback_start = datetime.combine(
        today - timedelta(days=LOOKBACK_DAYS), time.min, tzinfo=UTC
    )
    other_dates = await txn_repo.list_category_activity_dates(
        user_id,
        category_id=category_id,
        exclude_recurring_transaction_id=recurring_transaction_id,
        date_from=lookback_start,
    )
    return evaluate_unused_evidence(
        own_billing_dates=own_dates, other_category_activity_dates=other_dates, today=today
    )


async def _to_read(
    db: AsyncSession,
    subscription: Subscription,
    recurring_read: RecurringTransactionRead,
    *,
    user_id: uuid.UUID,
) -> SubscriptionRead:
    unused_evidence = await _evaluate_unused(
        db,
        user_id=user_id,
        category_id=recurring_read.category_id,
        recurring_transaction_id=recurring_read.id,
    )

    return SubscriptionRead(
        id=subscription.id,
        recurring_transaction_id=recurring_read.id,
        name=recurring_read.name,
        account_id=recurring_read.account_id,
        account_name=recurring_read.account_name,
        category_id=recurring_read.category_id,
        category_name=recurring_read.category_name,
        category_icon=recurring_read.category_icon,
        category_color=recurring_read.category_color,
        amount_minor=recurring_read.amount_minor,
        currency=recurring_read.currency,
        frequency=recurring_read.frequency,
        monthly_cost_minor=calculate_monthly_cost_minor(
            recurring_read.amount_minor, recurring_read.frequency
        ),
        yearly_cost_minor=calculate_yearly_cost_minor(
            recurring_read.amount_minor, recurring_read.frequency
        ),
        next_renewal_date=recurring_read.next_occurrence_date,
        is_active=recurring_read.is_active,
        is_possibly_unused=unused_evidence.is_possibly_unused,
        unused_reason=unused_evidence.reason,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


async def list_subscriptions(db: AsyncSession, *, user_id: uuid.UUID) -> list[SubscriptionRead]:
    rows = await SubscriptionRepository(db).list_for_user(user_id)
    reads = []
    for subscription, recurring in rows:
        # One get_recurring_transaction call per row (its own account/
        # category lookups included) rather than a hand-rolled bulk
        # enrichment - cheap at personal-finance subscription counts, and
        # it guarantees this list can never compute account/category/
        # next-renewal fields differently than the single-item GET does.
        recurring_read = await recurring_transaction_service.get_recurring_transaction(
            db, user_id=user_id, recurring_id=recurring.id
        )
        reads.append(await _to_read(db, subscription, recurring_read, user_id=user_id))
    return reads


async def get_subscription(
    db: AsyncSession, *, user_id: uuid.UUID, subscription_id: uuid.UUID
) -> SubscriptionRead:
    found = await SubscriptionRepository(db).get_by_id_for_user(subscription_id, user_id)
    if found is None:
        raise NotFoundError("Subscription not found.")
    subscription, recurring = found

    recurring_read = await recurring_transaction_service.get_recurring_transaction(
        db, user_id=user_id, recurring_id=recurring.id
    )
    return await _to_read(db, subscription, recurring_read, user_id=user_id)


async def create_subscription(
    db: AsyncSession, *, user_id: uuid.UUID, data: SubscriptionCreate
) -> SubscriptionRead:
    recurring_read = await recurring_transaction_service.create_recurring_transaction(
        db,
        user_id=user_id,
        data=RecurringTransactionCreate(
            name=data.name,
            account_id=data.account_id,
            category_id=data.category_id,
            type=TransactionType.EXPENSE,
            amount_minor=data.amount_minor,
            frequency=data.frequency,
            start_date=data.start_date,
        ),
    )

    repo = SubscriptionRepository(db)
    subscription = Subscription(recurring_transaction_id=recurring_read.id)
    repo.add(subscription)
    await repo.flush()

    return await get_subscription(db, user_id=user_id, subscription_id=subscription.id)


async def update_subscription(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
    data: SubscriptionUpdate,
) -> SubscriptionRead:
    found = await SubscriptionRepository(db).get_by_id_for_user(subscription_id, user_id)
    if found is None:
        raise NotFoundError("Subscription not found.")
    _subscription, recurring = found

    await recurring_transaction_service.update_recurring_transaction(
        db,
        user_id=user_id,
        recurring_id=recurring.id,
        data=RecurringTransactionUpdate(
            name=data.name,
            account_id=data.account_id,
            category_id=data.category_id,
            clear_category=data.clear_category,
            amount_minor=data.amount_minor,
            frequency=data.frequency,
        ),
    )
    return await get_subscription(db, user_id=user_id, subscription_id=subscription_id)


async def deactivate_subscription(
    db: AsyncSession, *, user_id: uuid.UUID, subscription_id: uuid.UUID
) -> None:
    found = await SubscriptionRepository(db).get_by_id_for_user(subscription_id, user_id)
    if found is None:
        raise NotFoundError("Subscription not found.")
    _subscription, recurring = found

    await recurring_transaction_service.deactivate_recurring_transaction(
        db, user_id=user_id, recurring_id=recurring.id
    )
