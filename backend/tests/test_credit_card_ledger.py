"""Credit-card ledger semantics (F-001): a card's balance_minor is the amount
owed. Purchases raise it, refunds and repayments lower it, and moving money
between the user's own accounts never changes net worth."""

from httpx import AsyncClient

from tests.test_receipts import _upload_pdf

CARD_LIMIT = 10_000_000


async def _create_card(client: AsyncClient, headers: dict, *, owed: int = 0, **card) -> dict:
    payload = {
        "name": card.pop("name", "Card"),
        "type": "credit_card",
        "balance_minor": owed,
        "credit_card": {
            "credit_limit_minor": card.pop("credit_limit_minor", CARD_LIMIT),
            "statement_day": 5,
            "payment_due_day": 25,
            **card,
        },
    }
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_bank(client: AsyncClient, headers: dict, *, balance: int = 1_000_000) -> dict:
    response = await client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Bank", "type": "bank_account", "balance_minor": balance},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _account(client: AsyncClient, headers: dict, account_id: str) -> dict:
    response = await client.get(f"/api/v1/accounts/{account_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _balance(client: AsyncClient, headers: dict, account_id: str) -> int:
    return (await _account(client, headers, account_id))["balance_minor"]


async def _net_worth(client: AsyncClient, headers: dict) -> int:
    response = await client.get("/api/v1/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["net_worth_minor"]


async def _txn(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _update(client: AsyncClient, headers: dict, txn_id: str, **payload) -> dict:
    response = await client.put(f"/api/v1/transactions/{txn_id}", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- create ---------------------------------------------------------------------


async def test_card_expense_increases_owed_and_reduces_net_worth(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=50_000, credit_limit_minor=1_000_000)
    worth_before = await _net_worth(client, auth_headers)

    await _txn(client, auth_headers, account_id=card["id"], type="expense", amount_minor=30_000)

    after = await _account(client, auth_headers, card["id"])
    assert after["balance_minor"] == 80_000
    assert after["credit_card"]["utilization_percent"] == 8.0
    assert after["credit_card"]["available_credit_minor"] == 920_000
    assert await _net_worth(client, auth_headers) == worth_before - 30_000


async def test_bank_expense_still_debits_the_bank(client: AsyncClient, auth_headers: dict) -> None:
    bank = await _create_bank(client, auth_headers, balance=100_000)
    await _txn(client, auth_headers, account_id=bank["id"], type="expense", amount_minor=30_000)
    assert await _balance(client, auth_headers, bank["id"]) == 70_000


async def test_card_refund_reduces_owed_and_raises_net_worth(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=50_000)
    worth_before = await _net_worth(client, auth_headers)

    await _txn(client, auth_headers, account_id=card["id"], type="income", amount_minor=5_000)

    assert await _balance(client, auth_headers, card["id"]) == 45_000
    assert await _net_worth(client, auth_headers) == worth_before + 5_000


async def test_card_repayment_reduces_bank_and_owed_without_changing_net_worth(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers, balance=1_000_000)
    card = await _create_card(client, auth_headers, owed=300_000)
    worth_before = await _net_worth(client, auth_headers)

    await _txn(
        client,
        auth_headers,
        account_id=bank["id"],
        transfer_account_id=card["id"],
        type="transfer",
        amount_minor=100_000,
    )

    assert await _balance(client, auth_headers, bank["id"]) == 900_000
    assert await _balance(client, auth_headers, card["id"]) == 200_000
    assert await _net_worth(client, auth_headers) == worth_before


async def test_card_repayment_is_not_income_or_expense(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers)
    card = await _create_card(client, auth_headers, owed=300_000)
    before = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()["data"]

    await _txn(
        client,
        auth_headers,
        account_id=bank["id"],
        transfer_account_id=card["id"],
        type="transfer",
        amount_minor=100_000,
    )

    after = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()["data"]
    assert after["total_income_minor"] == before["total_income_minor"]
    assert after["total_expense_minor"] == before["total_expense_minor"]


async def test_cash_advance_raises_owed_and_bank_without_changing_net_worth(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers, balance=100_000)
    card = await _create_card(client, auth_headers, owed=0)
    worth_before = await _net_worth(client, auth_headers)

    await _txn(
        client,
        auth_headers,
        account_id=card["id"],
        transfer_account_id=bank["id"],
        type="transfer",
        amount_minor=40_000,
    )

    assert await _balance(client, auth_headers, card["id"]) == 40_000
    assert await _balance(client, auth_headers, bank["id"]) == 140_000
    assert await _net_worth(client, auth_headers) == worth_before


async def test_card_to_card_transfer_moves_debt_without_changing_net_worth(
    client: AsyncClient, auth_headers: dict
) -> None:
    source = await _create_card(client, auth_headers, name="Source", owed=10_000)
    target = await _create_card(client, auth_headers, name="Target", owed=60_000)
    worth_before = await _net_worth(client, auth_headers)

    await _txn(
        client,
        auth_headers,
        account_id=source["id"],
        transfer_account_id=target["id"],
        type="transfer",
        amount_minor=50_000,
    )

    assert await _balance(client, auth_headers, source["id"]) == 60_000
    assert await _balance(client, auth_headers, target["id"]) == 10_000
    assert await _net_worth(client, auth_headers) == worth_before


async def test_overpayment_leaves_a_credit_balance(client: AsyncClient, auth_headers: dict) -> None:
    bank = await _create_bank(client, auth_headers)
    card = await _create_card(client, auth_headers, owed=20_000)

    await _txn(
        client,
        auth_headers,
        account_id=bank["id"],
        transfer_account_id=card["id"],
        type="transfer",
        amount_minor=25_000,
    )

    after = await _account(client, auth_headers, card["id"])
    assert after["balance_minor"] == -5_000
    assert after["credit_card"]["available_credit_minor"] == CARD_LIMIT + 5_000


async def test_idempotent_replay_applies_the_card_effect_once(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=0)
    headers = {**auth_headers, "Idempotency-Key": "card-expense-1"}
    payload = {"account_id": card["id"], "type": "expense", "amount_minor": 12_000}

    first = await client.post("/api/v1/transactions", headers=headers, json=payload)
    second = await client.post("/api/v1/transactions", headers=headers, json=payload)

    assert first.status_code == 201 and second.status_code == 201
    assert await _balance(client, auth_headers, card["id"]) == 12_000


# --- edit -----------------------------------------------------------------------


async def test_editing_card_expense_amount_rebooks_owed(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=10_000)
    txn = await _txn(
        client, auth_headers, account_id=card["id"], type="expense", amount_minor=4_000
    )

    await _update(client, auth_headers, txn["id"], amount_minor=6_000)

    assert await _balance(client, auth_headers, card["id"]) == 16_000


async def test_moving_expense_from_bank_to_card_and_back(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers, balance=100_000)
    card = await _create_card(client, auth_headers, owed=0)
    txn = await _txn(
        client, auth_headers, account_id=bank["id"], type="expense", amount_minor=9_000
    )

    await _update(client, auth_headers, txn["id"], account_id=card["id"])
    assert await _balance(client, auth_headers, bank["id"]) == 100_000
    assert await _balance(client, auth_headers, card["id"]) == 9_000

    await _update(client, auth_headers, txn["id"], account_id=bank["id"])
    assert await _balance(client, auth_headers, bank["id"]) == 91_000
    assert await _balance(client, auth_headers, card["id"]) == 0


async def test_changing_card_expense_into_repayment_transfer(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers, balance=100_000)
    card = await _create_card(client, auth_headers, owed=50_000)
    txn = await _txn(
        client, auth_headers, account_id=bank["id"], type="expense", amount_minor=20_000
    )
    worth_before_edit = await _net_worth(client, auth_headers)

    await _update(client, auth_headers, txn["id"], type="transfer", transfer_account_id=card["id"])

    assert await _balance(client, auth_headers, bank["id"]) == 80_000
    assert await _balance(client, auth_headers, card["id"]) == 30_000
    # The expense no longer exists, so the 20,000 it took off net worth comes back.
    assert await _net_worth(client, auth_headers) == worth_before_edit + 20_000


async def test_changing_repayment_transfer_into_card_expense(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers, balance=100_000)
    card = await _create_card(client, auth_headers, owed=50_000)
    txn = await _txn(
        client,
        auth_headers,
        account_id=bank["id"],
        transfer_account_id=card["id"],
        type="transfer",
        amount_minor=20_000,
    )
    assert await _balance(client, auth_headers, card["id"]) == 30_000

    await _update(client, auth_headers, txn["id"], account_id=card["id"], type="expense")

    assert await _balance(client, auth_headers, bank["id"]) == 100_000
    assert await _balance(client, auth_headers, card["id"]) == 70_000


async def test_changing_card_expense_into_refund(client: AsyncClient, auth_headers: dict) -> None:
    card = await _create_card(client, auth_headers, owed=50_000)
    txn = await _txn(
        client, auth_headers, account_id=card["id"], type="expense", amount_minor=8_000
    )
    assert await _balance(client, auth_headers, card["id"]) == 58_000

    await _update(client, auth_headers, txn["id"], type="income")

    assert await _balance(client, auth_headers, card["id"]) == 42_000


# --- delete / duplicate --------------------------------------------------------


async def test_deleting_card_transactions_restores_owed(
    client: AsyncClient, auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers, balance=100_000)
    card = await _create_card(client, auth_headers, owed=50_000)
    expense = await _txn(
        client, auth_headers, account_id=card["id"], type="expense", amount_minor=7_000
    )
    payment = await _txn(
        client,
        auth_headers,
        account_id=bank["id"],
        transfer_account_id=card["id"],
        type="transfer",
        amount_minor=10_000,
    )

    for txn in (expense, payment):
        response = await client.delete(f"/api/v1/transactions/{txn['id']}", headers=auth_headers)
        assert response.status_code == 200, response.text

    assert await _balance(client, auth_headers, card["id"]) == 50_000
    assert await _balance(client, auth_headers, bank["id"]) == 100_000


async def test_deleting_expense_on_archived_card_still_reverses_correctly(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=0)
    txn = await _txn(
        client, auth_headers, account_id=card["id"], type="expense", amount_minor=7_000
    )
    archive = await client.delete(f"/api/v1/accounts/{card['id']}", headers=auth_headers)
    assert archive.status_code == 200, archive.text

    response = await client.delete(f"/api/v1/transactions/{txn['id']}", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert await _balance(client, auth_headers, card["id"]) == 0


async def test_duplicating_card_expense_books_it_again(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=0)
    txn = await _txn(
        client, auth_headers, account_id=card["id"], type="expense", amount_minor=3_000
    )

    response = await client.post(
        f"/api/v1/transactions/{txn['id']}/duplicate", headers=auth_headers
    )

    assert response.status_code == 201, response.text
    assert await _balance(client, auth_headers, card["id"]) == 6_000


# --- other write paths that reuse create_transaction ---------------------------


async def test_recurring_expense_on_card_increases_owed(
    client: AsyncClient, auth_headers: dict
) -> None:
    from datetime import date

    card = await _create_card(client, auth_headers, owed=0)
    created = await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Streaming",
            "account_id": card["id"],
            "type": "expense",
            "amount_minor": 64_900,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    generated = await client.post("/api/v1/recurring-transactions/generate", headers=auth_headers)

    assert generated.status_code == 200, generated.text
    assert len(generated.json()["data"]) == 1
    assert await _balance(client, auth_headers, card["id"]) == 64_900


async def test_receipt_expense_on_card_increases_owed(
    client: AsyncClient, auth_headers: dict
) -> None:
    card = await _create_card(client, auth_headers, owed=0)
    receipt = await _upload_pdf(client, auth_headers)
    confirm = await client.put(
        f"/api/v1/receipts/{receipt['id']}/confirm",
        headers=auth_headers,
        json={"merchant": "Corner Cafe", "date": "2026-03-05", "total_minor": 60_000},
    )
    assert confirm.status_code == 200, confirm.text

    response = await client.post(
        f"/api/v1/receipts/{receipt['id']}/transaction",
        headers=auth_headers,
        json={"account_id": card["id"]},
    )

    assert response.status_code == 201, response.text
    assert await _balance(client, auth_headers, card["id"]) == 60_000


# --- isolation -----------------------------------------------------------------


async def test_cannot_repay_another_users_card(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    bank = await _create_bank(client, auth_headers)
    victim_card = await _create_card(client, other_auth_headers, owed=50_000)

    response = await client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": bank["id"],
            "transfer_account_id": victim_card["id"],
            "type": "transfer",
            "amount_minor": 10_000,
        },
    )

    assert response.status_code == 404
    assert await _balance(client, auth_headers, bank["id"]) == 1_000_000
    assert await _balance(client, other_auth_headers, victim_card["id"]) == 50_000
