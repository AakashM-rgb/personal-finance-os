"""Tests that Natural-Language Search logging (app.search.service) is safe
and useful: execution and confirmation-required events are both logged
with structured, safe metadata only - never a password, token, secret, or
raw SQL."""

import logging
import uuid
from datetime import date

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, *, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _create_account(client: AsyncClient, headers: dict) -> dict:
    response = await client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Bank", "type": "bank_account", "balance_minor": 500000, "currency": "INR"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_successful_search_is_logged_with_safe_metadata(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    headers = await _register(client, email="searchlog@example.com")
    account = await _create_account(client, headers)
    await client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 5000,
            "merchant": "Amazon",
            "occurred_at": f"{date.today().isoformat()}T12:00:00Z",
        },
    )

    with caplog.at_level(logging.INFO, logger="app.search"):
        response = await client.post(
            "/api/v1/search/financial", headers=headers, json={"query": "Amazon"}
        )
    assert response.status_code == 200

    matching = [r for r in caplog.records if r.message == "search_executed"]
    assert len(matching) == 1
    record = matching[0]
    assert record.result_count == 1
    assert record.total_matching == 1
    assert record.duration_ms >= 0
    assert uuid.UUID(record.user_id)  # a real uuid string, not garbage


async def test_confirmation_required_search_is_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    headers = await _register(client, email="searchlog-confirm@example.com")
    with caplog.at_level(logging.INFO, logger="app.search"):
        response = await client.post(
            "/api/v1/search/financial", headers=headers, json={"query": "August"}
        )
    assert response.status_code == 200

    matching = [r for r in caplog.records if r.message == "search_requires_confirmation"]
    assert len(matching) == 1


async def test_logs_never_contain_secrets_or_the_search_query_text(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    headers = await _register(client, email="searchlog-safe@example.com")
    with caplog.at_level(logging.INFO, logger="app.search"):
        await client.post(
            "/api/v1/search/financial",
            headers=headers,
            json={"query": "a very private search about my medical bills"},
        )

    for record in caplog.records:
        formatted = record.getMessage()
        assert "correcthorse123" not in formatted
        assert "password" not in formatted.lower()
        assert "bearer " not in formatted.lower()
        assert "medical" not in formatted.lower()
