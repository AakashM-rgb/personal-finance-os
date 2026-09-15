from datetime import date

from httpx import AsyncClient


def _iso(d: date, time_str: str = "09:00:00") -> str:
    return f"{d.isoformat()}T{time_str}Z"


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


async def _get_calendar(client: AsyncClient, headers: dict, year: int, month: int) -> dict:
    response = await client.get(
        "/api/v1/calendar", headers=headers, params={"year": year, "month": month}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _day(calendar_month: dict, d: date) -> dict:
    return next(day for day in calendar_month["days"] if day["date"] == d.isoformat())


# --- month navigation / boundaries ----------------------------------------------------


async def test_calendar_returns_the_correct_number_of_days_for_a_31_day_month(
    client: AsyncClient, auth_headers: dict
) -> None:
    calendar_month = await _get_calendar(client, auth_headers, 2026, 1)
    assert len(calendar_month["days"]) == 31
    assert calendar_month["days"][0]["date"] == "2026-01-01"
    assert calendar_month["days"][-1]["date"] == "2026-01-31"


async def test_calendar_returns_28_days_for_february_in_a_non_leap_year(
    client: AsyncClient, auth_headers: dict
) -> None:
    calendar_month = await _get_calendar(client, auth_headers, 2026, 2)
    assert len(calendar_month["days"]) == 28
    assert calendar_month["days"][-1]["date"] == "2026-02-28"


async def test_calendar_returns_29_days_for_february_in_a_leap_year(
    client: AsyncClient, auth_headers: dict
) -> None:
    calendar_month = await _get_calendar(client, auth_headers, 2028, 2)
    assert len(calendar_month["days"]) == 29
    assert calendar_month["days"][-1]["date"] == "2028-02-29"


async def test_calendar_handles_a_30_day_month(client: AsyncClient, auth_headers: dict) -> None:
    calendar_month = await _get_calendar(client, auth_headers, 2026, 4)
    assert len(calendar_month["days"]) == 30


async def test_calendar_month_and_year_navigation_rolls_over_correctly(
    client: AsyncClient, auth_headers: dict
) -> None:
    december = await _get_calendar(client, auth_headers, 2025, 12)
    january = await _get_calendar(client, auth_headers, 2026, 1)
    assert december["days"][-1]["date"] == "2025-12-31"
    assert january["days"][0]["date"] == "2026-01-01"


# --- daily totals: income, spending, transfer exclusion ------------------------------


async def test_daily_spending_and_income_are_computed_correctly(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    day = date(2026, 9, 10)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=500000,
        occurred_at=_iso(day),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=195000,
        category_id=food_id, occurred_at=_iso(day),
    )

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, day)
    assert target_day["income_minor"] == 500000
    assert target_day["expense_minor"] == 195000
    assert target_day["net_minor"] == 305000


async def test_transfer_excluded_from_totals_but_visible_in_day_transactions(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    other_account = await _create_account(client, auth_headers, name="Savings")
    day = date(2026, 9, 12)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="transfer",
        transfer_account_id=other_account["id"], amount_minor=999999, occurred_at=_iso(day),
    )

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, day)
    assert target_day["income_minor"] == 0
    assert target_day["expense_minor"] == 0
    assert target_day["net_minor"] == 0
    assert len(target_day["transactions"]) == 1
    assert target_day["transactions"][0]["type"] == "transfer"
    assert target_day["transactions"][0]["amount_minor"] == 999999


async def test_empty_days_show_a_clean_zero_state(
    client: AsyncClient, auth_headers: dict
) -> None:
    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, date(2026, 9, 20))
    assert target_day["income_minor"] == 0
    assert target_day["expense_minor"] == 0
    assert target_day["net_minor"] == 0
    assert target_day["transactions"] == []
    assert target_day["bills"] == []


# --- clicking a day: transaction details ----------------------------------------------


async def test_day_transactions_include_useful_details(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    day = date(2026, 9, 14)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=45000,
        category_id=food_id, occurred_at=_iso(day, "14:30:00"), description="Lunch",
    )

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, day)
    assert len(target_day["transactions"]) == 1
    txn = target_day["transactions"][0]
    assert txn["description"] == "Lunch"
    assert txn["category_id"] == food_id
    assert txn["account_id"] == account["id"]
    assert txn["amount_minor"] == 45000
    assert txn["type"] == "expense"
    assert txn["occurred_at"].startswith("2026-09-14T14:30:00")


async def test_multiple_transactions_on_one_day_are_all_returned_sorted(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    day = date(2026, 9, 16)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000,
        occurred_at=_iso(day, "18:00:00"),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=2000,
        occurred_at=_iso(day, "08:00:00"),
    )

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, day)
    assert len(target_day["transactions"]) == 2
    assert target_day["transactions"][0]["amount_minor"] == 2000  # earlier time first
    assert target_day["transactions"][1]["amount_minor"] == 1000


