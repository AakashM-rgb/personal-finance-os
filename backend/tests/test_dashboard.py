from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 0)
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


async def _get_dashboard(client: AsyncClient, headers: dict) -> dict:
    response = await client.get("/api/v1/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- empty state / auth -------------------------------------------------------


async def test_dashboard_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 401


async def test_dashboard_empty_state_for_brand_new_user(
    client: AsyncClient, auth_headers: dict
) -> None:
    data = await _get_dashboard(client, auth_headers)
    assert data["total_balance_minor"] == 0
    assert data["net_worth_minor"] == 0
    assert data["total_income_minor"] == 0
    assert data["total_expense_minor"] == 0
    assert data["savings_rate"] is None
    assert data["category_breakdown"] == []
    assert data["recent_transactions"] == []
    assert data["upcoming_payments"] == []
    # No real financial activity yet -> no fabricated score.
    assert data["health_score"]["score"] is None
    assert data["health_score"]["label"] is None


# --- balance / net worth -------------------------------------------------------


async def test_total_balance_excludes_credit_card_and_net_worth_subtracts_debt(
    client: AsyncClient, auth_headers: dict
) -> None:
    await _create_account(
        client, auth_headers, type="bank_account", balance_minor=500000, name="Bank"
    )
    await _create_account(
        client,
        auth_headers,
        type="credit_card",
        balance_minor=100000,
        name="Card",
        credit_card={"credit_limit_minor": 1000000, "statement_day": 1, "payment_due_day": 15},
    )

    data = await _get_dashboard(client, auth_headers)
    assert data["total_balance_minor"] == 500000  # only the cash-like account
    assert data["net_worth_minor"] == 400000  # 500000 - 100000 owed


async def test_accounts_in_a_different_currency_are_excluded_and_flagged(
    client: AsyncClient, auth_headers: dict
) -> None:
    await _create_account(
        client, auth_headers, type="bank_account", balance_minor=500000, currency="INR"
    )
    await _create_account(
        client, auth_headers, type="bank_account", balance_minor=999999, currency="USD"
    )

    data = await _get_dashboard(client, auth_headers)
    assert data["currency"] == "INR"
    assert data["total_balance_minor"] == 500000  # USD account excluded, not summed in
    assert data["excluded_other_currency_accounts"] == 1


# --- income / expense / savings ------------------------------------------------


async def test_income_expense_savings_and_savings_rate_this_month(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=100000
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=40000
    )

    data = await _get_dashboard(client, auth_headers)
    assert data["total_income_minor"] == 100000
    assert data["total_expense_minor"] == 40000
    assert data["savings_minor"] == 60000
    assert data["savings_rate"] == 60.0


async def test_transfers_are_excluded_from_income_and_expense_totals(
    client: AsyncClient, auth_headers: dict
) -> None:
    source = await _create_account(client, auth_headers, balance_minor=100000, name="Source")
    destination = await _create_account(client, auth_headers, balance_minor=0, name="Destination")
    await _create_transaction(
        client,
        auth_headers,
        account_id=source["id"],
        transfer_account_id=destination["id"],
        type="transfer",
        amount_minor=20000,
    )

    data = await _get_dashboard(client, auth_headers)
    assert data["total_income_minor"] == 0
    assert data["total_expense_minor"] == 0
    assert data["category_breakdown"] == []


# --- monthly spending comparison -----------------------------------------------


async def test_previous_month_comparison_and_percent_change(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    now = datetime.now(UTC)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_reference = this_month_start - timedelta(days=1)

    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=10000,
        occurred_at=previous_month_reference.isoformat(),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=15000
    )

    data = await _get_dashboard(client, auth_headers)
    spending = data["monthly_spending"]
    assert spending["previous_month_expense_minor"] == 10000
    assert spending["current_month_expense_minor"] == 15000
    assert spending["percent_change"] == 50.0  # (15000-10000)/10000 * 100


async def test_percent_change_is_none_when_previous_month_had_no_spending(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=5000
    )

    data = await _get_dashboard(client, auth_headers)
    assert data["monthly_spending"]["previous_month_expense_minor"] == 0
    assert data["monthly_spending"]["percent_change"] is None


async def test_daily_average_and_projection_are_internally_consistent(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=30000
    )

    data = await _get_dashboard(client, auth_headers)
    spending = data["monthly_spending"]
    assert spending["days_elapsed"] >= 1
    expected_daily_average = round(
        spending["current_month_expense_minor"] / spending["days_elapsed"]
    )
    assert spending["daily_average_minor"] == expected_daily_average
    assert (
        spending["projected_month_expense_minor"]
        == spending["daily_average_minor"] * spending["days_in_month"]
    )


# --- category breakdown --------------------------------------------------------


async def test_category_breakdown_amounts_and_percentages(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    food_id = await _get_category_id(client, auth_headers, "Food")
    transport_id = await _get_category_id(client, auth_headers, "Transport")

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=30000, category_id=food_id,
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=10000, category_id=transport_id,
    )

    data = await _get_dashboard(client, auth_headers)
    breakdown = data["category_breakdown"]
    assert len(breakdown) == 2
    assert breakdown[0]["category_id"] == food_id  # sorted descending by amount
    assert breakdown[0]["amount_minor"] == 30000
    assert breakdown[0]["percent"] == 75.0
    assert breakdown[1]["amount_minor"] == 10000
    assert breakdown[1]["percent"] == 25.0


async def test_uncategorized_expenses_are_grouped_together(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=5000
    )

    data = await _get_dashboard(client, auth_headers)
    assert len(data["category_breakdown"]) == 1
    assert data["category_breakdown"][0]["category_id"] is None
    assert data["category_breakdown"][0]["name"] == "Uncategorized"


# --- recent transactions --------------------------------------------------------


async def test_recent_transactions_are_capped_and_most_recent_first(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    for i in range(10):
        await _create_transaction(
            client, auth_headers, account_id=account["id"], type="expense", amount_minor=100 + i
        )

    data = await _get_dashboard(client, auth_headers)
    assert len(data["recent_transactions"]) == 8
    assert data["recent_transactions"][0]["amount_minor"] == 109  # created last


# --- upcoming payments ----------------------------------------------------------


async def test_upcoming_payments_come_from_real_credit_card_due_dates(
    client: AsyncClient, auth_headers: dict
) -> None:
    await _create_account(
        client,
        auth_headers,
        type="credit_card",
        balance_minor=50000,
        name="Card",
        credit_card={
            "credit_limit_minor": 500000,
            "statement_day": 1,
            "payment_due_day": 15,
            "minimum_payment_minor": 5000,
        },
    )

    data = await _get_dashboard(client, auth_headers)
    assert len(data["upcoming_payments"]) == 1
    payment = data["upcoming_payments"][0]
    assert payment["kind"] == "credit_card_due"
    assert payment["amount_minor"] == 5000
    # Must be a real, near-future date, not a placeholder.
    due_date = datetime.strptime(payment["due_date"], "%Y-%m-%d").date()
    assert due_date >= datetime.now(UTC).date()


async def test_no_upcoming_payments_without_any_credit_cards(
    client: AsyncClient, auth_headers: dict
) -> None:
    await _create_account(client, auth_headers, type="cash", balance_minor=1000)
    data = await _get_dashboard(client, auth_headers)
    assert data["upcoming_payments"] == []


# --- health score integration ---------------------------------------------------


async def test_health_score_reflects_real_activity(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers, balance_minor=0)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=100000
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=30000
    )

    data = await _get_dashboard(client, auth_headers)
    health = data["health_score"]
    assert health["score"] is not None
    assert 0 <= health["score"] <= 100
    assert health["label"] in {"Excellent", "Good", "Fair", "Needs Attention"}
    assert len(health["factors"]) == 4
    savings_factor = next(f for f in health["factors"] if f["key"] == "savings_rate")
    assert savings_factor["score"] is not None


# --- authorization / isolation ---------------------------------------------------


async def test_dashboard_is_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    my_account = await _create_account(client, auth_headers, balance_minor=100000)
    their_account = await _create_account(client, other_auth_headers, balance_minor=999999)
    await _create_transaction(
        client, auth_headers, account_id=my_account["id"], type="income", amount_minor=5000
    )
    await _create_transaction(
        client,
        other_auth_headers,
        account_id=their_account["id"],
        type="income",
        amount_minor=888888,
    )

    mine = await _get_dashboard(client, auth_headers)
    theirs = await _get_dashboard(client, other_auth_headers)

    # The income transactions above credit each account's balance via the
    # ledger (see transaction_service), so balances reflect starting amount
    # + income, not just the opening balance.
    assert mine["total_balance_minor"] == 105000
    assert mine["total_income_minor"] == 5000
    assert theirs["total_balance_minor"] == 1888887
    assert theirs["total_income_minor"] == 888888
