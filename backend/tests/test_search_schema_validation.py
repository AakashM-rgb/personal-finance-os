"""Validation tests for app.search.schemas.FinancialSearchQuery - the ONE
structure a natural-language interpretation is ever allowed to produce.
These are the core security tests for Step 15: an interpreter (deterministic
or AI-assisted) can propose anything, but only what survives this
validation ever reaches app.search.query_builder.
"""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.search.schemas import MAX_RESULT_LIMIT, FinancialSearchQuery, SearchRequest


def test_valid_query_constructs() -> None:
    query = FinancialSearchQuery(search_text="Amazon", min_amount_minor=1000)
    assert query.search_text == "Amazon"


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"search_text": "Amazon", "sql": "DROP TABLE users"})


def test_field_operator_value_triple_is_rejected() -> None:
    """The exact shape CLAUDE.md/§11 explicitly forbids as an indirect
    arbitrary-query mechanism."""
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate(
            {"field": "amount_minor", "operator": ">", "value": 1000}
        )


def test_raw_sql_string_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"raw_sql": "SELECT * FROM transactions"})


def test_user_id_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"user_id": str(uuid.uuid4())})


def test_account_id_field_is_rejected() -> None:
    """FinancialSearchQuery deliberately has no account_id field at all -
    an interpreter can never target another account this way."""
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"account_id": str(uuid.uuid4())})


def test_limit_within_bound_accepted() -> None:
    assert FinancialSearchQuery(limit=MAX_RESULT_LIMIT).limit == MAX_RESULT_LIMIT


def test_limit_exceeding_maximum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(limit=MAX_RESULT_LIMIT + 1)


def test_limit_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(limit=0)


def test_limit_negative_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(limit=-5)


def test_negative_min_amount_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(min_amount_minor=-100)


def test_negative_max_amount_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(max_amount_minor=-1)


def test_min_amount_exceeding_max_amount_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(min_amount_minor=5000, max_amount_minor=1000)


def test_min_amount_equal_to_max_amount_is_accepted() -> None:
    query = FinancialSearchQuery(min_amount_minor=1000, max_amount_minor=1000)
    assert query.min_amount_minor == query.max_amount_minor == 1000


def test_start_date_after_end_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(start_date=date(2026, 3, 1), end_date=date(2026, 1, 1))


def test_equal_start_and_end_date_is_accepted() -> None:
    query = FinancialSearchQuery(start_date=date(2026, 3, 1), end_date=date(2026, 3, 1))
    assert query.start_date == query.end_date


def test_unbounded_date_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(start_date=date(2000, 1, 1), end_date=date(2026, 1, 1))


def test_invalid_transaction_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"transaction_type": "not_a_real_type"})


def test_invalid_sort_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"sort": "amount_ascending_by_bribery"})


def test_days_of_week_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(days_of_week=[0, 7])


def test_days_of_week_negative_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(days_of_week=[-1])


def test_days_of_week_empty_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(days_of_week=[])


def test_days_of_week_duplicates_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(days_of_week=[0, 0])


def test_search_text_over_max_length_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery(search_text="x" * 201)


def test_invalid_category_id_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FinancialSearchQuery.model_validate({"category_id": "not-a-uuid"})


# --- SearchRequest (the actual API request body) --------------------------------------------


def test_search_request_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "food", "tool_name": "execute_sql"})


def test_search_request_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="")


def test_search_request_rejects_overlong_query() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="x" * 201)


def test_search_request_defaults() -> None:
    request = SearchRequest(query="food last month")
    assert request.confirmed is False
    assert request.category_override_id is None
