"""Budget business logic: ownership enforcement, real spending progress
from the transaction ledger, status derivation, and evidence-based
suggestions - every number here is computed from the authenticated
caller's own data (never another user's, never a caller-supplied user_id),
and nothing is randomly generated.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.budget import BudgetItem
from app.models.category import Category
from app.models.transaction import TransactionType
from app.repositories.budget_repository import BudgetItemRepository, BudgetRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.budget import BudgetItemCreate, BudgetItemRead, BudgetItemUpdate, BudgetSuggestion
from app.services import category_service
from app.services.budget_calculations import (
    build_warning_message,
    determine_budget_status,
    project_monthly_amount,
)
from app.services.month_bounds import (
    current_month_bounds,
    days_elapsed_in_month,
    days_in_month,
    month_start_n_months_ago,
)

_SUGGESTION_LOOKBACK_MONTHS = 3


async def _get_base_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


async def _categories_by_id(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, Category]:
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    return {c.id: c for c in categories}


def _to_read(
    item: BudgetItem,
    category: Category | None,
    spent_minor: int,
    days_elapsed: int,
    days_in_mo: int,
    currency: str,
) -> BudgetItemRead:
    percent_used = round(spent_minor / item.amount_minor * 100, 1) if item.amount_minor > 0 else 0.0
    status = determine_budget_status(percent_used)
    category_name = category_service.display_name(category)

    return BudgetItemRead(
        id=item.id,
        category_id=item.category_id,
        category_name=category_name,
        category_icon=category_service.display_icon(category),
        category_color=category_service.display_color(category),
        currency=currency,
        amount_minor=item.amount_minor,
        spent_minor=spent_minor,
        remaining_minor=item.amount_minor - spent_minor,
        percent_used=percent_used,
        status=status.value,
        warning_message=build_warning_message(category_name, percent_used, status),
        projected_month_minor=project_monthly_amount(
            spent_minor, days_elapsed=days_elapsed, days_in_month=days_in_mo
        ),
        days_elapsed=days_elapsed,
        days_in_month=days_in_mo,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def list_budget_items(db: AsyncSession, *, user_id: uuid.UUID) -> list[BudgetItemRead]:
    items = await BudgetItemRepository(db).list_for_user(user_id)
    if not items:
        return []

    now = datetime.now(UTC)
    _, this_month_start, next_month_start = current_month_bounds(now)
    elapsed = days_elapsed_in_month(now, this_month_start)
    in_month = days_in_month(now)
    base_currency = await _get_base_currency(db, user_id)

    this_month_transactions = await TransactionRepository(db).list_in_range(
        user_id, date_from=this_month_start, date_to=next_month_start, currency=base_currency
    )
    spent_by_category: dict[uuid.UUID, int] = defaultdict(int)
    for txn in this_month_transactions:
        if txn.type == TransactionType.EXPENSE and txn.category_id is not None:
            spent_by_category[txn.category_id] += txn.amount_minor

    categories_by_id = await _categories_by_id(db, user_id)

    return [
        _to_read(
            item,
            categories_by_id.get(item.category_id),
            spent_by_category.get(item.category_id, 0),
            elapsed,
            in_month,
            base_currency,
        )
        for item in items
    ]


async def get_budget_item(
    db: AsyncSession, *, user_id: uuid.UUID, item_id: uuid.UUID
) -> BudgetItemRead:
    item = await BudgetItemRepository(db).get_by_id_for_user(item_id, user_id)
    if item is None:
        raise NotFoundError("Budget not found.")

    now = datetime.now(UTC)
    _, this_month_start, next_month_start = current_month_bounds(now)
    elapsed = days_elapsed_in_month(now, this_month_start)
    in_month = days_in_month(now)
    base_currency = await _get_base_currency(db, user_id)

    spent_minor = await TransactionRepository(db).sum_expense_in_range(
        user_id,
        date_from=this_month_start,
        date_to=next_month_start,
        currency=base_currency,
        category_id=item.category_id,
    )
    category = await CategoryRepository(db).get_visible_by_id(item.category_id, user_id)
    return _to_read(item, category, spent_minor, elapsed, in_month, base_currency)


async def create_budget_item(
    db: AsyncSession, *, user_id: uuid.UUID, data: BudgetItemCreate
) -> BudgetItemRead:
    category = await CategoryRepository(db).get_visible_by_id(data.category_id, user_id)
    if category is None:
        raise ValidationAppError("Category not found.", field_errors={"category_id": "not found"})

    item_repo = BudgetItemRepository(db)
    existing = await item_repo.get_by_category_for_user(data.category_id, user_id)
    if existing is not None:
        raise ConflictError("A budget for this category already exists. Edit it instead.")

    budget = await BudgetRepository(db).get_or_create_for_user(user_id)
    item = BudgetItem(
        budget_id=budget.id, category_id=data.category_id, amount_minor=data.amount_minor
    )
    item_repo.add(item)
    await item_repo.flush()

    return await get_budget_item(db, user_id=user_id, item_id=item.id)


async def update_budget_item(
    db: AsyncSession, *, user_id: uuid.UUID, item_id: uuid.UUID, data: BudgetItemUpdate
) -> BudgetItemRead:
    item_repo = BudgetItemRepository(db)
    item = await item_repo.get_by_id_for_user(item_id, user_id)
    if item is None:
        raise NotFoundError("Budget not found.")

    item.amount_minor = data.amount_minor
    await item_repo.flush()

    return await get_budget_item(db, user_id=user_id, item_id=item_id)


async def delete_budget_item(db: AsyncSession, *, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item_repo = BudgetItemRepository(db)
    item = await item_repo.get_by_id_for_user(item_id, user_id)
    if item is None:
        raise NotFoundError("Budget not found.")

    await item_repo.delete(item)
    await item_repo.flush()


async def list_budget_suggestions(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[BudgetSuggestion]:
    """Every suggestion traces to either a real trailing average of actual
    spending or an explicit category default - never a fabricated number.
    A category with neither is simply omitted rather than guessed."""
    now = datetime.now(UTC)
    _, this_month_start, _ = current_month_bounds(now)
    lookback_start = month_start_n_months_ago(this_month_start, _SUGGESTION_LOOKBACK_MONTHS)

    existing_items = await BudgetItemRepository(db).list_for_user(user_id)
    budgeted_category_ids = {item.category_id for item in existing_items}

    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=False)
    candidates = [c for c in categories if c.id not in budgeted_category_ids]
    if not candidates:
        return []

    base_currency = await _get_base_currency(db, user_id)
    historical_transactions = await TransactionRepository(db).list_in_range(
        user_id, date_from=lookback_start, date_to=this_month_start, currency=base_currency
    )

    per_category_month_sums: dict[uuid.UUID, dict[tuple[int, int], int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for txn in historical_transactions:
        if txn.type != TransactionType.EXPENSE or txn.category_id is None:
            continue
        month_key = (txn.occurred_at.year, txn.occurred_at.month)
        per_category_month_sums[txn.category_id][month_key] += txn.amount_minor

    suggestions: list[BudgetSuggestion] = []
    for category in candidates:
        month_sums = per_category_month_sums.get(category.id)
        if month_sums:
            months_of_data = len(month_sums)
            average_minor = round(sum(month_sums.values()) / months_of_data)
            plural = "s" if months_of_data > 1 else ""
            suggestions.append(
                BudgetSuggestion(
                    category_id=category.id,
                    category_name=category.name,
                    category_icon=category.icon,
                    category_color=category.color,
                    suggested_amount_minor=average_minor,
                    based_on=f"average of the last {months_of_data} month{plural} of spending",
                )
            )
        elif category.budget_minor is not None and category.budget_minor > 0:
            suggestions.append(
                BudgetSuggestion(
                    category_id=category.id,
                    category_name=category.name,
                    category_icon=category.icon,
                    category_color=category.color,
                    suggested_amount_minor=category.budget_minor,
                    based_on="this category's default budget",
                )
            )
        # else: no real basis for a suggestion - omit rather than guess.

    return suggestions
