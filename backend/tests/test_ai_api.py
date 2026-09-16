"""Endpoint-level tests for POST /api/v1/ai/assistant - authentication,
input validation, response shape, and that nothing internal (tool
arguments, provider config, another user's data) leaks through the HTTP
layer.
"""

from datetime import date

from httpx import AsyncClient


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


# --- A: authentication ------------------------------------------------------------------


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/ai/assistant", json={"message": "hello"})
    assert response.status_code == 401


# --- input validation ---------------------------------------------------------------------


async def test_empty_message_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/ai/assistant", headers=auth_headers, json={"message": ""}
    )
    assert response.status_code == 422


async def test_overlong_message_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/ai/assistant", headers=auth_headers, json={"message": "x" * 2001}
    )
    assert response.status_code == 422


async def test_overlong_history_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    history = [{"role": "user", "content": "hi"} for _ in range(21)]
    response = await client.post(
        "/api/v1/ai/assistant",
        headers=auth_headers,
        json={"message": "hello", "history": history},
    )
    assert response.status_code == 422


async def test_invalid_history_role_is_rejected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/ai/assistant",
        headers=auth_headers,
        json={"message": "hello", "history": [{"role": "system", "content": "x"}]},
    )
    assert response.status_code == 422


async def test_unknown_field_in_request_body_is_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/ai/assistant",
        headers=auth_headers,
        json={"message": "hello", "user_id": "00000000-0000-0000-0000-00000000ffff"},
    )
    assert response.status_code == 422


# --- successful round trip / response shape -----------------------------------------------


async def test_successful_response_shape(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/ai/assistant",
        headers=auth_headers,
        json={"message": "Where am I spending the most?"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data.keys()) == {"answer", "tools_used", "provider", "disclaimer"}
    assert isinstance(data["answer"], str) and data["answer"]
    assert data["provider"] == "mock"
    for usage in data["tools_used"]:
        assert set(usage.keys()) == {"tool_name", "ok"}


async def test_response_never_exposes_internal_configuration(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/ai/assistant", headers=auth_headers, json={"message": "hello there"}
    )
    assert response.status_code == 200
    body_text = response.text.lower()
    for forbidden in ("api_key", "anthropic_api_key", "secret", "password"):
        assert forbidden not in body_text


# --- cross-user isolation through the HTTP layer -------------------------------------------


async def test_endpoint_never_leaks_another_users_data(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    victim_account = await _create_account(client, other_auth_headers, name="Victim Account")
    await _create_transaction(
        client,
        other_auth_headers,
        account_id=victim_account["id"],
        type="expense",
        amount_minor=123456,
        occurred_at=f"{date.today().isoformat()}T12:00:00Z",
        description="Victim's private purchase",
    )

    response = await client.post(
        "/api/v1/ai/assistant",
        headers=auth_headers,
        json={"message": "Where am I spending the most?"},
    )
    assert response.status_code == 200
    answer = response.json()["data"]["answer"]
    assert "Victim" not in answer
    assert "1234.56" not in answer
    assert "not enough data" in answer.lower()
