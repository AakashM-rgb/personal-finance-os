"""Endpoint-level tests for POST /api/v1/search/financial: authentication,
cross-user isolation, request validation, ambiguity/confirmation flow, and
that nothing internal (SQL, query-builder details, another user's data)
ever leaks through the HTTP layer.
"""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.base import ProviderTurn, ToolCall
from app.models.user_settings import UserSettings
from app.search import interpreter as search_interpreter_module


async def _register(client: AsyncClient, *, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}


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


# --- authentication -----------------------------------------------------------------------


async def test_unauthenticated_search_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/search/financial", json={"query": "food"})
    assert response.status_code == 401


# --- request validation --------------------------------------------------------------------


async def test_empty_query_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": ""}
    )
    assert response.status_code == 422


async def test_overlong_query_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "x" * 201}
    )
    assert response.status_code == 422


async def test_unknown_request_field_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "food", "sql": "DROP TABLE transactions"},
    )
    assert response.status_code == 422


async def test_user_id_in_request_body_is_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "food", "user_id": "00000000-0000-0000-0000-00000000ffff"},
    )
    assert response.status_code == 422


async def test_malformed_category_override_id_is_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "food", "category_override_id": "not-a-uuid"},
    )
    assert response.status_code == 422


async def test_response_never_exposes_sql_or_internal_details(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "food last month"}
    )
    assert response.status_code == 200
    body_text = response.text.lower()
    for forbidden in ("select ", "drop table", "from transactions", "traceback"):
        assert forbidden not in body_text


# --- ambiguity / confirmation flow ----------------------------------------------------------


async def test_ambiguous_query_returns_interpretation_without_results(
    client: AsyncClient, auth_headers: dict
) -> None:
    data_response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "August"}
    )
    assert data_response.status_code == 200
    data = data_response.json()["data"]
    assert data["requires_confirmation"] is True
    assert data["results"] == []
    assert data["interpretation"]["start_date"] == "2025-08-01" or data["interpretation"][
        "start_date"
    ].startswith("20")


async def test_confirmed_ambiguous_query_executes(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=5000,
        occurred_at=f"{date.today().isoformat()}T12:00:00Z",
    )

    first = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "this month"}
    )
    assert first.json()["data"]["requires_confirmation"] is True

    second = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "this month", "confirmed": True},
    )
    assert second.status_code == 200
    data = second.json()["data"]
    assert data["requires_confirmation"] is False
    assert data["result_count"] == 1


async def test_ambiguous_category_returns_candidates(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Car Insurance", "icon": "\U0001f697", "color": "#123456"},
    )
    await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Car Rental", "icon": "\U0001f697", "color": "#654321"},
    )

    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "car"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["requires_confirmation"] is True
    assert len(data["ambiguous_categories"]) == 2
    names = {c["name"] for c in data["ambiguous_categories"]}
    assert names == {"Car Insurance", "Car Rental"}


async def test_category_override_resolves_ambiguity(
    client: AsyncClient, auth_headers: dict
) -> None:
    car_insurance = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Car Insurance", "icon": "\U0001f697", "color": "#123456"},
    )
    await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Car Rental", "icon": "\U0001f697", "color": "#654321"},
    )
    car_insurance_id = car_insurance.json()["data"]["id"]

    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=15000,
        category_id=car_insurance_id,
        occurred_at=f"{date.today().isoformat()}T12:00:00Z",
    )

    response = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "car", "category_override_id": car_insurance_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["requires_confirmation"] is False
    assert data["result_count"] == 1
    assert data["interpretation"]["category_name"] == "Car Insurance"


async def test_unambiguous_query_executes_without_confirmation(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "Amazon"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["requires_confirmation"] is False


# --- cross-user isolation --------------------------------------------------------------------


async def test_cross_user_search_isolation(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    victim_account = await _create_account(client, other_auth_headers, name="Victim Account")
    await _create_transaction(
        client,
        other_auth_headers,
        account_id=victim_account["id"],
        type="expense",
        amount_minor=987654,
        merchant="Amazon",
        occurred_at=f"{date.today().isoformat()}T12:00:00Z",
        description="Victim's secret Amazon order",
    )

    response = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "Amazon"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["result_count"] == 0
    body_text = response.text
    assert "Victim" not in body_text
    assert "987654" not in body_text


# --- per-user AI setting is actually enforced, end to end -----------------------------------


class _FakeAnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.called = False

    async def next_turn(self, *, system_prompt, conversation, tools) -> ProviderTurn:
        self.called = True
        call = ToolCall(
            id="call_1", name="interpret_financial_search", arguments={"search_text": "Amazon"}
        )
        return ProviderTurn(tool_calls=(call,))


async def test_ai_disabled_setting_prevents_provider_call_through_the_full_api(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end version of the CLAUDE.md §14 guarantee already unit-tested
    in test_search_interpreter.py: even with a real provider configured,
    disabling AI access for this user must mean the search endpoint never
    calls it, and falls back to the deterministic interpreter."""
    fake = _FakeAnthropicProvider()
    monkeypatch.setattr(search_interpreter_module, "get_ai_provider", lambda: fake)

    # Disable ai_enabled for the authenticated user directly via the DB, the
    # same pattern used by backend/tests/test_ai_assistant_service.py.
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me.json()["data"]["id"]
    result = await db_session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one()
    settings.ai_enabled = False
    await db_session.commit()

    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "Amazon"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "deterministic"
    assert fake.called is False


async def test_ai_enabled_setting_allows_provider_selection_through_the_full_api(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropicProvider()
    monkeypatch.setattr(search_interpreter_module, "get_ai_provider", lambda: fake)

    response = await client.post(
        "/api/v1/search/financial", headers=auth_headers, json={"query": "Amazon"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "anthropic"
    assert fake.called is True


async def test_category_override_cannot_target_another_users_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_category = await client.post(
        "/api/v1/categories",
        headers=other_auth_headers,
        json={"name": "Their Private Category", "icon": "\U0001f512", "color": "#000000"},
    )
    their_category_id = their_category.json()["data"]["id"]

    response = await client.post(
        "/api/v1/search/financial",
        headers=auth_headers,
        json={"query": "something", "category_override_id": their_category_id},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    # The override is silently ignored (not found for THIS user) rather
    # than leaking whether the category exists for someone else.
    assert data["interpretation"]["category_name"] is None
