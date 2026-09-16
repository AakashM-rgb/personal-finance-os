"""Tests that AI tool-call logging (app.ai.tools.registry) is safe and
useful: accepted and rejected calls are both logged with structured, safe
metadata only - never a password, token, secret, or the tool's actual
financial payload."""

import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.registry import validate_and_execute


async def _register(client: AsyncClient, *, email: str) -> tuple[uuid.UUID, dict]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return uuid.UUID(data["user"]["id"]), headers


async def test_successful_call_is_logged_with_safe_metadata(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    user_id, _headers = await _register(client, email="logsuccess@example.com")
    with caplog.at_level(logging.INFO, logger="app.ai.tools"):
        result = await validate_and_execute(
            db_session,
            user_id=user_id,
            ai_enabled=True,
            tool_name="get_account_balances",
            raw_arguments={},
        )
    assert result.ok is True

    matching = [r for r in caplog.records if r.message == "ai_tool_call_succeeded"]
    assert len(matching) == 1
    record = matching[0]
    assert record.tool_name == "get_account_balances"
    assert record.user_id == str(user_id)
    assert record.duration_ms >= 0


async def test_rejected_call_is_logged_with_error_code(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    user_id, _headers = await _register(client, email="logreject@example.com")
    with caplog.at_level(logging.INFO, logger="app.ai.tools"):
        result = await validate_and_execute(
            db_session,
            user_id=user_id,
            ai_enabled=True,
            tool_name="not_a_real_tool",
            raw_arguments={},
        )
    assert result.ok is False

    matching = [r for r in caplog.records if r.message == "ai_tool_call_rejected"]
    assert len(matching) == 1
    record = matching[0]
    assert record.tool_name == "not_a_real_tool"
    assert record.error_code == "unknown_tool"


async def test_logs_never_contain_secrets_or_raw_financial_figures(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    user_id, headers = await _register(client, email="logsafe@example.com")
    account_response = await client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Bank", "type": "bank_account", "balance_minor": 12345678, "currency": "INR"},
    )
    assert account_response.status_code == 201, account_response.text

    with caplog.at_level(logging.INFO, logger="app.ai.tools"):
        await validate_and_execute(
            db_session,
            user_id=user_id,
            ai_enabled=True,
            tool_name="get_account_balances",
            raw_arguments={},
        )

    for record in caplog.records:
        formatted = record.getMessage()
        assert "12345678" not in formatted
        assert "correcthorse123" not in formatted
        assert "password" not in formatted.lower()
        assert "bearer " not in formatted.lower()
