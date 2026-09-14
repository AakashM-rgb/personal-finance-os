from httpx import AsyncClient


async def test_list_accounts_starts_empty(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/accounts", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_create_bank_account(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "HDFC Savings",
            "type": "bank_account",
            "balance_minor": 500000,
            "currency": "INR",
            "institution_name": "HDFC Bank",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["name"] == "HDFC Savings"
    assert data["type"] == "bank_account"
    assert data["balance_minor"] == 500000
    assert data["institution_name"] == "HDFC Bank"
    assert data["is_active"] is True
    assert data["credit_card"] is None


async def test_create_each_non_credit_card_type(client: AsyncClient, auth_headers: dict) -> None:
    for account_type in ["cash", "upi", "savings_account", "wallet"]:
        response = await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={"name": account_type, "type": account_type, "balance_minor": 1000},
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["type"] == account_type


async def test_create_credit_card_requires_credit_card_fields(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Amex", "type": "credit_card", "balance_minor": 0},
    )
    assert response.status_code == 422


async def test_credit_card_fields_rejected_for_non_credit_card_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Cash",
            "type": "cash",
            "credit_card": {
                "credit_limit_minor": 100000,
                "statement_day": 1,
                "payment_due_day": 15,
            },
        },
    )
    assert response.status_code == 422


async def test_credit_card_utilization_matches_spec_example(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Spec example: 32,450 / 1,00,000 -> 32.45% utilization.
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={
            "name": "Amex",
            "type": "credit_card",
            "balance_minor": 3245000,
            "credit_card": {
                "credit_limit_minor": 10000000,
                "statement_day": 5,
                "payment_due_day": 25,
                "minimum_payment_minor": 100000,
            },
        },
    )
    assert response.status_code == 201, response.text
    credit_card = response.json()["data"]["credit_card"]
    assert credit_card["available_credit_minor"] == 10000000 - 3245000
    assert credit_card["utilization_percent"] == 32.45


async def test_credit_card_utilization_edge_cases(client: AsyncClient, auth_headers: dict) -> None:
    cases = [
        (0, 0.0),  # no usage
        (10000000, 100.0),  # fully utilized
        (12000000, 120.0),  # over limit - allowed to exceed 100%, not clamped/hidden
    ]
    for balance_minor, expected_percent in cases:
        response = await client.post(
            "/api/v1/accounts",
            headers=auth_headers,
            json={
                "name": "Amex",
                "type": "credit_card",
                "balance_minor": balance_minor,
                "credit_card": {
                    "credit_limit_minor": 10000000,
                    "statement_day": 1,
                    "payment_due_day": 15,
                },
            },
        )
        assert response.status_code == 201, response.text
        credit_card = response.json()["data"]["credit_card"]
        assert credit_card["utilization_percent"] == expected_percent
        assert credit_card["available_credit_minor"] == 10000000 - balance_minor


async def test_get_account_not_found_for_other_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Wallet", "type": "wallet", "balance_minor": 0},
    )
    account_id = create_response.json()["data"]["id"]

    response = await client.get(f"/api/v1/accounts/{account_id}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_update_account_cannot_change_type(client: AsyncClient, auth_headers: dict) -> None:
    create_response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Wallet", "type": "wallet", "balance_minor": 0},
    )
    account_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/accounts/{account_id}",
        headers=auth_headers,
        json={"type": "bank_account"},
    )
    assert response.status_code == 422  # `type` is not a field AccountUpdate accepts


async def test_update_account_updates_fields(client: AsyncClient, auth_headers: dict) -> None:
    create_response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Wallet", "type": "wallet", "balance_minor": 0},
    )
    account_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/accounts/{account_id}",
        headers=auth_headers,
        json={"name": "Paytm Wallet", "balance_minor": 5000},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Paytm Wallet"
    assert data["balance_minor"] == 5000


async def test_update_other_users_account_not_found(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Wallet", "type": "wallet", "balance_minor": 0},
    )
    account_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/accounts/{account_id}",
        headers=other_auth_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


async def test_delete_account_soft_deletes_and_hides_from_default_list(
    client: AsyncClient, auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Wallet", "type": "wallet", "balance_minor": 0},
    )
    account_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert delete_response.status_code == 200

    list_response = await client.get("/api/v1/accounts", headers=auth_headers)
    assert list_response.json()["data"] == []

    include_inactive_response = await client.get(
        "/api/v1/accounts", params={"include_inactive": True}, headers=auth_headers
    )
    ids = [a["id"] for a in include_inactive_response.json()["data"]]
    assert account_id in ids

    get_response = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["is_active"] is False


async def test_delete_other_users_account_not_found(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Wallet", "type": "wallet", "balance_minor": 0},
    )
    account_id = create_response.json()["data"]["id"]

    response = await client.delete(f"/api/v1/accounts/{account_id}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_accounts_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Mine", "type": "cash", "balance_minor": 0},
    )
    await client.post(
        "/api/v1/accounts",
        headers=other_auth_headers,
        json={"name": "Theirs", "type": "cash", "balance_minor": 0},
    )

    mine = await client.get("/api/v1/accounts", headers=auth_headers)
    theirs = await client.get("/api/v1/accounts", headers=other_auth_headers)

    assert [a["name"] for a in mine.json()["data"]] == ["Mine"]
    assert [a["name"] for a in theirs.json()["data"]] == ["Theirs"]
