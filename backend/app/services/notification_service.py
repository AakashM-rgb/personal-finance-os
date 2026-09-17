"""Notification business logic: generation (one detector per category,
each reusing the exact same service-layer functions the corresponding
feature's own page calls - never a second, divergent calculation) and the
plain CRUD operations (list/count/mark-read) the API exposes.

Every detector is idempotent by construction: each notification it creates
carries a `dedupe_key` that deterministically encodes the real-world event
it's about (see app.models.notification's docstring), and
NotificationRepository.create_if_not_exists silently no-ops if a row with
that (user_id, dedupe_key) already exists - backed by a real database
unique constraint, not just application discipline, so concurrent
generation runs can never create a duplicate (see
app.services.recurring_transaction_service for the identical pattern this
mirrors, including its own concurrency lesson: every value a detector
needs is read out of a service-layer Pydantic response, never a live ORM
object, specifically because a Pydantic model can never be invalidated by
another detector's rollback later in the same request)."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.account import AccountType
from app.models.notification import NotificationCategory
from app.models.transaction import TransactionType
from app.repositories.account_repository import AccountRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.notification import NotificationRead
from app.schemas.user_settings import NotificationPreferences
from app.services import (
    budget_service,
    recurring_transaction_service,
    savings_goal_service,
    subscription_service,
)
from app.services.export_formatting import format_money
from app.services.notification_calculations import (
    is_unusual_expense,
    is_within_reminder_window,
    milestone_amount_minor,
    milestones_reached,
)

_UNUSUAL_SPENDING_LOOKBACK_DAYS = 90


async def _get_preferences(db: AsyncSession, user_id: uuid.UUID) -> NotificationPreferences:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    raw = settings.notification_preferences if settings is not None else {}
    return NotificationPreferences.model_validate(raw or {})


async def _get_base_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


async def _generate_budget_notifications(
    db: AsyncSession, *, user_id: uuid.UUID, period: str
) -> None:
    repo = NotificationRepository(db)
    items = await budget_service.list_budget_items(db, user_id=user_id)
    for item in items:
        amount = format_money(item.spent_minor, item.currency)
        limit = format_money(item.amount_minor, item.currency)
        if item.status == "exceeded":
            await repo.create_if_not_exists(
                user_id=user_id,
                category=NotificationCategory.BUDGET_EXCEEDED,
                title=f"{item.category_name} budget exceeded",
                message=(
                    f"You've spent {amount} of your {limit} {item.category_name} "
                    f"budget this month ({item.percent_used:.0f}% used)."
                ),
                dedupe_key=f"budget_exceeded:{item.id}:{period}",
                reference_type="budget_item",
                reference_id=str(item.id),
                action_url="/budgets",
            )
        elif item.status in ("warning", "near_limit"):
            await repo.create_if_not_exists(
                user_id=user_id,
                category=NotificationCategory.BUDGET_WARNING,
                title=f"{item.category_name} budget warning",
                message=(
                    f"You've used {amount} of your {limit} {item.category_name} "
                    f"budget this month ({item.percent_used:.0f}% used)."
                ),
                dedupe_key=f"budget_warning:{item.id}:{period}",
                reference_type="budget_item",
                reference_id=str(item.id),
                action_url="/budgets",
            )


async def _generate_payment_reminder_notifications(
    db: AsyncSession, *, user_id: uuid.UUID, today: date
) -> None:
    repo = NotificationRepository(db)

    subscriptions = await subscription_service.list_subscriptions(db, user_id=user_id)
    for sub in subscriptions:
        if not sub.is_active:
            continue
        days_until = (sub.next_renewal_date - today).days
        if not is_within_reminder_window(days_until):
            continue
        amount = format_money(sub.amount_minor, sub.currency)
        await repo.create_if_not_exists(
            user_id=user_id,
            category=NotificationCategory.SUBSCRIPTION_REMINDER,
            title=f"{sub.name} renews soon",
            message=f"{sub.name} ({amount}) renews on {sub.next_renewal_date.isoformat()}.",
            dedupe_key=f"subscription_reminder:{sub.id}:{sub.next_renewal_date.isoformat()}",
            reference_type="subscription",
            reference_id=str(sub.id),
            action_url="/subscriptions",
        )

    accounts = await AccountRepository(db).list_for_user(user_id, include_inactive=False)
    # Every value the loop below needs is copied out of the ORM rows into
    # plain tuples up front, before any create_if_not_exists call runs
    # (which may roll back this session on a duplicate-key race) - touching
    # an ORM attribute (account.name, account.credit_card.payment_due_day)
    # after that rollback would try an implicit, unsupported lazy-reload
    # (see app.services.recurring_transaction_service's own docstring for
    # the concurrency bug this exact pattern once caused, and
    # _generate_unusual_spending_notifications below for the identical
    # extract-before-any-write precedent already used in this module).
    credit_cards = [
        (str(account.id), account.name, account.credit_card.payment_due_day)
        for account in accounts
        if account.type == AccountType.CREDIT_CARD and account.credit_card is not None
    ]

    for account_id, account_name, payment_due_day in credit_cards:
        due_date = _next_occurrence_of_day(today, payment_due_day)
        days_until = (due_date - today).days
        if not is_within_reminder_window(days_until):
            continue
        await repo.create_if_not_exists(
            user_id=user_id,
            category=NotificationCategory.CREDIT_CARD_REMINDER,
            title=f"{account_name} payment due soon",
            message=f"Your {account_name} payment is due on {due_date.isoformat()}.",
            dedupe_key=f"credit_card_reminder:{account_id}:{due_date.isoformat()}",
            reference_type="account",
            reference_id=account_id,
            action_url="/accounts",
        )


def _next_occurrence_of_day(today: date, day_of_month: int) -> date:
    """The next calendar date (today or later) whose day-of-month is
    `day_of_month`, clamped to the last real day of a shorter month -
    e.g. day_of_month=31 in April resolves to April 30. Mirrors
    app.services.recurrence's own month-end clamping convention for the
    same reason: a fixed billing day must still resolve to a real date
    every month."""
    import calendar

    def _clamped(year: int, month: int) -> date:
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(day_of_month, last_day))

    candidate = _clamped(today.year, today.month)
    if candidate >= today:
        return candidate
    if today.month == 12:
        return _clamped(today.year + 1, 1)
    return _clamped(today.year, today.month + 1)


async def _generate_goal_milestone_notifications(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    repo = NotificationRepository(db)
    goals = await savings_goal_service.list_savings_goals(db, user_id=user_id)
    for goal in goals:
        for milestone in milestones_reached(goal.progress_percent):
            title = (
                f"{goal.name} goal reached!"
                if milestone == 100
                else f"{goal.name} is {milestone}% funded"
            )
            amount_at_milestone = milestone_amount_minor(goal.target_amount_minor, milestone)
            message = (
                f"You've saved {format_money(amount_at_milestone, goal.currency)} of your "
                f"{format_money(goal.target_amount_minor, goal.currency)} target for {goal.name}."
            )
            await repo.create_if_not_exists(
                user_id=user_id,
                category=NotificationCategory.GOAL_MILESTONE,
                title=title,
                message=message,
                dedupe_key=f"goal_milestone:{goal.id}:{milestone}",
                reference_type="savings_goal",
                reference_id=str(goal.id),
                action_url="/goals",
            )


async def _generate_recurring_reminder_notifications(
    db: AsyncSession, *, user_id: uuid.UUID, today: date
) -> None:
    repo = NotificationRepository(db)
    # Subscriptions are a 1:1 extension of recurring_transactions (CLAUDE.md
    # §4), so list_recurring_transactions also returns every subscription's
    # own backing schedule - excluded here since it already gets its own,
    # more specific SUBSCRIPTION_REMINDER notification; without this a
    # single subscription would otherwise generate two redundant reminders
    # for the same real-world renewal date.
    subscriptions = await subscription_service.list_subscriptions(db, user_id=user_id)
    subscription_recurring_ids = {sub.recurring_transaction_id for sub in subscriptions}

    recurring = await recurring_transaction_service.list_recurring_transactions(db, user_id=user_id)
    for item in recurring:
        if not item.is_active or item.type != TransactionType.EXPENSE:
            continue
        if item.id in subscription_recurring_ids:
            continue
        days_until = (item.next_occurrence_date - today).days
        if not is_within_reminder_window(days_until):
            continue
        amount = format_money(item.amount_minor, item.currency)
        await repo.create_if_not_exists(
            user_id=user_id,
            category=NotificationCategory.RECURRING_REMINDER,
            title=f"{item.name} due soon",
            message=f"{item.name} ({amount}) is due on {item.next_occurrence_date.isoformat()}.",
            dedupe_key=f"recurring_reminder:{item.id}:{item.next_occurrence_date.isoformat()}",
            reference_type="recurring_transaction",
            reference_id=str(item.id),
            action_url="/recurring-transactions",
        )


async def _generate_unusual_spending_notifications(
    db: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> None:
    repo = NotificationRepository(db)
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    window_start = now - timedelta(days=_UNUSUAL_SPENDING_LOOKBACK_DAYS)
    transactions = await txn_repo.list_in_range(
        user_id, date_from=window_start, date_to=now, currency=currency
    )
    # Every value needed below is copied out of the ORM rows into plain
    # tuples up front, before any create_if_not_exists call runs (which may
    # roll back this session on a duplicate-key race) - touching an ORM
    # attribute after that rollback would try an implicit, unsupported
    # lazy-reload (see app.services.recurring_transaction_service's own
    # docstring for the concurrency bug this exact pattern once caused).
    expenses = sorted(
        (
            (str(t.id), t.category_id, t.amount_minor, t.occurred_at)
            for t in transactions
            if t.type == TransactionType.EXPENSE and t.category_id is not None
        ),
        key=lambda row: row[3],
    )

    visible_categories = await CategoryRepository(db).list_visible_for_user(
        user_id, include_inactive=True
    )
    categories_by_id = {c.id: c for c in visible_categories}

    for index, (txn_id, category_id, amount_minor, _occurred_at) in enumerate(expenses):
        history = [
            amt
            for i, (_, cat_id, amt, _occ) in enumerate(expenses)
            if i < index and cat_id == category_id
        ]
        if not is_unusual_expense(amount_minor=amount_minor, historical_amounts_minor=history):
            continue
        category = categories_by_id.get(category_id)
        category_name = category.name if category is not None else "this category"
        await repo.create_if_not_exists(
            user_id=user_id,
            category=NotificationCategory.UNUSUAL_SPENDING,
            title="Unusual spending detected",
            message=(
                f"A {format_money(amount_minor, currency)} {category_name} expense is "
                f"significantly higher than your recent average for that category."
            ),
            dedupe_key=f"unusual_spending:{txn_id}",
            reference_type="transaction",
            reference_id=txn_id,
            action_url="/transactions",
        )


async def generate_due_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    """The user-scoped entry point - called inline by the list/unread-count
    endpoints (see app.api.v1.notifications) so notification data is always
    fresh without the frontend needing to remember a separate "refresh"
    call, and also callable from app.jobs.notification_generator for a
    real scheduler. Every detector independently no-ops when its category
    is disabled in the user's own notification_preferences (checked here,
    a second time, even though nothing upstream currently disables the
    call itself - the same defense-in-depth CLAUDE.md §14 requires for the
    AI's own per-user setting)."""
    preferences = await _get_preferences(db, user_id)
    now = datetime.now(UTC)
    today = now.date()
    period = f"{today.year:04d}-{today.month:02d}"

    if preferences.budget_warnings:
        await _generate_budget_notifications(db, user_id=user_id, period=period)
    if preferences.payment_reminders:
        await _generate_payment_reminder_notifications(db, user_id=user_id, today=today)
    if preferences.goal_milestones:
        await _generate_goal_milestone_notifications(db, user_id=user_id)
    if preferences.recurring_reminders:
        await _generate_recurring_reminder_notifications(db, user_id=user_id, today=today)
    if preferences.unusual_spending:
        await _generate_unusual_spending_notifications(db, user_id=user_id, now=now)