# --- bills / recurring: scheduled vs actually occurred ---------------------------------


async def test_a_future_scheduled_bill_appears_without_being_counted_as_spent(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    bill_day = date(2026, 9, 15)

    created = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 300000,
            "frequency": "monthly",
            "start_date": bill_day.isoformat(),
        },
    )
    assert created.status_code == 201

    # Deliberately never call /recurring-transactions/generate - nothing
    # has actually been paid yet.
    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, bill_day)
    assert target_day["expense_minor"] == 0  # not counted as spent
    assert target_day["transactions"] == []  # no real transaction exists
    assert len(target_day["bills"]) == 1
    assert target_day["bills"][0]["name"] == "Rent"
    assert target_day["bills"][0]["amount_minor"] == 300000
    assert target_day["bills"][0]["is_subscription"] is False


async def test_a_subscription_bill_is_flagged_as_a_subscription(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    bill_day = date(2026, 9, 5)

    created = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": bill_day.isoformat(),
        },
    )
    assert created.status_code == 201

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, bill_day)
    assert len(target_day["bills"]) == 1
    assert target_day["bills"][0]["is_subscription"] is True


async def test_after_generation_a_bill_becomes_a_real_transaction_not_a_duplicate(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    bill_day = date(2026, 9, 1)

    await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 300000,
            "frequency": "monthly",
            "start_date": bill_day.isoformat(),
        },
    )
    generate_response = await client.post(
        "/api/v1/recurring-transactions/generate", headers=auth_headers
    )
    assert generate_response.status_code == 200

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, bill_day)
    # Once generated, it is a REAL transaction and counts as real spending -
    # and it must never also appear as a still-scheduled bill that day.
    assert target_day["expense_minor"] == 300000
    assert len(target_day["transactions"]) == 1
    assert target_day["transactions"][0]["recurring_transaction_id"] is not None
    assert target_day["bills"] == []


async def test_an_inactive_recurring_transaction_produces_no_bills(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    bill_day = date(2026, 9, 22)

    created = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Cancelled Gym",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 150000,
            "frequency": "monthly",
            "start_date": bill_day.isoformat(),
        },
    )
    recurring_id = created.json()["data"]["id"]
    await client.delete(f"/api/v1/recurring-transactions/{recurring_id}", headers=auth_headers)

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, bill_day)
    assert target_day["bills"] == []


# --- timezone / date-boundary correctness ----------------------------------------------


async def test_a_transaction_at_midnight_utc_stays_on_its_own_calendar_day(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    day = date(2026, 9, 1)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000,
        occurred_at=f"{day.isoformat()}T00:00:00Z",
    )

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, day)
    assert target_day["expense_minor"] == 1000
    # It must not have shifted into August due to any timezone conversion
    # during database grouping - it should be the very first day (Sep 1)
    # of THIS month's results, not silently absent from them.
    assert calendar_month["days"][0]["date"] == "2026-09-01"
    assert calendar_month["days"][0]["expense_minor"] == 1000


async def test_a_transaction_late_in_the_day_stays_on_the_same_calendar_day(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    day = date(2026, 9, 30)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=2000,
        occurred_at=f"{day.isoformat()}T23:59:59Z",
    )

    calendar_month = await _get_calendar(client, auth_headers, 2026, 9)
    target_day = _day(calendar_month, day)
    assert target_day["expense_minor"] == 2000
    # It must not have shifted into October.
    assert calendar_month["days"][-1]["date"] == "2026-09-30"
    assert calendar_month["days"][-1]["expense_minor"] == 2000


# --- authorization isolation ------------------------------------------------------------


async def test_calendar_never_leaks_another_users_data(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    day = date(2026, 9, 8)
    await _create_transaction(
        client, other_auth_headers, account_id=their_account["id"], type="expense",
        amount_minor=999999, occurred_at=_iso(day),
    )
    await client.post(
        "/api/v1/recurring-transactions",
        headers=other_auth_headers,
        json={
            "name": "Their Rent",
            "account_id": their_account["id"],
            "type": "expense",
            "amount_minor": 500000,
            "frequency": "monthly",
            "start_date": day.isoformat(),
        },
    )

    my_calendar = await _get_calendar(client, auth_headers, 2026, 9)
    my_day = _day(my_calendar, day)
    assert my_day["expense_minor"] == 0
    assert my_day["transactions"] == []
    assert my_day["bills"] == []


async def test_invalid_month_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/calendar", headers=auth_headers, params={"year": 2026, "month": 13}
    )
    assert response.status_code == 422
