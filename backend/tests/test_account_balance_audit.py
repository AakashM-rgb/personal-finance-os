"""A balance set through PUT /accounts bypasses the ledger, so every actual
change must leave an `account.balance_updated` audit row (previous and new
value). Ledger writes and no-op edits must not."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

ACTION = "account.balance_updated"


async def _create_card(client: AsyncClient, headers: dict, *, owed: int) -> dict:
    response = await client.post(
        "/api/v1/accounts",
        headers=headers,
        json={
            "name": "Card",
            "type": "credit_card",
            "balance_minor": owed,
            "credit_card": {
                "credit_limit_minor": 1_000_000,
                "statement_day": 5,
                "payment_due_day": 25,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _put(client: AsyncClient, headers: dict, account_id: str, **payload) -> int:
    response = await client.put(f"/api/v1/accounts/{account_id}", headers=headers, json=payload)
    return response.status_code


async def _entries(db: AsyncSession, account_id: str) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.action == ACTION, AuditLog.entity_id == account_id)
        .order_by(AuditLog.created_at)
    )
    return list(result.scalars().all())


async def test_balance_change_is_audit_logged_with_previous_and_new_value(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    card = await _create_card(client, auth_headers, owed=50_000)

    assert await _put(client, auth_headers, card["id"], balance_minor=42_000) == 200

    entries = await _entries(db_session, card["id"])
    assert len(entries) == 1
    entry = entries[0]
    owner = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()["data"]
    assert entry.entity_type == "account"
    assert str(entry.user_id) == owner["id"]
    assert entry.metadata_json == {
        "account_type": "credit_card",
        "previous_balance_minor": 50_000,
        "new_balance_minor": 42_000,
    }
    assert entry.user_agent is not None


async def test_each_change_gets_its_own_entry(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    card = await _create_card(client, auth_headers, owed=0)

    await _put(client, auth_headers, card["id"], balance_minor=1_000)
    await _put(client, auth_headers, card["id"], balance_minor=-500)

    entries = await _entries(db_session, card["id"])
    assert [(e.metadata_json or {})["previous_balance_minor"] for e in entries] == [0, 1_000]
    assert [(e.metadata_json or {})["new_balance_minor"] for e in entries] == [1_000, -500]


async def test_unchanged_balance_or_other_fields_are_not_logged(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    card = await _create_card(client, auth_headers, owed=50_000)

    assert await _put(client, auth_headers, card["id"], balance_minor=50_000) == 200
    assert await _put(client, auth_headers, card["id"], name="Renamed") == 200

    assert await _entries(db_session, card["id"]) == []


async def test_ledger_writes_are_not_logged_as_manual_balance_changes(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    card = await _create_card(client, auth_headers, owed=0)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={"account_id": card["id"], "type": "expense", "amount_minor": 5_000},
    )
    assert response.status_code == 201, response.text

    assert await _entries(db_session, card["id"]) == []


async def test_bank_account_balance_change_is_logged_too(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Bank", "type": "bank_account", "balance_minor": 100_000},
    )
    bank = response.json()["data"]

    await _put(client, auth_headers, bank["id"], balance_minor=90_000)

    entries = await _entries(db_session, bank["id"])
    assert len(entries) == 1
    assert (entries[0].metadata_json or {})["account_type"] == "bank_account"


async def test_rejected_cross_user_edit_changes_nothing_and_logs_nothing(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict, db_session: AsyncSession
) -> None:
    card = await _create_card(client, auth_headers, owed=50_000)

    assert await _put(client, other_auth_headers, card["id"], balance_minor=0) == 404

    owner_view = await client.get(f"/api/v1/accounts/{card['id']}", headers=auth_headers)
    assert owner_view.json()["data"]["balance_minor"] == 50_000
    assert await _entries(db_session, card["id"]) == []
