import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import TransactionType
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import TransactionCreate
from app.services import transaction_service


async def _create_account(
    client: AsyncClient, headers: dict, *, type: str = "cash", balance_minor: int = 0, **overrides
) -> dict:
    payload = {
        "name": overrides.pop("name", "Test Account"),
        "type": type,
        "balance_minor": balance_minor,
    }
    payload.update(overrides)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_account(client: AsyncClient, headers: dict, account_id: str) -> dict:
    response = await client.get(f"/api/v1/accounts/{account_id}", headers=headers)
    assert response.status_code == 200, response.text
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


# --- balance ledger correctness -------------------------------------------------


async def test_create_expense_debits_account_balance(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=3000
    )
    updated = await _get_account(client, auth_headers, account["id"])
    assert updated["balance_minor"] == 7000


async def test_create_income_credits_account_balance(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="income", amount_minor=2500
    )
    updated = await _get_account(client, auth_headers, account["id"])
    assert updated["balance_minor"] == 12500


async def test_transfer_moves_money_between_accounts(
    client: AsyncClient, auth_headers: dict
) -> None:
    source = await _create_account(client, auth_headers, balance_minor=10000, name="Source")
    destination = await _create_account(
        client, auth_headers, balance_minor=1000, name="Destination"
    )

    await _create_transaction(
        client,
        auth_headers,
        account_id=source["id"],
        transfer_account_id=destination["id"],
        type="transfer",
        amount_minor=4000,
    )

    source_after = await _get_account(client, auth_headers, source["id"])
    destination_after = await _get_account(client, auth_headers, destination["id"])
    assert source_after["balance_minor"] == 6000
    assert destination_after["balance_minor"] == 5000


async def test_transfer_excluded_from_income_and_expense_filters(
    client: AsyncClient, auth_headers: dict
) -> None:
    source = await _create_account(client, auth_headers, balance_minor=10000, name="Source")
    destination = await _create_account(client, auth_headers, balance_minor=0, name="Destination")
    await _create_transaction(
        client,
        auth_headers,
        account_id=source["id"],
        transfer_account_id=destination["id"],
        type="transfer",
        amount_minor=4000,
    )
    await _create_transaction(
        client, auth_headers, account_id=source["id"], type="expense", amount_minor=500
    )

    expense_response = await client.get(
        "/api/v1/transactions", params={"type": "expense"}, headers=auth_headers
    )
    income_response = await client.get(
        "/api/v1/transactions", params={"type": "income"}, headers=auth_headers
    )
    transfer_response = await client.get(
        "/api/v1/transactions", params={"type": "transfer"}, headers=auth_headers
    )

    assert [t["type"] for t in expense_response.json()["data"]] == ["expense"]
    assert income_response.json()["data"] == []
    assert [t["type"] for t in transfer_response.json()["data"]] == ["transfer"]


async def test_update_transaction_reverses_old_effect_before_applying_new(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000)
    transaction = await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=2000
    )
    after_create = await _get_account(client, auth_headers, account["id"])
    assert after_create["balance_minor"] == 8000

    response = await client.put(
        f"/api/v1/transactions/{transaction['id']}",
        headers=auth_headers,
        json={"amount_minor": 5000},
    )
    assert response.status_code == 200, response.text

    after_update = await _get_account(client, auth_headers, account["id"])
    # Reverse the original 2000 expense (+2000) then apply the new 5000 expense (-5000):
    # 8000 + 2000 - 5000 == 5000
    assert after_update["balance_minor"] == 5000


async def test_update_transaction_moving_accounts_adjusts_both_balances(
    client: AsyncClient, auth_headers: dict
) -> None:
    account_a = await _create_account(client, auth_headers, balance_minor=10000, name="A")
    account_b = await _create_account(client, auth_headers, balance_minor=10000, name="B")
    transaction = await _create_transaction(
        client, auth_headers, account_id=account_a["id"], type="expense", amount_minor=3000
    )

    response = await client.put(
        f"/api/v1/transactions/{transaction['id']}",
        headers=auth_headers,
        json={"account_id": account_b["id"]},
    )
    assert response.status_code == 200, response.text

    a_after = await _get_account(client, auth_headers, account_a["id"])
    b_after = await _get_account(client, auth_headers, account_b["id"])
    assert a_after["balance_minor"] == 10000  # fully reversed
    assert b_after["balance_minor"] == 7000  # now debited instead


async def test_delete_transaction_reverses_balance(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000)
    transaction = await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=4000
    )
    response = await client.delete(
        f"/api/v1/transactions/{transaction['id']}", headers=auth_headers
    )
    assert response.status_code == 200

    after_delete = await _get_account(client, auth_headers, account["id"])
    assert after_delete["balance_minor"] == 10000


