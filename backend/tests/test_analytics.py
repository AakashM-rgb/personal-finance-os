from datetime import date, timedelta

from httpx import AsyncClient


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _iso(d: date) -> str:
    return f"{d.isoformat()}T12:00:00Z"


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 10000000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def _create_transaction(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_analytics(client: AsyncClient, headers: dict, **params) -> dict:
    response = await client.get("/api/v1/analytics", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- empty dataset --------------------------------------------------------------------


async def test_empty_dataset_returns_zeroed_analytics_without_crashing(
    client: AsyncClient, auth_headers: dict
) -> None:
    data = await _get_analytics(client, auth_headers, range="current_month")

    assert data["category_breakdown"]["items"] == []
    assert data["category_breakdown"]["total_expense_minor"] == 0
    assert data["income_vs_expense"]["total_income_minor"] == 0
    assert data["income_vs_expense"]["total_expense_minor"] == 0
    assert data["income_vs_expense"]["net_minor"] == 0
    assert data["income_vs_expense"]["is_spending_more_than_earning"] is False
    assert data["budget_performance"] == []
    assert data["recurring_expense_breakdown"]["items"] == []
    assert data["recurring_expense_breakdown"]["total_scheduled_monthly_minor"] == 0
    assert data["recurring_expense_breakdown"]["total_actual_paid_minor"] == 0
    assert data["recurring_expense_breakdown"]["recurring_share_of_expense_percent"] is None

    # A single-month range has exactly one savings-trend point -> not
    # enough data points to determine a trend.
    assert len(data["savings_trend"]["points"]) == 1
    assert data["savings_trend"]["trend"]["direction"] is None

    # Every day in the current month is zero-filled but still present.
    assert all(p["amount_minor"] == 0 for p in data["daily_spending"]["points"])
    assert data["daily_spending"]["highest_amount_minor"] == 0
    assert data["daily_spending"]["highest_day"] is not None

    assert all(p["amount_minor"] == 0 for p in data["spending_over_time"]["points"])
    assert data["spending_over_time"]["trend"]["direction"] == "flat"
    assert data["spending_over_time"]["trend"]["percent_change"] == 0.0


async def test_custom_range_rejects_from_after_to(client: AsyncClient, auth_headers: dict) -> None:
    today = date.today()
    response = await client.get(
        "/api/v1/analytics",
        headers=auth_headers,
        params={
            "range": "custom",
            "custom_from": today.isoformat(),
            "custom_to": (today - timedelta(days=5)).isoformat(),
        },
    )
    assert response.status_code == 422


# --- date-range boundaries -------------------------------------------------------------


async def test_current_month_excludes_the_last_day_of_the_previous_month(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())
    last_day_of_previous_month = month_start - timedelta(days=1)

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=11111,
        category_id=food_id,
        occurred_at=_iso(last_day_of_previous_month),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=22222,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )

    current = await _get_analytics(client, auth_headers, range="current_month")
    assert current["category_breakdown"]["total_expense_minor"] == 22222

    previous = await _get_analytics(client, auth_headers, range="previous_month")
    assert previous["category_breakdown"]["total_expense_minor"] == 11111


async def test_custom_range_is_inclusive_of_the_end_date(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=5000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )

    data = await _get_analytics(
        client,
        auth_headers,
        range="custom",
        custom_from=month_start.isoformat(),
        custom_to=month_start.isoformat(),
    )
    assert data["category_breakdown"]["total_expense_minor"] == 5000
    assert data["date_from"] == month_start.isoformat()
    assert data["date_to"] == month_start.isoformat()


# --- income vs expense + transfer exclusion ---------------------------------------------


async def test_income_vs_expense_excludes_transfers(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    other_account = await _create_account(client, auth_headers, name="Savings")
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="income",
        amount_minor=500000,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=195000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="transfer",
        transfer_account_id=other_account["id"],
        amount_minor=999999,
        occurred_at=_iso(month_start),
    )

    data = await _get_analytics(client, auth_headers, range="current_month")
    income_vs_expense = data["income_vs_expense"]
    assert income_vs_expense["total_income_minor"] == 500000
    assert income_vs_expense["total_expense_minor"] == 195000
    assert income_vs_expense["net_minor"] == 305000
    assert income_vs_expense["is_spending_more_than_earning"] is False

    # The transfer must not appear anywhere - category breakdown, daily
    # spending, or spending-over-time either.
    assert data["category_breakdown"]["total_expense_minor"] == 195000
    assert sum(p["amount_minor"] for p in data["daily_spending"]["points"]) == 195000
    assert sum(p["amount_minor"] for p in data["spending_over_time"]["points"]) == 195000


async def test_spending_more_than_earning_is_true_on_a_deficit(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="income",
        amount_minor=100000,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=250000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )

    data = await _get_analytics(client, auth_headers, range="current_month")
    assert data["income_vs_expense"]["net_minor"] == -150000
    assert data["income_vs_expense"]["is_spending_more_than_earning"] is True


# --- category breakdown, including uncategorized ----------------------------------------


async def test_category_breakdown_handles_uncategorized_explicitly(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=175000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=20000,
        occurred_at=_iso(month_start),
        # no category_id - uncategorized
    )

    data = await _get_analytics(client, auth_headers, range="current_month")
    breakdown = data["category_breakdown"]
    assert breakdown["total_expense_minor"] == 195000
    assert len(breakdown["items"]) == 2

    food_item = next(i for i in breakdown["items"] if i["category_id"] == food_id)
    uncategorized_item = next(i for i in breakdown["items"] if i["category_id"] is None)

    assert food_item["amount_minor"] == 175000
    assert food_item["percent"] == 89.7
    assert uncategorized_item["name"] == "Uncategorized"
    assert uncategorized_item["icon"] == "🏷️"
    assert uncategorized_item["amount_minor"] == 20000
    assert uncategorized_item["percent"] == 10.3


# --- spending over time / trend ---------------------------------------------------------


async def test_spending_over_time_zero_fills_days_with_no_spending(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=10000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )

    data = await _get_analytics(client, auth_headers, range="current_month")
    points = data["spending_over_time"]["points"]
    assert data["spending_over_time"]["granularity"] == "day"
    # Every calendar day of the month is present, not just the one with data.
    assert len(points) >= 28
    by_day = {p["period"]: p["amount_minor"] for p in points}
    assert by_day[month_start.isoformat()] == 10000
    zero_days = [amt for day, amt in by_day.items() if day != month_start.isoformat()]
    assert all(amt == 0 for amt in zero_days)


async def test_spending_over_time_detects_an_increasing_trend(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    today = date.today()
    # Two months of clearly increasing spend, well inside a last_3_months window.
    two_months_ago = today.replace(day=1)
    for _ in range(2):
        two_months_ago = (two_months_ago - timedelta(days=1)).replace(day=1)

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=10000,
        category_id=food_id,
        occurred_at=_iso(two_months_ago),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=100000,
        category_id=food_id,
        occurred_at=_iso(_month_start(today)),
    )

    data = await _get_analytics(client, auth_headers, range="last_3_months")
    assert data["spending_over_time"]["granularity"] == "month"
    assert data["spending_over_time"]["trend"]["direction"] == "increasing"


# --- savings trend -----------------------------------------------------------------------


async def test_savings_trend_reflects_income_minus_expense_per_month(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="income",
        amount_minor=500000,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=200000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )

    data = await _get_analytics(client, auth_headers, range="current_month")
    points = data["savings_trend"]["points"]
    assert len(points) == 1
    assert points[0]["income_minor"] == 500000
    assert points[0]["expense_minor"] == 200000
    assert points[0]["savings_minor"] == 300000
    assert points[0]["savings_rate"] == 60.0


# --- daily spending ------------------------------------------------------------------------


async def test_daily_spending_identifies_the_highest_day(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = _month_start(date.today())
    big_day = month_start + timedelta(days=4)

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=5000,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=999999,
        category_id=food_id,
        occurred_at=_iso(big_day),
    )

    data = await _get_analytics(client, auth_headers, range="current_month")
    daily = data["daily_spending"]
    assert daily["highest_day"] == big_day.isoformat()
    assert daily["highest_amount_minor"] == 999999


# --- budget performance reuse ----------------------------------------------------------


async def test_budget_performance_matches_the_budgets_endpoint_exactly(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")

    budget_response = await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": food_id, "amount_minor": 500000},
    )
    assert budget_response.status_code == 201

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=324000,
        category_id=food_id,
        occurred_at=_iso(date.today()),
    )

    budgets_direct = (await client.get("/api/v1/budgets", headers=auth_headers)).json()["data"]
    analytics_data = await _get_analytics(client, auth_headers, range="current_month")
    assert analytics_data["budget_performance"] == budgets_direct


