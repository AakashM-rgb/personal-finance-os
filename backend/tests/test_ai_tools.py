"""Tests for the AI tool layer: app.ai.tools.registry.validate_and_execute is
the single choke point every AI tool call goes through, so these tests call
it directly (never a provider) with real, seeded data - covering tool
correctness, authorization/cross-user isolation, and the security
validation rules (allowlist, argument validation, identity-override
rejection, bounded result limits).
"""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.registry import validate_and_execute
from app.models.user_settings import UserSettings

# --- shared helpers ------------------------------------------------------------------------


async def _register(client: AsyncClient, *, email: str, full_name: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": full_name},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _register_with_headers(client: AsyncClient, *, email: str) -> tuple[str, dict]:
    data = await _register(client, email=email, full_name="Test User")
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return user_id, headers


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


async def _create_budget(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/budgets", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_goal(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("currency", "INR")
    response = await client.post("/api/v1/goals", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_recurring(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/recurring-transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _call(db_session: AsyncSession, *, user_id: str, tool_name: str, arguments: dict):
    return await validate_and_execute(
        db_session,
        user_id=uuid.UUID(user_id),
        ai_enabled=True,
        tool_name=tool_name,
        raw_arguments=arguments,
    )


# --- A: tool allowlist ---------------------------------------------------------------------


async def test_unknown_tool_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, _headers = await _register_with_headers(client, email="allowlist@example.com")
    result = await _call(db_session, user_id=user_id, tool_name="drop_table_users", arguments={})
    assert result.ok is False
    assert result.error_code == "unknown_tool"


async def test_arbitrary_function_name_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="arbitrary@example.com")
    result = await _call(
        db_session, user_id=user_id, tool_name="execute_sql", arguments={"query": "SELECT 1"}
    )
    assert result.ok is False
    assert result.error_code == "unknown_tool"


async def test_all_eight_tools_are_allowlisted() -> None:
    from app.ai.tools.catalog import TOOL_NAMES

    assert {
        "get_monthly_spending",
        "get_category_spending",
        "get_transactions",
        "get_budget_status",
        "get_savings_goals",
        "get_recurring_expenses",
        "get_account_balances",
        "compare_periods",
    } == TOOL_NAMES
    assert len(TOOL_NAMES) == 8


# --- D: identity-override / argument validation --------------------------------------------


async def test_identity_override_attempt_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="override@example.com")
    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="get_transactions",
        arguments={"user_id": "00000000-0000-0000-0000-00000000ffff"},
    )
    assert result.ok is False
    assert result.error_code == "identity_override_attempt"


async def test_malformed_arguments_are_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="malformed@example.com")
    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="get_transactions",
        arguments={"limit": "not-a-number"},
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_unknown_extra_argument_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="extra-arg@example.com")
    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="get_monthly_spending",
        arguments={"period": "current_month", "sql": "DROP TABLE transactions"},
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_excessive_transaction_limit_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="limit@example.com")
    result = await _call(
        db_session, user_id=user_id, tool_name="get_transactions", arguments={"limit": 5000}
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_zero_limit_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, _headers = await _register_with_headers(client, email="zerolimit@example.com")
    result = await _call(
        db_session, user_id=user_id, tool_name="get_transactions", arguments={"limit": 0}
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_invalid_period_string_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="badperiod@example.com")
    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="get_monthly_spending",
        arguments={"period": "not-a-real-period"},
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_invalid_transaction_type_enum_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="badtype@example.com")
    result = await _call(
        db_session, user_id=user_id, tool_name="get_transactions", arguments={"type": "not_a_type"}
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_backwards_date_range_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="backwards@example.com")
    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="get_transactions",
        arguments={"date_from": "2026-03-01", "date_to": "2026-01-01"},
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


async def test_ai_disabled_setting_rejects_every_tool_call(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Registration already creates a UserSettings row with ai_enabled=True
    # by default (see app.repositories.user_repository) - disable it here.
    user_id, _headers = await _register_with_headers(client, email="disabled@example.com")
    settings_result = await db_session.execute(
        select(UserSettings).where(UserSettings.user_id == uuid.UUID(user_id))
    )
    settings = settings_result.scalar_one()
    settings.ai_enabled = False
    await db_session.commit()

    result = await validate_and_execute(
        db_session,
        user_id=uuid.UUID(user_id),
        ai_enabled=False,
        tool_name="get_account_balances",
        raw_arguments={},
    )
    assert result.ok is False
    assert result.error_code == "ai_disabled"


# --- C: tool correctness with real seeded data ---------------------------------------------


async def test_get_monthly_spending_matches_real_transactions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="monthly@example.com")
    account = await _create_account(client, headers)
    food_id = await _get_category_id(client, headers, "Food")
    today = date.today().isoformat()

    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="income",
        amount_minor=500000,
        occurred_at=f"{today}T09:00:00Z",
        description="Salary",
    )
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=120000,
        category_id=food_id,
        occurred_at=f"{today}T12:00:00Z",
        description="Groceries",
    )
    # A transfer must never count as income or expense.
    other_account = await _create_account(client, headers, name="Savings")
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="transfer",
        transfer_account_id=other_account["id"],
        amount_minor=50000,
        occurred_at=f"{today}T13:00:00Z",
    )

    result = await _call(
        db_session, user_id=user_id, tool_name="get_monthly_spending", arguments={}
    )
    assert result.ok is True
    assert result.data["total_income_minor"] == 500000
    assert result.data["total_expense_minor"] == 120000
    assert result.data["net_minor"] == 380000
    assert result.data["currency"] == "INR"