async def test_duplicate_transaction_applies_balance_again_with_new_date(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000)
    original = await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=1000,
        occurred_at="2020-01-01T00:00:00Z",
    )

    response = await client.post(
        f"/api/v1/transactions/{original['id']}/duplicate", headers=auth_headers
    )
    assert response.status_code == 201, response.text
    duplicate = response.json()["data"]

    assert duplicate["id"] != original["id"]
    assert duplicate["occurred_at"] != original["occurred_at"]
    assert duplicate["occurred_at"].startswith("2026") or not duplicate["occurred_at"].startswith(
        "2020"
    )

    after = await _get_account(client, auth_headers, account["id"])
    assert after["balance_minor"] == 8000  # both the original and duplicate 1000 expense applied


# --- validation --------------------------------------------------------------


async def test_transfer_requires_destination_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={"account_id": account["id"], "type": "transfer", "amount_minor": 1000},
    )
    assert response.status_code == 422


async def test_transfer_rejects_same_source_and_destination(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": account["id"],
            "transfer_account_id": account["id"],
            "type": "transfer",
            "amount_minor": 1000,
        },
    )
    assert response.status_code == 422


async def test_transfer_rejects_category(client: AsyncClient, auth_headers: dict) -> None:
    source = await _create_account(client, auth_headers, name="Source")
    destination = await _create_account(client, auth_headers, name="Destination")
    food_id = await _get_category_id(client, auth_headers, "Food")
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": source["id"],
            "transfer_account_id": destination["id"],
            "type": "transfer",
            "amount_minor": 1000,
            "category_id": food_id,
        },
    )
    assert response.status_code == 422


async def test_transfer_rejects_currency_mismatch(client: AsyncClient, auth_headers: dict) -> None:
    source = await _create_account(client, auth_headers, name="Source", currency="INR")
    destination = await _create_account(client, auth_headers, name="Destination", currency="USD")
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": source["id"],
            "transfer_account_id": destination["id"],
            "type": "transfer",
            "amount_minor": 1000,
        },
    )
    assert response.status_code == 422


async def test_transfer_destination_belonging_to_another_user_is_not_found(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    my_account = await _create_account(client, auth_headers, name="Mine")
    their_account = await _create_account(client, other_auth_headers, name="Theirs")

    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": my_account["id"],
            "transfer_account_id": their_account["id"],
            "type": "transfer",
            "amount_minor": 1000,
        },
    )
    assert response.status_code == 404


async def test_transfer_source_belonging_to_another_user_is_not_found(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers, name="Theirs")
    my_account = await _create_account(client, auth_headers, name="Mine")

    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": their_account["id"],
            "transfer_account_id": my_account["id"],
            "type": "transfer",
            "amount_minor": 1000,
        },
    )
    assert response.status_code == 404


async def test_cannot_transact_against_archived_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    await client.delete(f"/api/v1/accounts/{account['id']}", headers=auth_headers)

    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={"account_id": account["id"], "type": "expense", "amount_minor": 1000},
    )
    assert response.status_code == 422


async def test_negative_or_zero_amount_rejected(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    for bad_amount in [0, -500]:
        response = await client.post(
            "/api/v1/transactions",
            headers=auth_headers,
            json={"account_id": account["id"], "type": "expense", "amount_minor": bad_amount},
        )
        assert response.status_code == 422


async def test_unknown_category_rejected(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 1000,
            "category_id": "00000000-0000-0000-0000-00000000ffff",
        },
    )
    assert response.status_code == 422


# --- authorization ------------------------------------------------------------


async def test_cannot_create_transaction_against_other_users_account(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/transactions",
        headers=other_auth_headers,
        json={"account_id": account["id"], "type": "expense", "amount_minor": 1000},
    )
    assert response.status_code == 404


async def test_cannot_get_other_users_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    transaction = await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000
    )
    response = await client.get(
        f"/api/v1/transactions/{transaction['id']}", headers=other_auth_headers
    )
    assert response.status_code == 404


async def test_cannot_update_other_users_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    transaction = await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000
    )
    response = await client.put(
        f"/api/v1/transactions/{transaction['id']}",
        headers=other_auth_headers,
        json={"amount_minor": 9999},
    )
    assert response.status_code == 404


async def test_cannot_delete_other_users_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    transaction = await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000
    )
    response = await client.delete(
        f"/api/v1/transactions/{transaction['id']}", headers=other_auth_headers
    )
    assert response.status_code == 404


