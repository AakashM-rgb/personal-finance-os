"""Natural-Language Financial Search orchestration - the ONLY place a
user's search text reaches the interpreter, and the ONLY caller of
app.search.query_builder for a search request.

    Authenticated user
        -> Search API (app.api.v1.search)
        -> this service
        -> app.search.interpreter (produces a validated FinancialSearchQuery)
        -> app.search.query_builder (maps it onto predefined TransactionFilters)
        -> app.services.transaction_service (existing, authorized)
        -> database

`user_id` is always the authenticated caller's own id from the request
context - never read from the query text, the interpreter's output, or any
request field. `category_override_id` is the one exception to "never trust
client input for a filter", and even it is re-verified against the
caller's own visible categories before use, exactly like any other
user-supplied id elsewhere in this app.
"""

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.schemas import TransactionSummary
from app.core.errors import NotFoundError
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.category import CategoryRead
from app.schemas.transaction import TransactionRead
from app.search import interpreter as search_interpreter
from app.search.category_resolution import CategoryResolution
from app.search.interpreter import InterpretationOutcome
from app.search.query_builder import build_transaction_filters
from app.search.schemas import (
    CategoryCandidate,
    InterpretedCriteria,
    SearchRequest,
    SearchResponse,
)
from app.services import category_service, transaction_service

logger = logging.getLogger("app.search")


async def _get_currency_and_ai_enabled(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, bool]:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    if settings is None:
        return "INR", True
    return settings.currency, settings.ai_enabled


async def _resolve_override_category(
    db: AsyncSession, *, user_id: uuid.UUID, category_id: uuid.UUID
) -> CategoryResolution:
    try:
        # Reuses the exact same ownership check + CategoryRead conversion
        # every other endpoint uses - never a second, divergent way to
        # look up a category.
        category = await category_service.get_category(
            db, user_id=user_id, category_id=category_id
        )
    except NotFoundError:
        return CategoryResolution(matched=None)
    return CategoryResolution(matched=category)


def _build_interpreted_criteria(
    outcome: InterpretationOutcome, *, currency: str, category_name: str | None
) -> InterpretedCriteria:
    query = outcome.query
    return InterpretedCriteria(
        search_text=query.search_text,
        category_name=category_name,
        start_date=query.start_date,
        end_date=query.end_date,
        min_amount_minor=query.min_amount_minor,
        max_amount_minor=query.max_amount_minor,
        transaction_type=query.transaction_type,
        is_weekend_only=query.days_of_week is not None,
        subscriptions_only=query.subscriptions_only,
        sort=query.sort,
        limit=query.limit,
        currency=currency,
    )


def _to_summary(
    transaction: TransactionRead, categories_by_id: dict[uuid.UUID, CategoryRead]
) -> TransactionSummary:
    category = categories_by_id.get(transaction.category_id) if transaction.category_id else None
    # `categories_by_id` holds CategoryRead (from category_service.list_categories),
    # not the ORM Category category_service.display_name expects - the
    # same "Uncategorized" fallback convention, applied directly here.
    category_name = category.name if category is not None else category_service.UNCATEGORIZED_NAME
    return TransactionSummary(
        id=transaction.id,
        occurred_at=transaction.occurred_at,
        type=transaction.type,
        amount_minor=transaction.amount_minor,
        currency=transaction.currency,
        category_name=category_name,
        merchant=transaction.merchant,
        description=transaction.description,
    )


async def search(db: AsyncSession, *, user_id: uuid.UUID, request: SearchRequest) -> SearchResponse:
    started = time.perf_counter()

    categories = await category_service.list_categories(db, user_id=user_id, include_inactive=False)
    currency, ai_enabled = await _get_currency_and_ai_enabled(db, user_id)
    interpreter_name = search_interpreter.get_search_interpreter(ai_enabled=ai_enabled).name

    outcome = await search_interpreter.interpret(
        request.query, categories=categories, now=datetime.now(UTC), ai_enabled=ai_enabled
    )

    category_name: str | None = None
    if request.category_override_id is not None:
        override = await _resolve_override_category(
            db, user_id=user_id, category_id=request.category_override_id
        )
        if override.matched is not None:
            outcome.query.category_id = override.matched.id
            category_name = override.matched.name
            outcome = InterpretationOutcome(
                query=outcome.query,
                requires_confirmation=False,
                ambiguity_reason=None,
                ambiguous_categories=[],
            )
    elif outcome.query.category_id is not None:
        matched = next((c for c in categories if c.id == outcome.query.category_id), None)
        category_name = matched.name if matched is not None else None

    interpretation = _build_interpreted_criteria(
        outcome, currency=currency, category_name=category_name
    )

    if outcome.requires_confirmation and not request.confirmed:
        logger.info(
            "search_requires_confirmation",
            extra={
                "user_id": str(user_id),
                "interpreter": interpreter_name,
                "ambiguous_category_count": len(outcome.ambiguous_categories),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return SearchResponse(
            interpretation=interpretation,
            requires_confirmation=True,
            ambiguity_reason=outcome.ambiguity_reason,
            ambiguous_categories=[
                CategoryCandidate(id=c.id, name=c.name, icon=c.icon)
                for c in outcome.ambiguous_categories
            ],
            results=[],
            result_count=0,
            total_matching=0,
            limited=False,
            provider=interpreter_name,
        )

    subscription_recurring_ids: list[uuid.UUID] | None = None
    if outcome.query.subscriptions_only:
        rows = await SubscriptionRepository(db).list_for_user(user_id)
        subscription_recurring_ids = [recurring.id for _sub, recurring in rows]

    filters = build_transaction_filters(
        outcome.query, subscription_recurring_ids=subscription_recurring_ids
    )

    try:
        transactions, total = await transaction_service.list_transactions(
            db, user_id=user_id, filters=filters
        )
    except Exception:  # noqa: BLE001 - logged safely, then re-raised unchanged
        logger.error(
            "search_execution_failed",
            extra={
                "user_id": str(user_id),
                "interpreter": interpreter_name,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
            exc_info=True,
        )
        raise

    categories_by_id = {c.id: c for c in categories}
    results = [_to_summary(t, categories_by_id) for t in transactions]

    logger.info(
        "search_executed",
        extra={
            "user_id": str(user_id),
            "interpreter": interpreter_name,
            "result_count": len(results),
            "total_matching": total,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )

    return SearchResponse(
        interpretation=interpretation,
        requires_confirmation=False,
        ambiguity_reason=None,
        ambiguous_categories=[],
        results=results,
        result_count=len(results),
        total_matching=total,
        limited=total > len(results),
        provider=interpreter_name,
    )
