import uuid
from datetime import date

from app.models.transaction import TransactionType
from app.search.query_builder import build_transaction_filters
from app.search.schemas import FinancialSearchQuery


def test_search_text_maps_to_filters_search() -> None:
    query = FinancialSearchQuery(search_text="Amazon")
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.search == "Amazon"


def test_category_id_passthrough() -> None:
    category_id = uuid.uuid4()
    query = FinancialSearchQuery(category_id=category_id)
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.category_id == category_id


def test_date_range_converted_to_full_day_bounds() -> None:
    query = FinancialSearchQuery(start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.date_from.date() == date(2026, 8, 1)
    assert filters.date_from.hour == 0
    assert filters.date_to.date() == date(2026, 8, 31)
    assert filters.date_to.hour == 23


def test_amount_bounds_passthrough() -> None:
    query = FinancialSearchQuery(min_amount_minor=1000, max_amount_minor=5000)
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.amount_min == 1000
    assert filters.amount_max == 5000


def test_transaction_type_passthrough() -> None:
    query = FinancialSearchQuery(transaction_type=TransactionType.EXPENSE)
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.type == TransactionType.EXPENSE


def test_days_of_week_passthrough() -> None:
    query = FinancialSearchQuery(days_of_week=[0, 6])
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.days_of_week == [0, 6]


def test_subscriptions_only_uses_provided_recurring_ids() -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]
    query = FinancialSearchQuery(subscriptions_only=True)
    filters = build_transaction_filters(query, subscription_recurring_ids=ids)
    assert filters.recurring_transaction_ids == ids


def test_subscriptions_only_with_no_subscriptions_filters_to_nothing() -> None:
    query = FinancialSearchQuery(subscriptions_only=True)
    filters = build_transaction_filters(query, subscription_recurring_ids=[])
    assert filters.recurring_transaction_ids == []


def test_non_subscription_search_never_sets_recurring_filter() -> None:
    query = FinancialSearchQuery(search_text="Amazon", subscriptions_only=False)
    filters = build_transaction_filters(query, subscription_recurring_ids=[uuid.uuid4()])
    assert filters.recurring_transaction_ids is None


def test_sort_mapping() -> None:
    for sort, expected in [
        ("date_desc", ("occurred_at", "desc")),
        ("date_asc", ("occurred_at", "asc")),
        ("amount_desc", ("amount_minor", "desc")),
        ("amount_asc", ("amount_minor", "asc")),
    ]:
        query = FinancialSearchQuery(sort=sort)
        filters = build_transaction_filters(query, subscription_recurring_ids=None)
        assert (filters.sort_by, filters.sort_dir) == expected


def test_limit_passthrough() -> None:
    query = FinancialSearchQuery(limit=45)
    filters = build_transaction_filters(query, subscription_recurring_ids=None)
    assert filters.limit == 45
    assert filters.offset == 0
