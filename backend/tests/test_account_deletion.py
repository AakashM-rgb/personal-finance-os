"""POST /auth/delete-account: a user can permanently delete their account and
everything they own (CLAUDE.md §12: fully scoped to the requesting user, with
complete cascade).

The completeness check is driven by the live schema: every table with a
`user_id` column is counted, so a user-owned table added later is covered
without touching this file."""

import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.services import receipt_service
from app.storage.base import StorageError
from app.storage.factory import get_storage_provider
from tests.conftest import test_engine
from tests.test_receipts import _upload_pdf

PASSWORD = "correcthorse123"
DELETE = "/api/v1/auth/delete-account"


async def _register(client: AsyncClient, email: str) -> tuple[uuid.UUID, dict, dict]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Test User"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return uuid.UUID(data["user"]["id"]), headers, dict(response.cookies)


async def _populate(client: AsyncClient, headers: dict) -> None:
    """One of nearly everything a user can own."""

    async def post(path: str, payload: dict) -> dict:
        response = await client.post(f"/api/v1/{path}", headers=headers, json=payload)
        assert response.status_code == 201, (path, response.text)
        return response.json()["data"]

    bank = await post(
        "accounts", {"name": "Bank", "type": "bank_account", "balance_minor": 50_000_00}
    )
    card = await post(
        "accounts",
        {
            "name": "Card",
            "type": "credit_card",
            "balance_minor": 0,
            "credit_card": {
                "credit_limit_minor": 1_00_000_00,
                "statement_day": 5,
                "payment_due_day": 25,
            },
        },
    )
    categories = (await client.get("/api/v1/categories", headers=headers)).json()["data"]
    food = next(c["id"] for c in categories if c["name"] == "Food")
    await post(
        "transactions",
        {
            "account_id": card["id"],
            "type": "expense",
            "amount_minor": 1_250_00,
            "category_id": food,
            "merchant": "Swiggy",
        },
    )
    await post(
        "transactions",
        {
            "account_id": bank["id"],
            "type": "transfer",
            "transfer_account_id": card["id"],
            "amount_minor": 1_000_00,
        },
    )
    await post("categories", {"name": "Hobbies", "icon": "🎨", "color": "#888888"})
    await post("budgets", {"category_id": food, "amount_minor": 8_000_00})
    await post(
        "goals",
        {"name": "Emergency Fund", "target_amount_minor": 1_00_000_00, "target_date": "2027-12-31"},
    )
    await post(
        "subscriptions",
        {
            "name": "Netflix",
            "amount_minor": 649_00,
            "frequency": "monthly",
            "account_id": bank["id"],
            "start_date": "2026-01-01",
        },
    )
    await _upload_pdf(client, headers)
    await client.get("/api/v1/notifications", headers=headers)  # generates any due ones


async def _rows_owned_by(user_id: uuid.UUID) -> dict[str, int]:
    async with test_engine.connect() as conn:
        tables = (
            (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND column_name = 'user_id' ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        counts = {}
        for table in tables:
            counts[table] = (
                await conn.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE user_id = :u'), {"u": user_id}
                )
            ).scalar_one()
        counts["users"] = (
            await conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": user_id})
        ).scalar_one()
        return counts


async def test_deleting_an_account_removes_every_row_it_owns(client: AsyncClient) -> None:
    user_id, headers, _ = await _register(client, "leaving@example.com")
    other_id, other_headers, _ = await _register(client, "staying@example.com")
    await _populate(client, headers)
    await _populate(client, other_headers)
    other_before = await _rows_owned_by(other_id)

    response = await client.post(DELETE, headers=headers, json={"password": PASSWORD})

    assert response.status_code == 200, response.text
    remaining = await _rows_owned_by(user_id)
    # audit_logs rows survive with user_id SET NULL, so they count as 0 here too.
    assert {table: n for table, n in remaining.items() if n} == {}
    assert await _rows_owned_by(other_id) == other_before, "another user's data was touched"


async def test_the_audit_trail_keeps_actions_but_loses_personal_data(client: AsyncClient) -> None:
    user_id, headers, _ = await _register(client, "audited@example.com")
    await client.post(DELETE, headers=headers, json={"password": "wrong-password"})

    await client.post(DELETE, headers=headers, json={"password": PASSWORD})

    async with test_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT action, user_id, ip_address, user_agent, metadata_json "
                    "FROM audit_logs WHERE entity_id = :u ORDER BY created_at"
                ),
                {"u": str(user_id)},
            )
        ).all()
    actions = [row.action for row in rows]
    assert "user.register" in actions
    assert "user.account_deletion_failed" in actions
    assert actions[-1] == "user.account_deleted"
    for row in rows:
        assert row.user_id is None
        assert (row.ip_address, row.user_agent, row.metadata_json) == (None, None, None), row.action


