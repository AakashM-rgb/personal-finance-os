"""Result-correctness tests: real seeded transactions through the real
app.search.service.search() pipeline, verifying returned results match
the actual database-backed data exactly - never fabricated, never another
user's, never outside the interpreted filter.
"""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.transaction_repository import TransactionFilters, TransactionRepository


async def _register(client: AsyncClient, *, email: str) -> tuple[str, dict]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return data["user"]["id"], {"Authorization": f"Bearer {data['access_token']}"}


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Main Bank")
    payload.setdefault("type", "bank_account")
    payload.setdefault("balance_minor", 10_000_00)
    payload.setdefault("currency", "INR")
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found")


async def _create_transaction(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _search(client: AsyncClient, headers: dict, query: str, **extra) -> dict:
    response = await client.post(
        "/api/v1/search/financial", headers=headers, json={"query": query, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- food last month ---------------------------------------------------------------------


async def test_food_last_month_returns_only_matching_transactions(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    transport_id = await _get_category_id(client, auth_headers, "Transport")

    today = date.today()
    last_month = date(today.year, today.month, 1) - timedelta(days=1)
    in_last_month = date(last_month.year, last_month.month, min(last_month.day, 15))

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=45000,
        category_id=food_id,
        occurred_at=f"{in_last_month.isoformat()}T12:00:00Z",
        description="Groceries last month",
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=20000,
        category_id=transport_id,
        occurred_at=f"{in_last_month.isoformat()}T13:00:00Z",
        description="Transport last month",
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=99999,
        category_id=food_id,
        occurred_at=f"{today.isoformat()}T12:00:00Z",
        description="Food this month - must not appear",
    )

    data = await _search(client, auth_headers, "food last month")
    assert data["requires_confirmation"] is False
    assert data["result_count"] == 1
    assert data["results"][0]["amount_minor"] == 45000
    assert data["results"][0]["category_name"] == "Food"


# --- Amazon above amount ----------------------------------------------------------------


async def test_amazon_above_amount_returns_only_matching(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today().isoformat()

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=150000,
        merchant="Amazon",
        occurred_at=f"{today}T12:00:00Z",
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=50000,
        merchant="Amazon",
        occurred_at=f"{today}T13:00:00Z",
        description="Amazon but below threshold",
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=200000,
        merchant="Flipkart",
        occurred_at=f"{today}T14:00:00Z",
    )

    data = await _search(client, auth_headers, "Amazon purchases above ₹1000")
    assert data["result_count"] == 1
    assert data["results"][0]["amount_minor"] == 150000
    assert data["results"][0]["merchant"] == "Amazon"


# --- biggest expenses this year ----------------------------------------------------------


async def test_biggest_expenses_this_year_sorted_descending(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today().isoformat()
    amounts = [10000, 500000, 250000]
    for amount in amounts:
        await _create_transaction(
            client,
            auth_headers,
            account_id=account["id"],
            type="expense",
            amount_minor=amount,
            occurred_at=f"{today}T12:00:00Z",
        )

    data = await _search(client, auth_headers, "biggest expenses this year")
    returned_amounts = [r["amount_minor"] for r in data["results"]]
    assert returned_amounts == sorted(amounts, reverse=True)


# --- weekend spending --------------------------------------------------------------------


async def test_weekend_spending_returns_only_saturday_sunday(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    # 2026-03-14 is a Saturday, 2026-03-16 is a Monday (both in "this month"
    # relative to any "now" would vary - use explicit dates far enough in
    # the past/future is unnecessary; the filter is pure day-of-week, not
    # period-bound, so any real Saturday/weekday pair works regardless of
    # when the test runs).
    saturday = date(2026, 3, 14)
    monday = date(2026, 3, 16)

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=30000,
        occurred_at=f"{saturday.isoformat()}T12:00:00Z",
        description="Weekend purchase",
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=40000,
        occurred_at=f"{monday.isoformat()}T12:00:00Z",
        description="Weekday purchase",
    )

    data = await _search(client, auth_headers, "weekend spending")
    assert data["result_count"] == 1
    assert data["results"][0]["description"] == "Weekend purchase"


async def test_weekend_day_of_week_filter_correct_under_non_utc_session_timezone(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Postgres's EXTRACT(DOW) uses the session's TimeZone setting unless
    pinned - the same class of bug already documented and fixed for
    date_trunc elsewhere in this app. A transaction at 2026-03-14 23:30 UTC
    (a Saturday) must still be classified as Saturday even when the DB
    session's own TimeZone is set to something that would otherwise shift
    it onto Sunday."""
    user_id, headers = await _register(client, email="tz-weekend@example.com")
    account = await _create_account(client, headers)
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=12345,
        occurred_at="2026-03-14T23:30:00Z",
        description="Late Saturday UTC",
    )

    await db_session.execute(text("SET TIME ZONE 'Pacific/Kiritimati'"))  # UTC+14
    try:
        filters = TransactionFilters(days_of_week=[6])  # Saturday
        results, total = await TransactionRepository(db_session).list_for_user(
            uuid.UUID(user_id), filters
        )
        assert total == 1
        assert results[0].description == "Late Saturday UTC"
    finally:
        # A session-level SET is connection-scoped, not session-object-scoped -
        # reset it so a pooled connection can't leak a non-UTC timezone into
        # an unrelated later test.
        await db_session.execute(text("SET TIME ZONE 'UTC'"))


# --- subscriptions this month -------------------------------------------------------------


async def test_subscriptions_this_month_excludes_plain_recurring_transactions(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today().isoformat()

    subscription = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": today,
        },
    )
    assert subscription.status_code == 201, subscription.text

    # A plain recurring transaction (e.g. rent) that is NOT a subscription.
    await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 2000000,
            "frequency": "monthly",
            "start_date": today,
        },
    )

    generate = await client.post("/api/v1/recurring-transactions/generate", headers=auth_headers)
    assert generate.status_code == 200, generate.text

    data = await _search(client, auth_headers, "subscriptions this month")
    assert data["result_count"] == 1
    assert data["results"][0]["merchant"] is None
    assert data["results"][0]["amount_minor"] == 64900


async def test_subscriptions_this_month_empty_when_user_has_no_subscriptions(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=5000,
        occurred_at=f"{date.today().isoformat()}T12:00:00Z",
    )
    data = await _search(client, auth_headers, "subscriptions this month")
    assert data["result_count"] == 0
    assert data["total_matching"] == 0


# --- transfers excluded ------------------------------------------------------------------


async def test_transfers_excluded_from_default_expense_search(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    other_account = await _create_account(client, auth_headers, name="Savings")
    today = date.today().isoformat()

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="transfer",
        transfer_account_id=other_account["id"],
        amount_minor=500000,
        occurred_at=f"{today}T12:00:00Z",
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=30000,
        occurred_at=f"{today}T13:00:00Z",
    )

    data = await _search(client, auth_headers, "this month")
    assert data["requires_confirmation"] is True  # bare period, no other signal
    confirmed = await _search(client, auth_headers, "this month", confirmed=True)
    assert confirmed["result_count"] == 1
    assert confirmed["results"][0]["amount_minor"] == 30000
    assert confirmed["results"][0]["type"] == "expense"


# --- empty results / limits ---------------------------------------------------------------


async def test_empty_search_results_are_clean(client: AsyncClient, auth_headers: dict) -> None:
    data = await _search(client, auth_headers, "Amazon purchases above ₹1000")
    assert data["result_count"] == 0
    assert data["total_matching"] == 0
    assert data["results"] == []
    assert data["limited"] is False


async def test_result_limit_is_reflected_in_response(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today().isoformat()
    for i in range(5):
        await _create_transaction(
            client,
            auth_headers,
            account_id=account["id"],
            type="expense",
            amount_minor=1000 + i,
            merchant="Amazon",
            occurred_at=f"{today}T0{i + 1}:00:00Z",
        )

    data = await _search(client, auth_headers, "Amazon")
    assert data["result_count"] == 5
    assert data["total_matching"] == 5
    assert data["limited"] is False
