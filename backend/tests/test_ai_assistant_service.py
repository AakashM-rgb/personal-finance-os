"""Integration tests for app.services.ai_assistant_service.ask - the full
orchestration loop (provider -> tool validation/execution -> final answer)
running against the deterministic MockProvider (no ANTHROPIC_API_KEY is
configured in the test environment, so app.ai.provider.factory resolves to
MockProvider automatically - the same "default to mock" behavior a real
deployment gets without a configured key).
"""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings
from app.services import ai_assistant_service


async def _register(client: AsyncClient, *, email: str) -> tuple[uuid.UUID, dict]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return uuid.UUID(data["user"]["id"]), headers


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Main Bank")
    payload.setdefault("type", "bank_account")
    payload.setdefault("balance_minor", 10_000_00)
    payload.setdefault("currency", "INR")
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_transaction(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found")


# --- provider labeling / disclaimer ---------------------------------------------------------


async def test_provider_is_mock_when_no_api_key_configured(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="mocklabel@example.com")
    response = await ai_assistant_service.ask(db_session, user_id=user_id, message="hello")
    assert response.provider == "mock"


async def test_response_always_carries_a_disclaimer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="disclaimer@example.com")
    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Where am I spending the most?"
    )
    assert "not licensed financial advice" in response.disclaimer.lower()


async def test_answer_never_claims_to_be_a_licensed_advisor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="notadvisor@example.com")
    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Can I afford a ₹70,000 phone?"
    )
    lowered = response.answer.lower()
    for banned in ("guaranteed", "certain", "risk-free", "licensed financial advisor"):
        assert banned not in lowered


# --- anti-hallucination -------------------------------------------------------------------


async def test_unsupported_question_gives_explicit_insufficient_tools_message(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="unsupported@example.com")
    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="What's the weather like today?"
    )
    assert response.tools_used == []
    lowered = response.answer.lower()
    assert "can't answer" in lowered or "not able to answer" in lowered


async def test_empty_data_gives_explicit_insufficient_data_message(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="emptydata@example.com")
    # No accounts, no transactions at all for this brand-new user.
    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Where am I spending the most?"
    )
    assert "not enough data to answer that reliably" in response.answer
    assert response.tools_used[0].tool_name == "get_category_spending"
    assert response.tools_used[0].ok is True  # the tool succeeded; it just found nothing


async def test_affordability_without_amount_gives_insufficient_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="noamount@example.com")
    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Can I afford this?"
    )
    assert "not enough data to answer that reliably" in response.answer
    assert response.tools_used == []  # no tool call was even attempted


# --- ai_enabled short-circuit ---------------------------------------------------------------


async def test_ai_disabled_short_circuits_before_any_tool_call(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, _headers = await _register(client, email="disabled-service@example.com")
    result = await db_session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one()
    settings.ai_enabled = False
    await db_session.commit()

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Where am I spending the most?"
    )
    assert response.tools_used == []
    assert "disabled" in response.answer.lower() or "turned off" in response.answer.lower()


# --- supported example questions, grounded in real seeded data ------------------------------


async def test_where_am_i_spending_the_most(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, headers = await _register(client, email="topspend@example.com")
    account = await _create_account(client, headers)
    food_id = await _get_category_id(client, headers, "Food")
    today = date.today().isoformat()
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=500000,
        category_id=food_id,
        occurred_at=f"{today}T12:00:00Z",
    )

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Where am I spending the most?"
    )
    assert "Food" in response.answer
    assert "5000.00 INR" in response.answer
    assert response.tools_used[0].tool_name == "get_category_spending"


async def test_how_much_did_i_spend_on_food_this_month(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register(client, email="foodspend@example.com")
    account = await _create_account(client, headers)
    food_id = await _get_category_id(client, headers, "Food")
    transport_id = await _get_category_id(client, headers, "Transport")
    today = date.today().isoformat()
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=250000,
        category_id=food_id,
        occurred_at=f"{today}T12:00:00Z",
    )
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=90000,
        category_id=transport_id,
        occurred_at=f"{today}T13:00:00Z",
    )

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="How much did I spend on food this month?"
    )
    assert "2500.00 INR" in response.answer
    assert "900.00 INR" not in response.answer  # transport figure must not leak into this answer


async def test_compare_this_month_with_last_month(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register(client, email="comparemonth@example.com")
    account = await _create_account(client, headers)
    today = date.today().isoformat()
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=300000,
        occurred_at=f"{today}T12:00:00Z",
    )

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Compare this month with last month."
    )
    assert "3000.00 INR" in response.answer
    assert response.tools_used[0].tool_name == "compare_periods"


async def test_biggest_recurring_expenses(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, headers = await _register(client, email="bigrecurring@example.com")
    account = await _create_account(client, headers)
    today = date.today().isoformat()
    await client.post(
        "/api/v1/recurring-transactions",
        headers=headers,
        json={
            "name": "Netflix",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 64900,
            "frequency": "monthly",
            "start_date": today,
        },
    )

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="What are my biggest recurring expenses?"
    )
    assert "Netflix" in response.answer
    assert "649.00 INR" in response.answer


async def test_how_much_should_i_save_each_month_with_a_goal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register(client, email="savegoal@example.com")
    await client.post(
        "/api/v1/goals",
        headers=headers,
        json={
            "name": "Emergency Fund",
            "target_amount_minor": 1000000,
            "current_amount_minor": 0,
            "currency": "INR",
            "target_date": (date.today() + timedelta(days=100)).isoformat(),
        },
    )

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="How much should I save each month?"
    )
    assert "Emergency Fund" in response.answer
    assert "Fact:" in response.answer


async def test_can_i_afford_a_phone(client: AsyncClient, db_session: AsyncSession) -> None:
    user_id, headers = await _register(client, email="affordphone@example.com")
    await _create_account(client, headers, balance_minor=10_000_000)  # 100,000.00 INR

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Can I afford a ₹70,000 phone?"
    )
    assert "Assumptions:" in response.answer
    assert "Calculation:" in response.answer
    assert "Limitations:" in response.answer
    assert "70000.00 INR" in response.answer
    assert "30000.00 INR" in response.answer  # 100,000 - 70,000 remaining


async def test_afford_question_exceeding_balance_is_honest_about_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register(client, email="cantafford@example.com")
    await _create_account(client, headers, balance_minor=1000000)  # 10,000.00 INR

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Can I afford a ₹70,000 phone?"
    )
    assert "exceed" in response.answer.lower()


# --- tool usage metadata is safe (name + success only) --------------------------------------


async def test_tools_used_never_includes_raw_arguments_or_results(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, headers = await _register(client, email="safe-meta@example.com")
    account = await _create_account(client, headers)
    await _create_transaction(
        client,
        headers,
        account_id=account["id"],
        type="expense",
        amount_minor=999999,
        occurred_at=f"{date.today().isoformat()}T12:00:00Z",
        description="Very private purchase",
    )

    response = await ai_assistant_service.ask(
        db_session, user_id=user_id, message="Where am I spending the most?"
    )
    for usage in response.tools_used:
        dumped = usage.model_dump()
        assert set(dumped.keys()) == {"tool_name", "ok"}