# --- recurring expense breakdown --------------------------------------------------------


async def test_recurring_expense_breakdown_distinguishes_scheduled_from_actual(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    month_start = _month_start(date.today())

    plain_recurring = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 300000,
            "frequency": "monthly",
            "start_date": month_start.isoformat(),
        },
    )
    assert plain_recurring.status_code == 201

    subscription = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": month_start.isoformat(),
        },
    )
    assert subscription.status_code == 201

    # An income-type recurring transaction must never appear in an
    # EXPENSE breakdown.
    salary = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Salary",
            "account_id": account["id"],
            "type": "income",
            "amount_minor": 5000000,
            "frequency": "monthly",
            "start_date": month_start.isoformat(),
        },
    )
    assert salary.status_code == 201

    generate_response = await client.post(
        "/api/v1/recurring-transactions/generate", headers=auth_headers
    )
    assert generate_response.status_code == 200

    data = await _get_analytics(client, auth_headers, range="current_month")
    breakdown = data["recurring_expense_breakdown"]

    assert len(breakdown["items"]) == 2  # Rent and Netflix - not Salary
    names = {item["name"] for item in breakdown["items"]}
    assert names == {"Rent", "Netflix"}

    rent_item = next(i for i in breakdown["items"] if i["name"] == "Rent")
    netflix_item = next(i for i in breakdown["items"] if i["name"] == "Netflix")

    assert rent_item["is_subscription"] is False
    assert rent_item["scheduled_monthly_cost_minor"] == 300000
    assert rent_item["actual_paid_minor"] == 300000  # billed once this month

    assert netflix_item["is_subscription"] is True
    assert netflix_item["scheduled_monthly_cost_minor"] == 64900
    assert netflix_item["actual_paid_minor"] == 64900

    assert breakdown["total_scheduled_monthly_minor"] == 364900
    assert breakdown["total_actual_paid_minor"] == 364900
    # No other (manual) expense exists this month, so 100% of real
    # expense in range is recurring.
    assert breakdown["recurring_share_of_expense_percent"] == 100.0