async def test_cannot_duplicate_other_users_transaction(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    transaction = await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000
    )
    response = await client.post(
        f"/api/v1/transactions/{transaction['id']}/duplicate", headers=other_auth_headers
    )
    assert response.status_code == 404


async def test_transactions_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    other_account = await _create_account(client, other_auth_headers)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=1000
    )
    await _create_transaction(
        client,
        other_auth_headers,
        account_id=other_account["id"],
        type="expense",
        amount_minor=2000,
    )

    mine = await client.get("/api/v1/transactions", headers=auth_headers)
    theirs = await client.get("/api/v1/transactions", headers=other_auth_headers)
    assert len(mine.json()["data"]) == 1
    assert len(theirs.json()["data"]) == 1
    assert mine.json()["data"][0]["amount_minor"] == 1000
    assert theirs.json()["data"][0]["amount_minor"] == 2000


# --- idempotency ---------------------------------------------------------------


async def test_idempotency_key_prevents_double_booking(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers, balance_minor=10000)
    payload = {"account_id": account["id"], "type": "expense", "amount_minor": 1000}

    first = await client.post(
        "/api/v1/transactions",
        headers={**auth_headers, "Idempotency-Key": "retry-key-1"},
        json=payload,
    )
    second = await client.post(
        "/api/v1/transactions",
        headers={**auth_headers, "Idempotency-Key": "retry-key-1"},
        json=payload,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]

    after = await _get_account(client, auth_headers, account["id"])
    assert after["balance_minor"] == 9000  # debited only once