async def test_a_wrong_password_deletes_nothing(client: AsyncClient) -> None:
    user_id, headers, _ = await _register(client, "careful@example.com")
    await _populate(client, headers)
    before = await _rows_owned_by(user_id)

    response = await client.post(DELETE, headers=headers, json={"password": "not-my-password"})

    assert response.status_code == 422
    assert response.json()["error"]["field_errors"] == {"password": "incorrect"}
    after = await _rows_owned_by(user_id)
    assert after["audit_logs"] == before["audit_logs"] + 1  # the failed attempt is recorded
    assert {t: n for t, n in after.items() if t != "audit_logs"} == {
        t: n for t, n in before.items() if t != "audit_logs"
    }
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200


async def test_the_deleted_user_is_signed_out_everywhere(client: AsyncClient) -> None:
    _, headers, cookies = await _register(client, "gone@example.com")

    response = await client.post(DELETE, headers=headers, json={"password": PASSWORD})

    assert response.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    client.cookies.set("refresh_token", cookies["refresh_token"])
    refreshed = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": cookies["csrf_token"]}
    )
    assert refreshed.status_code == 401
    set_cookie = response.headers.get_list("set-cookie")
    assert any(h.startswith("refresh_token=") and "Max-Age=0" in h for h in set_cookie)


async def test_receipt_files_are_removed_from_storage(client: AsyncClient) -> None:
    user_id, headers, _ = await _register(client, "receipts@example.com")
    await _upload_pdf(client, headers)
    async with test_engine.connect() as conn:
        key = (
            await conn.execute(
                text("SELECT storage_key FROM receipts WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar_one()
    storage = get_storage_provider()
    assert await storage.read(key)

    await client.post(DELETE, headers=headers, json={"password": PASSWORD})

    with pytest.raises(StorageError):
        await storage.read(key)


async def test_the_email_can_register_again_afterwards(client: AsyncClient) -> None:
    _, headers, _ = await _register(client, "comeback@example.com")
    await client.post(DELETE, headers=headers, json={"password": PASSWORD})

    await _register(client, "comeback@example.com")


async def test_deletion_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(DELETE, json={"password": PASSWORD})
    assert response.status_code == 401


async def test_a_token_for_one_user_can_only_delete_that_user(client: AsyncClient) -> None:
    """There is no target id in the request at all: the account deleted is
    always the authenticated caller's."""
    _, headers, _ = await _register(client, "self@example.com")
    other_id, _, _ = await _register(client, "victim@example.com")

    response = await client.post(
        DELETE, headers=headers, json={"password": PASSWORD, "user_id": str(other_id)}
    )

    assert response.status_code == 422  # extra fields are refused outright
    assert (await _rows_owned_by(other_id))["users"] == 1


async def test_a_file_that_cannot_be_deleted_is_reported_with_its_prefix(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The rows are already committed, so a storage failure can't undo the
    deletion; it must leave enough in the log to clean up by hand, and not
    stop the other files from being removed."""
    user_id, headers, _ = await _register(client, "stuckfile@example.com")
    await _upload_pdf(client, headers)
    await _upload_pdf(client, headers)
    storage = get_storage_provider()
    real_delete = storage.delete
    calls: list[str] = []

    async def flaky_delete(key: str) -> None:
        calls.append(key)
        if len(calls) == 1:
            raise StorageError("disk unavailable")
        await real_delete(key)

    monkeypatch.setattr(storage, "delete", flaky_delete)
    monkeypatch.setattr(receipt_service, "get_storage_provider", lambda: storage)

    with caplog.at_level(logging.WARNING, logger="app.services.receipt_service"):
        response = await client.post(DELETE, headers=headers, json={"password": PASSWORD})

    assert response.status_code == 200, "a storage failure must not undo the deletion"
    assert len(calls) == 2, "the second file is still attempted"
    assert (await _rows_owned_by(user_id))["users"] == 0
    message = " ".join(r.getMessage() for r in caplog.records)
    assert "1 of 2 receipt file(s)" in message
    assert f"'{user_id}/'" in message
    with pytest.raises(StorageError):
        await storage.read(calls[1])


async def test_a_throttled_deletion_says_why_in_its_own_words(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-account throttle, not the per-IP limiter in front of it (which
    is switched off here so the account-level message is what's reached)."""
    monkeypatch.setattr(limiter, "enabled", False)
    _, headers, _ = await _register(client, "throttled@example.com")
    for _ in range(get_settings().login_account_max_failures + 1):
        response = await client.post(DELETE, headers=headers, json={"password": "wrong-password"})
        if response.status_code == 429:
            break

    assert response.status_code == 429
    message = response.json()["error"]["message"]
    assert "confirm your password" in message
    assert "password change" not in message
