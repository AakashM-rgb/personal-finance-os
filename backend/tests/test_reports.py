from datetime import date, timedelta

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


# --- Monthly report ---------------------------------------------------------------------


async def test_monthly_report_hand_calculated(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = date(2026, 6, 1)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=500000,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=200000,
        category_id=food_id, occurred_at=_iso(month_start),
    )

    response = await client.get(
        "/api/v1/reports/monthly", headers=auth_headers, params={"year": 2026, "month": 6}
    )
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["total_income_minor"] == 500000
    assert report["total_expense_minor"] == 200000
    assert report["net_cash_flow_minor"] == 300000
    assert report["savings_minor"] == 300000
    assert report["savings_rate"] == 60.0
    assert report["date_from"] == "2026-06-01"
    assert report["date_to"] == "2026-06-30"
    assert report["category_breakdown"]["items"][0]["name"] == "Food"


async def test_monthly_report_empty_month(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/reports/monthly", headers=auth_headers, params={"year": 2026, "month": 6}
    )
    report = response.json()["data"]
    assert report["total_income_minor"] == 0
    assert report["savings_rate"] is None
    assert report["category_breakdown"]["items"] == []
    assert report["budget_performance"] == []


async def test_monthly_report_handles_a_leap_year_february(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000,
        occurred_at=_iso(date(2028, 2, 29)),
    )
    response = await client.get(
        "/api/v1/reports/monthly", headers=auth_headers, params={"year": 2028, "month": 2}
    )
    report = response.json()["data"]
    assert report["date_to"] == "2028-02-29"
    assert report["total_expense_minor"] == 1000


# --- Yearly report -----------------------------------------------------------------------


async def test_yearly_report_hand_calculated_with_missing_months(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    # Only January and July have data - the other 10 months must still
    # be represented (as zero), not silently omitted.
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=500000,
        occurred_at=_iso(date(2026, 1, 15)),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=100000,
        occurred_at=_iso(date(2026, 7, 15)),
    )

    response = await client.get(
        "/api/v1/reports/yearly", headers=auth_headers, params={"year": 2026}
    )
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["total_income_minor"] == 500000
    assert report["total_expense_minor"] == 100000
    assert report["net_cash_flow_minor"] == 400000
    assert len(report["monthly_income_trend"]) == 12
    assert len(report["monthly_expense_trend"]) == 12
    assert len(report["monthly_savings_trend"]) == 12

    january = next(p for p in report["monthly_income_trend"] if p["month"] == "2026-01-01")
    march = next(p for p in report["monthly_income_trend"] if p["month"] == "2026-03-01")
    assert january["amount_minor"] == 500000
    assert march["amount_minor"] == 0  # missing month represented as zero, not omitted


# --- Category report --------------------------------------------------------------------


async def test_category_report_uncategorized_handled_explicitly(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    month_start = date(2026, 6, 1)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=175000,
        category_id=food_id, occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=20000,
        occurred_at=_iso(month_start),
    )

    response = await client.get(
        "/api/v1/reports/category",
        headers=auth_headers,
        params={"range": "custom", "custom_from": "2026-06-01", "custom_to": "2026-06-30"},
    )
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["total_expense_minor"] == 195000
    uncategorized = next(i for i in report["items"] if i["category_id"] is None)
    assert uncategorized["name"] == "Uncategorized"
    assert uncategorized["amount_minor"] == 20000
    assert uncategorized["transaction_count"] == 1
    food_item = next(i for i in report["items"] if i["category_id"] == food_id)
    assert food_item["transaction_count"] == 1
    assert food_item["percent"] == 89.7


async def test_category_report_empty_data(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/reports/category", headers=auth_headers, params={"range": "current_month"}
    )
    report = response.json()["data"]
    assert report["items"] == []
    assert report["total_expense_minor"] == 0


# --- Income report -----------------------------------------------------------------------


async def test_income_report_hand_calculated(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    month_start = date(2026, 6, 1)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=500000,
        occurred_at=_iso(month_start), description="Salary",
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=50000,
        occurred_at=_iso(month_start + timedelta(days=5)), description="Freelance",
    )
    # A transfer must never be counted as income.
    other_account = await _create_account(client, auth_headers, name="Savings")
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="transfer",
        transfer_account_id=other_account["id"], amount_minor=999999, occurred_at=_iso(month_start),
    )

    response = await client.get(
        "/api/v1/reports/income",
        headers=auth_headers,
        params={"range": "custom", "custom_from": "2026-06-01", "custom_to": "2026-06-30"},
    )
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["total_income_minor"] == 550000
    assert report["transaction_count"] == 2
    assert len(report["largest_transactions"]) == 2
    assert report["largest_transactions"][0]["amount_minor"] == 500000
    assert sum(p["amount_minor"] for p in report["over_time"]) == 550000