async def test_idempotency_key_is_scoped_per_user_never_shared(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    """Two different users reusing the identical Idempotency-Key string
    (e.g. both clients independently generating a predictable key, or a
    coincidence) must never collide - the database's uniqueness constraint
    is (user_id, idempotency_key), not idempotency_key alone. User B must
    get their OWN transaction, never User A's, and User A's must be
    completely unaffected by User B's request under the same key."""
    my_account = await _create_account(client, auth_headers, balance_minor=10000)
    their_account = await _create_account(
        client, other_auth_headers, name="Theirs", balance_minor=5000
    )
    shared_key = "same-key-used-by-both-users"

    mine = await client.post(
        "/api/v1/transactions",
        headers={**auth_headers, "Idempotency-Key": shared_key},
        json={"account_id": my_account["id"], "type": "expense", "amount_minor": 1000},
    )
    theirs = await client.post(
        "/api/v1/transactions",
        headers={**other_auth_headers, "Idempotency-Key": shared_key},
        json={"account_id": their_account["id"], "type": "expense", "amount_minor": 2000},
    )

    assert mine.status_code == 201, mine.text
    assert theirs.status_code == 201, theirs.text
    assert mine.json()["data"]["id"] != theirs.json()["data"]["id"]
    assert mine.json()["data"]["amount_minor"] == 1000
    assert theirs.json()["data"]["amount_minor"] == 2000

    # User B replaying the SAME key must retrieve only their own
    # transaction - never User A's, even though the key string matches.
    theirs_replay = await client.post(
        "/api/v1/transactions",
        headers={**other_auth_headers, "Idempotency-Key": shared_key},
        json={"account_id": their_account["id"], "type": "expense", "amount_minor": 2000},
    )
    assert theirs_replay.status_code == 201
    assert theirs_replay.json()["data"]["id"] == theirs.json()["data"]["id"]
    assert theirs_replay.json()["data"]["id"] != mine.json()["data"]["id"]

    # Neither user's balance was affected by the other's request.
    my_after = await _get_account(client, auth_headers, my_account["id"])
    their_after = await _get_account(client, other_auth_headers, their_account["id"])
    assert my_after["balance_minor"] == 9000  # 10000 - 1000, debited once
    # 5000 - 2000, debited once - the replay under the same key never double-charged
    assert their_after["balance_minor"] == 3000


async def test_concurrent_idempotent_requests_never_create_two_transactions(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Case D/H from the offline-sync spec: the same operation submitted
    twice at (almost) the same instant - e.g. a retried request racing the
    original after a client-side timeout - must still resolve to exactly
    one transaction, not a raw error from the two concurrent inserts
    colliding on the (user_id, idempotency_key) database constraint."""
    account = await _create_account(client, auth_headers, balance_minor=10000)
    payload = {"account_id": account["id"], "type": "expense", "amount_minor": 1500}
    headers = {**auth_headers, "Idempotency-Key": "concurrent-retry-key"}

    responses = await asyncio.gather(
        client.post("/api/v1/transactions", headers=headers, json=payload),
        client.post("/api/v1/transactions", headers=headers, json=payload),
    )

    for response in responses:
        assert response.status_code == 201, response.text

    ids = {response.json()["data"]["id"] for response in responses}
    assert len(ids) == 1, "concurrent duplicate requests must resolve to the same transaction"

    after = await _get_account(client, auth_headers, account["id"])
    assert after["balance_minor"] == 8500  # debited exactly once, never twice


async def test_service_handles_true_toctou_race_on_the_db_constraint(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministically forces the exact race window that
    test_concurrent_idempotent_requests_never_create_two_transactions can
    only probabilistically hit: a second caller whose own "does this
    idempotency key already exist" check ran (and found nothing) BEFORE
    the first caller's row was committed. Simulated here by monkeypatching
    that check to always report "not found", so the second create attempt
    proceeds straight to the INSERT and collides with the real row at the
    database's own (user_id, idempotency_key) unique constraint - proving
    the service recovers by returning the winning row instead of a raw
    IntegrityError/500."""
    account = await _create_account(client, auth_headers, balance_minor=10000)
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = uuid.UUID(me.json()["data"]["id"])
    account_id = uuid.UUID(account["id"])
    idempotency_key = "toctou-race-key"

    data = TransactionCreate(
        account_id=account_id, type=TransactionType.EXPENSE, amount_minor=2500
    )

    winner = await transaction_service.create_transaction(
        db_session, user_id=user_id, data=data, idempotency_key=idempotency_key
    )
    await db_session.commit()

    # Only the FIRST call (the pre-insert "does this already exist?" check)
    # must lie and say "no" - the recovery re-fetch inside the fixed
    # create_transaction's except-block must still see the real row, or
    # this test couldn't distinguish "the fix works" from "the check is
    # just permanently broken".
    original_lookup = TransactionRepository.get_by_idempotency_key
    call_count = {"n": 0}

    async def _lie_once_then_real(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None
        return await original_lookup(self, *args, **kwargs)

    monkeypatch.setattr(TransactionRepository, "get_by_idempotency_key", _lie_once_then_real)

    loser_result = await transaction_service.create_transaction(
        db_session, user_id=user_id, data=data, idempotency_key=idempotency_key
    )

    assert loser_result.id == winner.id, "the race loser must resolve to the winning row"
    assert call_count["n"] == 2, "expected the initial lied check plus the recovery re-fetch"

    after = await _get_account(client, auth_headers, account["id"])
    assert after["balance_minor"] == 7500  # 10000 - 2500, debited exactly once


# --- filtering, search, sort, pagination --------------------------------------


async def test_search_filters_by_description(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=100, description="Grocery run",
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=200, description="Movie night",
    )

    response = await client.get(
        "/api/v1/transactions", params={"q": "grocery"}, headers=auth_headers
    )
    results = response.json()["data"]
    assert len(results) == 1
    assert results[0]["description"] == "Grocery run"


async def test_category_and_account_filters(client: AsyncClient, auth_headers: dict) -> None:
    account_a = await _create_account(client, auth_headers, name="A")
    account_b = await _create_account(client, auth_headers, name="B")
    food_id = await _get_category_id(client, auth_headers, "Food")
    transport_id = await _get_category_id(client, auth_headers, "Transport")

    await _create_transaction(
        client, auth_headers, account_id=account_a["id"], type="expense",
        amount_minor=100, category_id=food_id,
    )
    await _create_transaction(
        client, auth_headers, account_id=account_b["id"], type="expense",
        amount_minor=200, category_id=transport_id,
    )

    by_category = await client.get(
        "/api/v1/transactions", params={"category_id": food_id}, headers=auth_headers
    )
    by_account = await client.get(
        "/api/v1/transactions", params={"account_id": account_b["id"]}, headers=auth_headers
    )
    assert len(by_category.json()["data"]) == 1
    assert by_category.json()["data"][0]["category_id"] == food_id
    assert len(by_account.json()["data"]) == 1
    assert by_account.json()["data"][0]["amount_minor"] == 200


async def test_amount_range_filter(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    for amount in [100, 500, 1000]:
        await _create_transaction(
            client, auth_headers, account_id=account["id"], type="expense", amount_minor=amount
        )

    response = await client.get(
        "/api/v1/transactions",
        params={"amount_min": 400, "amount_max": 900},
        headers=auth_headers,
    )
    amounts = [t["amount_minor"] for t in response.json()["data"]]
    assert amounts == [500]


async def test_date_range_filter(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=100, occurred_at="2020-01-15T00:00:00Z",
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=200, occurred_at="2025-06-15T00:00:00Z",
    )

    response = await client.get(
        "/api/v1/transactions",
        params={"date_from": "2024-01-01T00:00:00Z", "date_to": "2025-12-31T00:00:00Z"},
        headers=auth_headers,
    )
    amounts = [t["amount_minor"] for t in response.json()["data"]]
    assert amounts == [200]


async def test_recurring_filter(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=100, is_recurring=True,
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=200, is_recurring=False,
    )

    response = await client.get(
        "/api/v1/transactions", params={"is_recurring": True}, headers=auth_headers
    )
    amounts = [t["amount_minor"] for t in response.json()["data"]]
    assert amounts == [100]


async def test_tags_filter_matches_any_overlap(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=100, tags=["urgent", "work"],
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=200, tags=["personal"],
    )

    response = await client.get(
        "/api/v1/transactions", params={"tags": ["work"]}, headers=auth_headers
    )
    amounts = [t["amount_minor"] for t in response.json()["data"]]
    assert amounts == [100]


async def test_sort_by_amount(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    for amount in [300, 100, 200]:
        await _create_transaction(
            client, auth_headers, account_id=account["id"], type="expense", amount_minor=amount
        )

    response = await client.get(
        "/api/v1/transactions",
        params={"sort_by": "amount_minor", "sort_dir": "asc"},
        headers=auth_headers,
    )
    amounts = [t["amount_minor"] for t in response.json()["data"]]
    assert amounts == [100, 200, 300]


async def test_pagination_meta_and_limit(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    for i in range(5):
        await _create_transaction(
            client, auth_headers, account_id=account["id"], type="expense", amount_minor=100 + i
        )

    response = await client.get(
        "/api/v1/transactions", params={"limit": 2, "offset": 0}, headers=auth_headers
    )
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"]["count"] == 5
    assert body["meta"]["limit"] == 2


# --- quick add -----------------------------------------------------------------


async def test_quick_add_parse_high_confidence_strips_category_word(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "120 food lunch"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["amount_minor"] == 12000
    assert data["category_name"] == "Food"
    assert data["description"] == "Lunch"
    assert data["confidence"] == "high"


async def test_quick_add_parse_medium_confidence_keeps_keyword_in_description(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "450 uber college"},
    )
    data = response.json()["data"]
    assert data["amount_minor"] == 45000
    assert data["category_name"] == "Transport"
    assert data["description"] == "Uber college"
    assert data["confidence"] == "medium"


async def test_quick_add_parse_handles_currency_symbol(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/transactions/quick-add/parse", headers=auth_headers, json={"text": "₹250 dinner"}
    )
    data = response.json()["data"]
    assert data["amount_minor"] == 25000
    assert data["category_name"] == "Food"


async def test_quick_add_parse_reports_error_for_unparseable_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "no amount here"},
    )
    data = response.json()["data"]
    assert data["amount_minor"] is None
    assert data["error"] is not None


async def _create_category(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("icon", "🏷️")
    payload.setdefault("color", "#123456")
    response = await client.post("/api/v1/categories", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_quick_add_parse_recognizes_multi_word_custom_category(
    client: AsyncClient, auth_headers: dict
) -> None:
    category = await _create_category(client, auth_headers, name="College Snacks")
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "250 college snacks"},
    )
    data = response.json()["data"]
    assert data["amount_minor"] == 25000
    assert data["category_id"] == category["id"]
    assert data["category_name"] == "College Snacks"
    assert data["confidence"] == "high"


async def test_quick_add_parse_prefers_custom_category_over_default_keyword(
    client: AsyncClient, auth_headers: dict
) -> None:
    category = await _create_category(client, auth_headers, name="Groceries")
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "500 groceries weekly shopping"},
    )
    data = response.json()["data"]
    assert data["category_id"] == category["id"]
    assert data["category_name"] == "Groceries"
    assert data["description"] == "Weekly shopping"


async def test_quick_add_parse_never_matches_another_users_custom_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await _create_category(client, other_auth_headers, name="Groceries")
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "500 groceries weekly shopping"},
    )
    data = response.json()["data"]
    # The custom category belongs to a different user, so it must never be
    # matched here - falls through to the default "Shopping" category only.
    assert data["category_name"] == "Shopping"


async def test_quick_add_parse_reports_ambiguous_categories_for_confirmation(
    client: AsyncClient, auth_headers: dict
) -> None:
    await _create_category(client, auth_headers, name="Gym")
    await _create_category(client, auth_headers, name="Groceries")
    response = await client.post(
        "/api/v1/transactions/quick-add/parse",
        headers=auth_headers,
        json={"text": "500 gym and groceries"},
    )
    data = response.json()["data"]
    assert data["category_id"] is None
    assert data["category_name"] is None
    assert data["confidence"] == "low"
    assert data["error"] is not None