async def test_get_category_spending_ranks_and_labels_uncategorized(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="category@example.com")
    account = await _create_account(client, headers)
    food_id = await _get_category_id(client, headers, "Food")
    today = date.today().isoformat()

    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=300000,
        category_id=food_id,
        occurred_at=f"{today}T12:00:00Z",
    )
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=100000,
        occurred_at=f"{today}T13:00:00Z",
        description="No category",
    )

    result = await _call(
        db_session, user_id=user_id, tool_name="get_category_spending", arguments={}
    )
    assert result.ok is True
    categories = result.data["categories"]
    assert categories[0]["name"] == "Food"
    assert categories[0]["amount_minor"] == 300000
    names = {c["name"] for c in categories}
    assert "Uncategorized" in names
    assert result.data["total_expense_minor"] == 400000


async def test_get_transactions_returns_only_own_transactions_bounded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="txnlist@example.com")
    account = await _create_account(client, headers)
    today = date.today().isoformat()
    for i in range(3):
        await _create_transaction(
            client,
            headers,
            account_id=account["id"],
            type="expense",
            amount_minor=1000 + i,
            occurred_at=f"{today}T1{i}:00:00Z",
            description=f"txn {i}",
        )

    result = await _call(db_session, user_id=user_id, tool_name="get_transactions", arguments={})
    assert result.ok is True
    assert result.data["total_matching"] == 3
    assert result.data["returned_count"] == 3
    assert result.data["limit"] == 20


async def test_get_transactions_respects_requested_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="txnlimit@example.com")
    account = await _create_account(client, headers)
    today = date.today().isoformat()
    for i in range(5):
        await _create_transaction(
            client,
            headers,
            account_id=account["id"],
            type="expense",
            amount_minor=1000 + i,
            occurred_at=f"{today}T0{i+1}:00:00Z",
        )

    result = await _call(
        db_session, user_id=user_id, tool_name="get_transactions", arguments={"limit": 2}
    )
    assert result.ok is True
    assert result.data["total_matching"] == 5
    assert result.data["returned_count"] == 2


async def test_get_budget_status_reuses_real_budget_calculations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="budget@example.com")
    account = await _create_account(client, headers)
    food_id = await _get_category_id(client, headers, "Food")
    await _create_budget(client, headers, category_id=food_id, amount_minor=500000)
    today = date.today().isoformat()
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=200000,
        category_id=food_id,
        occurred_at=f"{today}T12:00:00Z",
    )

    result = await _call(db_session, user_id=user_id, tool_name="get_budget_status", arguments={})
    assert result.ok is True
    items = result.data["items"]
    assert len(items) == 1
    assert items[0]["category_name"] == "Food"
    assert items[0]["amount_minor"] == 500000
    assert items[0]["spent_minor"] == 200000
    assert items[0]["percent_used"] == 40.0


async def test_get_savings_goals_reuses_real_progress_calculations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="goals@example.com")
    target_date = (date.today() + timedelta(days=100)).isoformat()
    await _create_goal(
        client,
        headers,
        name="Emergency Fund",
        target_amount_minor=1000000,
        current_amount_minor=250000,
        target_date=target_date,
    )

    result = await _call(db_session, user_id=user_id, tool_name="get_savings_goals", arguments={})
    assert result.ok is True
    goals = result.data["goals"]
    assert len(goals) == 1
    assert goals[0]["name"] == "Emergency Fund"
    assert goals[0]["progress_percent"] == 25.0
    assert goals[0]["remaining_minor"] == 750000
    assert goals[0]["required_monthly_savings_minor"] is not None


