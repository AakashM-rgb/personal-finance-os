"""The ONLY place a validated app.search.schemas.FinancialSearchQuery is
translated into a database query - and it maps onto the SAME predefined,
allowlisted app.repositories.transaction_repository.TransactionFilters the
rest of the app already uses for the regular transactions list. There is
no generic filter engine here: every field is read by name and mapped onto
one specific, typed TransactionFilters field - an interpreter can never
smuggle through a filter this function doesn't already know how to
construct, because FinancialSearchQuery's own `extra="forbid"` already
rejected anything else before this module ever saw it.
"""

import uuid
from datetime import UTC, datetime, time

from app.repositories.transaction_repository import SortDirection, SortField, TransactionFilters
from app.search.schemas import FinancialSearchQuery, SortOption

_SORT_MAP: dict[SortOption, tuple[SortField, SortDirection]] = {
    "date_desc": ("occurred_at", "desc"),
    "date_asc": ("occurred_at", "asc"),
    "amount_desc": ("amount_minor", "desc"),
    "amount_asc": ("amount_minor", "asc"),
}


def build_transaction_filters(
    query: FinancialSearchQuery, *, subscription_recurring_ids: list[uuid.UUID] | None
) -> TransactionFilters:
    """`subscription_recurring_ids` is the caller's already-fetched set of
    the AUTHENTICATED user's own subscription schedule ids (see
    app.search.service) - passed in only when `query.subscriptions_only`
    is set, never derived here and never anyone else's."""
    date_from = (
        datetime.combine(query.start_date, time.min, tzinfo=UTC) if query.start_date else None
    )
    date_to = datetime.combine(query.end_date, time.max, tzinfo=UTC) if query.end_date else None
    sort_by, sort_dir = _SORT_MAP[query.sort]

    return TransactionFilters(
        search=query.search_text,
        category_id=query.category_id,
        type=query.transaction_type,
        date_from=date_from,
        date_to=date_to,
        amount_min=query.min_amount_minor,
        amount_max=query.max_amount_minor,
        days_of_week=query.days_of_week,
        recurring_transaction_ids=(
            subscription_recurring_ids if query.subscriptions_only else None
        ),
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=query.limit,
        offset=0,
    )