async def test_recurring_expense_breakdown_never_implies_a_future_schedule_has_been_paid(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    future_start = date.today() + timedelta(days=60)

    response = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Future Bill",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 50000,
            "frequency": "monthly",
            "start_date": future_start.isoformat(),
        },
    )
    assert response.status_code == 201

    # Deliberately do NOT call generate - nothing has actually been billed.
    data = await _get_analytics(client, auth_headers, range="current_month")
    item = data["recurring_expense_breakdown"]["items"][0]
    assert item["is_active"] is True
    assert item["scheduled_monthly_cost_minor"] == 50000  # a real, computed commitment
    assert item["actual_paid_minor"] == 0  # never billed yet - not implied as paid


async def test_recurring_expense_breakdown_excludes_inactive_from_scheduled_total(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    month_start = _month_start(date.today())

    created = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Cancelled Gym",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 150000,
            "frequency": "monthly",
            "start_date": month_start.isoformat(),
        },
    )
    recurring_id = created.json()["data"]["id"]

    await client.post("/api/v1/recurring-transactions/generate", headers=auth_headers)
    await client.delete(f"/api/v1/recurring-transactions/{recurring_id}", headers=auth_headers)

    data = await _get_analytics(client, auth_headers, range="current_month")
    breakdown = data["recurring_expense_breakdown"]
    item = breakdown["items"][0]

    assert item["is_active"] is False
    # Real money WAS paid before cancellation - historical fact, always counted.
    assert item["actual_paid_minor"] == 150000
    assert breakdown["total_actual_paid_minor"] == 150000
    # But it no longer counts toward CURRENT ongoing commitment.
    assert breakdown["total_scheduled_monthly_minor"] == 0


# --- authorization isolation ------------------------------------------------------------


async def test_analytics_never_leaks_another_users_data(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    food_id = await _get_category_id(client, other_auth_headers, "Food")
    month_start = _month_start(date.today())

    await _create_transaction(
        client,
        other_auth_headers,
        account_id=their_account["id"],
        type="expense",
        amount_minor=999999,
        category_id=food_id,
        occurred_at=_iso(month_start),
    )
    await client.post(
        "/api/v1/budgets",
        headers=other_auth_headers,
        json={"category_id": food_id, "amount_minor": 100000},
    )

    my_data = await _get_analytics(client, auth_headers, range="current_month")
    assert my_data["category_breakdown"]["items"] == []
    assert my_data["category_breakdown"]["total_expense_minor"] == 0
    assert my_data["budget_performance"] == []