# --- Expense report ----------------------------------------------------------------------


async def test_expense_report_recurring_vs_non_recurring_and_transfer_exclusion(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    other_account = await _create_account(client, auth_headers, name="Savings")
    month_start = date(2026, 6, 1)

    await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Rent", "account_id": account["id"], "type": "expense",
            "amount_minor": 300000, "frequency": "monthly", "start_date": month_start.isoformat(),
        },
    )
    generate_response = await client.post(
        "/api/v1/recurring-transactions/generate", headers=auth_headers
    )
    assert generate_response.status_code == 200

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=50000,
        occurred_at=_iso(month_start), description="Groceries",
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="transfer",
        transfer_account_id=other_account["id"], amount_minor=999999, occurred_at=_iso(month_start),
    )

    response = await client.get(
        "/api/v1/reports/expense",
        headers=auth_headers,
        params={"range": "custom", "custom_from": "2026-06-01", "custom_to": "2026-06-30"},
    )
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["total_expense_minor"] == 350000  # transfer excluded
    assert report["recurring_expense_minor"] == 300000
    assert report["non_recurring_expense_minor"] == 50000
    assert report["largest_transactions"][0]["amount_minor"] == 300000


# --- Budget report -----------------------------------------------------------------------


async def test_budget_report_reuses_budget_service_and_summarizes_risk(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    entertainment_id = await _get_category_id(client, auth_headers, "Entertainment")

    await client.post(
        "/api/v1/budgets", headers=auth_headers,
        json={"category_id": food_id, "amount_minor": 500000},
    )
    await client.post(
        "/api/v1/budgets", headers=auth_headers,
        json={"category_id": entertainment_id, "amount_minor": 10000},
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=15000,
        category_id=entertainment_id, occurred_at=_iso(date.today()),
    )

    budgets_direct = (await client.get("/api/v1/budgets", headers=auth_headers)).json()["data"]
    response = await client.get("/api/v1/reports/budget", headers=auth_headers)
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["items"] == budgets_direct  # identical to the Budgets module's own output
    assert report["exceeded_count"] == 1
    assert report["at_risk_count"] == 1
    assert report["total_budgeted_minor"] == 510000


async def test_budget_report_empty(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/reports/budget", headers=auth_headers)
    report = response.json()["data"]
    assert report["items"] == []
    assert report["at_risk_count"] == 0
    assert report["exceeded_count"] == 0


# --- Savings report ----------------------------------------------------------------------


async def test_savings_report_hand_calculated_and_includes_goals(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    month_start = date(2026, 6, 1)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=500000,
        occurred_at=_iso(month_start),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=200000,
        occurred_at=_iso(month_start),
    )
    await client.post(
        "/api/v1/goals", headers=auth_headers,
        json={
            "name": "New Laptop", "target_amount_minor": 10000000, "current_amount_minor": 2000000,
            "target_date": (date.today() + timedelta(days=300)).isoformat(),
        },
    )

    response = await client.get(
        "/api/v1/reports/savings",
        headers=auth_headers,
        params={"range": "custom", "custom_from": "2026-06-01", "custom_to": "2026-06-30"},
    )
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["savings_minor"] == 300000
    assert report["savings_rate"] == 60.0
    assert len(report["goals"]) == 1
    assert report["goals"][0]["name"] == "New Laptop"
    assert report["goals"][0]["progress_percent"] == 20.0


async def test_savings_report_never_fabricates_a_rate_with_zero_income(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.get(
        "/api/v1/reports/savings", headers=auth_headers, params={"range": "current_month"}
    )
    report = response.json()["data"]
    assert report["savings_rate"] is None
    assert report["savings_minor"] == 0


# --- Net worth report --------------------------------------------------------------------


async def test_net_worth_report_hand_calculated(client: AsyncClient, auth_headers: dict) -> None:
    await _create_account(
        client, auth_headers, name="Bank", type="bank_account", balance_minor=1000000
    )
    await _create_account(
        client, auth_headers, name="Credit Card", type="credit_card", balance_minor=200000,
        credit_card={
            "credit_limit_minor": 500000, "statement_day": 5, "payment_due_day": 20,
        },
    )

    response = await client.get("/api/v1/reports/net-worth", headers=auth_headers)
    assert response.status_code == 200
    report = response.json()["data"]
    assert report["total_assets_minor"] == 1000000
    assert report["total_liabilities_minor"] == 200000
    assert report["net_worth_minor"] == 800000
    assert len(report["accounts"]) == 2
    credit_card_item = next(a for a in report["accounts"] if a["type"] == "credit_card")
    assert credit_card_item["is_liability"] is True
    bank_item = next(a for a in report["accounts"] if a["type"] == "bank_account")
    assert bank_item["is_liability"] is False
    assert len(report["trend"]) == 12
    # The most recent trend point (current month) must equal current net worth,
    # since nothing has happened yet this month to explain a difference.
    assert report["trend"][-1]["net_worth_minor"] == 800000


async def test_net_worth_report_trend_reconstructs_a_past_transaction_correctly(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(
        client, auth_headers, name="Bank", type="bank_account", balance_minor=1000000
    )
    # An expense two months ago reduced the balance - the trend for THIS
    # month should show a net worth that already reflects it (no special
    # correction needed, since it happened before this month started),
    # while a month even further back should show a HIGHER net worth
    # (before that expense had happened yet).
    two_months_ago = date.today().replace(day=1)
    for _ in range(2):
        two_months_ago = (two_months_ago - timedelta(days=1)).replace(day=1)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=100000,
        occurred_at=_iso(two_months_ago),
    )

    response = await client.get("/api/v1/reports/net-worth", headers=auth_headers)
    report = response.json()["data"]
    assert report["net_worth_minor"] == 900000  # 1,000,000 - 100,000 spent

    trend_by_month = {p["month"]: p["net_worth_minor"] for p in report["trend"]}
    two_months_ago_iso = two_months_ago.isoformat()
    assert trend_by_month[two_months_ago_iso] == 1000000  # before that month's own expense


async def test_net_worth_report_trend_reflects_a_transfer_between_two_asset_accounts_as_neutral(
    client: AsyncClient, auth_headers: dict
) -> None:
    """A transfer between two ordinary (non-credit-card) accounts must
    never move total net worth - one account's balance falls by exactly
    what the other's rises by, so every trend point before and after the
    transfer must be identical."""
    bank = await _create_account(
        client, auth_headers, name="Bank", type="bank_account", balance_minor=1000000
    )
    cash = await _create_account(client, auth_headers, name="Cash", type="cash", balance_minor=0)

    two_months_ago = date.today().replace(day=1)
    for _ in range(2):
        two_months_ago = (two_months_ago - timedelta(days=1)).replace(day=1)

    await _create_transaction(
        client, auth_headers, account_id=bank["id"], transfer_account_id=cash["id"],
        type="transfer", amount_minor=300000, occurred_at=_iso(two_months_ago),
    )

    response = await client.get("/api/v1/reports/net-worth", headers=auth_headers)
    report = response.json()["data"]
    assert report["net_worth_minor"] == 1000000  # unchanged: still just money moved between assets

    trend_by_month = {p["month"]: p["net_worth_minor"] for p in report["trend"]}
    assert trend_by_month[two_months_ago.isoformat()] == 1000000
    assert all(v == 1000000 for v in trend_by_month.values())


async def test_net_worth_report_trend_reflects_a_transfer_into_a_credit_card_as_real(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Paying a credit card via a transfer from a bank account is a real,
    ordinary action this app allows - and it is NOT net-worth-neutral,
    because the credit card leg changes a liability, not an asset. The
    trend must reflect the actual, larger swing (both legs move net worth
    the same direction under this app's balance convention), never
    silently treat every transfer as net-worth-neutral."""
    bank = await _create_account(
        client, auth_headers, name="Bank", type="bank_account", balance_minor=1000000
    )
    card = await _create_account(
        client, auth_headers, name="Credit Card", type="credit_card", balance_minor=100000,
        credit_card={"credit_limit_minor": 500000, "statement_day": 5, "payment_due_day": 20},
    )

    two_months_ago = date.today().replace(day=1)
    for _ in range(2):
        two_months_ago = (two_months_ago - timedelta(days=1)).replace(day=1)

    # Bank -100000 (asset falls), Credit Card +100000 (liability rises) -
    # net worth falls by 200000 total, not zero.
    await _create_transaction(
        client, auth_headers, account_id=bank["id"], transfer_account_id=card["id"],
        type="transfer", amount_minor=100000, occurred_at=_iso(two_months_ago),
    )

    response = await client.get("/api/v1/reports/net-worth", headers=auth_headers)
    report = response.json()["data"]
    # assets 900000, liabilities 200000
    assert report["net_worth_minor"] == 700000

    trend_by_month = {p["month"]: p["net_worth_minor"] for p in report["trend"]}
    # Before the transfer, net worth was 900000 (1,000,000 assets - 100,000
    # starting liability) - 200000 higher than after, never the same value
    # a "transfers are always neutral" assumption would have produced.
    assert trend_by_month[two_months_ago.isoformat()] == 900000