async def generate_due_for_all_users(db: AsyncSession) -> None:
    """The system-wide sweep a real scheduler would call on a fixed
    interval instead - mirrors
    app.services.recurring_transaction_service.generate_due_for_all_users
    exactly, including not being wired to any user-facing endpoint."""
    user_ids = await UserRepository(db).list_all_ids()
    for user_id in user_ids:
        await generate_due_for_user(db, user_id=user_id)


async def list_notifications(
    db: AsyncSession, *, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
) -> tuple[list[NotificationRead], int]:
    notifications, total = await NotificationRepository(db).list_for_user(
        user_id, unread_only=unread_only, limit=limit, offset=offset
    )
    return [NotificationRead.model_validate(n) for n in notifications], total


async def get_unread_count(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    return await NotificationRepository(db).count_unread_for_user(user_id)


async def mark_notification_read(
    db: AsyncSession, *, user_id: uuid.UUID, notification_id: uuid.UUID
) -> NotificationRead:
    repo = NotificationRepository(db)
    notification = await repo.get_by_id_for_user(notification_id, user_id)
    if notification is None:
        raise NotFoundError("Notification not found.")
    await repo.mark_read(notification)
    return NotificationRead.model_validate(notification)


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    return await NotificationRepository(db).mark_all_read_for_user(user_id)