async def test_get_recurring_expenses_distinguishes_scheduled_from_actual(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="recurring@example.com")
    account = await _create_account(client, headers)
    start = date.today().isoformat()
    await _create_recurring(
        client,
        headers,
        name="Netflix",
        account_id=account["id"],
        type="expense",
        amount_minor=64900,
        frequency="monthly",
        start_date=start,
    )
    # No generation run yet - actual_paid_minor must be 0, never assumed.
    result = await _call(
        db_session, user_id=user_id, tool_name="get_recurring_expenses", arguments={}
    )
    assert result.ok is True
    items = result.data["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Netflix"
    assert items[0]["scheduled_monthly_cost_minor"] == 64900
    assert items[0]["actual_paid_minor"] == 0


async def test_get_account_balances_computes_real_net_worth(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="balances@example.com")
    await _create_account(client, headers, name="Bank", type="bank_account", balance_minor=500000)
    await _create_account(
        client,
        headers,
        name="Card",
        type="credit_card",
        balance_minor=100000,
        credit_card={
            "credit_limit_minor": 300000,
            "statement_day": 1,
            "payment_due_day": 20,
            "minimum_payment_minor": 10000,
        },
    )

    result = await _call(
        db_session, user_id=user_id, tool_name="get_account_balances", arguments={}
    )
    assert result.ok is True
    assert result.data["total_assets_minor"] == 500000
    assert result.data["total_liabilities_minor"] == 100000
    assert result.data["net_worth_minor"] == 400000
    assert len(result.data["accounts"]) == 2


async def test_compare_periods_current_vs_previous_month_default(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="compare@example.com")
    account = await _create_account(client, headers)
    today = date.today().isoformat()
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=100000,
        occurred_at=f"{today}T12:00:00Z",
    )

    result = await _call(db_session, user_id=user_id, tool_name="compare_periods", arguments={})
    assert result.ok is True
    assert result.data["period_a"]["total_expense_minor"] == 100000
    assert result.data["period_b"]["total_expense_minor"] == 0
    # Percent change is undefined (not fabricated) when the baseline is zero.
    assert result.data["expense_percent_change"] is None
    assert result.data["expense_diff_minor"] == 100000


async def test_compare_periods_explicit_months(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="compare-explicit@example.com")
    account = await _create_account(client, headers)
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=200000,
        occurred_at="2026-01-15T12:00:00Z",
    )
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=100000,
        occurred_at="2025-12-15T12:00:00Z",
    )

    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="compare_periods",
        arguments={"period_a": "2026-01", "period_b": "2025-12"},
    )
    assert result.ok is True
    assert result.data["period_a"]["total_expense_minor"] == 200000
    assert result.data["period_b"]["total_expense_minor"] == 100000
    assert result.data["expense_diff_minor"] == 100000
    assert result.data["expense_percent_change"] == 100.0


async def test_compare_periods_explicit_date_ranges(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register_with_headers(client, email="compare-range@example.com")
    account = await _create_account(client, headers)
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=150000,
        occurred_at="2026-02-10T12:00:00Z",
    )

    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="compare_periods",
        arguments={
            "date_from_a": "2026-02-01",
            "date_to_a": "2026-02-28",
            "date_from_b": "2026-01-01",
            "date_to_b": "2026-01-31",
        },
    )
    assert result.ok is True
    assert result.data["period_a"]["total_expense_minor"] == 150000
    assert result.data["period_b"]["total_expense_minor"] == 0


async def test_compare_periods_rejects_half_specified_custom_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register_with_headers(client, email="compare-bad@example.com")
    result = await _call(
        db_session,
        user_id=user_id,
        tool_name="compare_periods",
        arguments={"date_from_a": "2026-02-01"},
    )
    assert result.ok is False
    assert result.error_code == "invalid_arguments"


# --- B: cross-user authorization / data isolation -------------------------------------------


async def _seed_full_profile(client: AsyncClient, headers: dict) -> None:
    account = await _create_account(client, headers, name="Their Account")
    food_id = await _get_category_id(client, headers, "Food")
    today = date.today().isoformat()
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=999999,
        category_id=food_id,
        occurred_at=f"{today}T12:00:00Z",
        description="Their secret purchase",
    )
    await _create_budget(client, headers, category_id=food_id, amount_minor=500000)
    await _create_goal(
        client,
        headers,
        name="Their Goal",
        target_amount_minor=1000000,
        current_amount_minor=100000,
        target_date=(date.today() + timedelta(days=60)).isoformat(),
    )
    await _create_recurring(
        client,
        headers,
        name="Their Subscription",
        account_id=account["id"],
        type="expense",
        amount_minor=99900,
        frequency="monthly",
        start_date=today,
    )


async def test_cross_user_isolation_for_every_tool(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _their_id, their_headers = await _register_with_headers(client, email="victim@example.com")
    my_id, my_headers = await _register_with_headers(client, email="attacker@example.com")

    await _seed_full_profile(client, their_headers)
    # The attacker has no data of their own at all.

    tool_names = [
        "get_monthly_spending",
        "get_category_spending",
        "get_transactions",
        "get_budget_status",
        "get_savings_goals",
        "get_recurring_expenses",
        "get_account_balances",
        "compare_periods",
    ]
    for tool_name in tool_names:
        result = await _call(db_session, user_id=my_id, tool_name=tool_name, arguments={})
        assert result.ok is True, f"{tool_name} should still succeed with empty data"
        payload_text = str(result.data)
        assert "Their" not in payload_text
        assert "999999" not in payload_text
        assert "secret" not in payload_text.lower()

    # And the attacker's own transaction list must be empty, not the victim's.
    txn_result = await _call(db_session, user_id=my_id, tool_name="get_transactions", arguments={})
    assert txn_result.data["total_matching"] == 0

    # Sanity: the victim's own call DOES see their data (proves isolation is
    # about ownership, not that the tool is broken for everyone).
    their_result = await _call(
        db_session, user_id=_their_id, tool_name="get_transactions", arguments={}
    )
    assert their_result.data["total_matching"] == 1
