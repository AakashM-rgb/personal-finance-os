from datetime import date, timedelta

from httpx import AsyncClient


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 10000000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def _create_subscription(
    client: AsyncClient, headers: dict, account_id: str, **overrides
) -> dict:
    payload = {
        "name": "Netflix",
        "account_id": account_id,
        "amount_minor": 64900,
        "frequency": "monthly",
        "start_date": date.today().isoformat(),
    }
    payload.update(overrides)
    response = await client.post("/api/v1/subscriptions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _generate(client: AsyncClient, headers: dict) -> list[dict]:
    response = await client.post("/api/v1/recurring-transactions/generate", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_transaction(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


# --- creation / validation ----------------------------------------------------------


async def test_create_subscription(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    today = date.today()

    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        name="Netflix",
        amount_minor=64900,
        category_id=food_id,
        frequency="monthly",
        start_date=today.isoformat(),
    )

    assert subscription["name"] == "Netflix"
    assert subscription["account_id"] == account["id"]
    assert subscription["account_name"] == account["name"]
    assert subscription["category_id"] == food_id
    assert subscription["category_name"] == "Food"
    assert subscription["amount_minor"] == 64900
    assert subscription["currency"] == account["currency"]
    assert subscription["frequency"] == "monthly"
    assert subscription["monthly_cost_minor"] == 64900
    assert subscription["yearly_cost_minor"] == 778800
    assert subscription["next_renewal_date"] == today.isoformat()  # nothing generated yet
    assert subscription["is_active"] is True
    assert subscription["is_possibly_unused"] is None
    assert "hasn't been billed yet" in subscription["unused_reason"]


async def test_create_rejects_zero_or_negative_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    for bad_amount in [0, -500]:
        response = await client.post(
            "/api/v1/subscriptions",
            headers=auth_headers,
            json={
                "name": "Bad",
                "account_id": account["id"],
                "amount_minor": bad_amount,
                "frequency": "monthly",
                "start_date": date.today().isoformat(),
            },
        )
        assert response.status_code == 422


async def test_create_rejects_unknown_account(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": "00000000-0000-0000-0000-00000000ffff",
            "amount_minor": 1000,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 404


async def test_create_rejects_archived_account(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    archive_response = await client.delete(
        f"/api/v1/accounts/{account['id']}", headers=auth_headers
    )
    assert archive_response.status_code == 200

    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "amount_minor": 1000,
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_unknown_category(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "amount_minor": 1000,
            "category_id": "00000000-0000-0000-0000-00000000ffff",
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_another_users_custom_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    their_category_response = await client.post(
        "/api/v1/categories",
        headers=other_auth_headers,
        json={"name": "Their Category", "icon": "🏷️", "color": "#123456"},
    )
    assert their_category_response.status_code == 201
    their_category = their_category_response.json()["data"]

    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "amount_minor": 1000,
            "category_id": their_category["id"],
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_a_type_field(client: AsyncClient, auth_headers: dict) -> None:
    # A subscription is always an expense - there is no `type` field to set.
    account = await _create_account(client, auth_headers)
    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={
            "name": "Bad",
            "account_id": account["id"],
            "amount_minor": 1000,
            "type": "income",
            "frequency": "monthly",
            "start_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_created_subscription_is_backed_by_an_expense_recurring_transaction(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    subscription = await _create_subscription(client, auth_headers, account["id"])

    recurring_response = await client.get(
        f"/api/v1/recurring-transactions/{subscription['recurring_transaction_id']}",
        headers=auth_headers,
    )
    assert recurring_response.status_code == 200
    assert recurring_response.json()["data"]["type"] == "expense"


# --- CRUD -----------------------------------------------------------------------------


async def test_list_starts_empty(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/subscriptions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_get_by_id(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_subscription(client, auth_headers, account["id"])
    response = await client.get(f"/api/v1/subscriptions/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


async def test_get_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/subscriptions/00000000-0000-0000-0000-00000000ffff", headers=auth_headers
    )
    assert response.status_code == 404


async def test_update_amount_and_frequency(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_subscription(client, auth_headers, account["id"], frequency="monthly")
    response = await client.put(
        f"/api/v1/subscriptions/{created['id']}",
        headers=auth_headers,
        json={"amount_minor": 99900, "frequency": "yearly"},
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["amount_minor"] == 99900
    assert updated["frequency"] == "yearly"
    assert updated["monthly_cost_minor"] == 8325  # 99900 / 12 rounded
    assert updated["yearly_cost_minor"] == 99900
    assert updated["name"] == created["name"]


async def test_update_category_clear(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    created = await _create_subscription(client, auth_headers, account["id"], category_id=food_id)
    response = await client.put(
        f"/api/v1/subscriptions/{created['id']}",
        headers=auth_headers,
        json={"clear_category": True},
    )
    assert response.status_code == 200
    assert response.json()["data"]["category_id"] is None
    assert response.json()["data"]["is_possibly_unused"] is None
    assert "No category" in response.json()["data"]["unused_reason"]


async def test_update_account_changes_currency(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers, currency="INR")
    other_account = await _create_account(client, auth_headers, name="USD Account", currency="USD")
    created = await _create_subscription(client, auth_headers, account["id"])

    response = await client.put(
        f"/api/v1/subscriptions/{created['id']}",
        headers=auth_headers,
        json={"account_id": other_account["id"]},
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["account_id"] == other_account["id"]
    assert updated["currency"] == "USD"


async def test_update_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.put(
        "/api/v1/subscriptions/00000000-0000-0000-0000-00000000ffff",
        headers=auth_headers,
        json={"name": "Nope"},
    )
    assert response.status_code == 404


async def test_deactivate(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _create_subscription(client, auth_headers, account["id"])

    response = await client.delete(f"/api/v1/subscriptions/{created['id']}", headers=auth_headers)
    assert response.status_code == 200

    follow_up = await client.get(f"/api/v1/subscriptions/{created['id']}", headers=auth_headers)
    assert follow_up.status_code == 200
    assert follow_up.json()["data"]["is_active"] is False


async def test_deactivate_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.delete(
        "/api/v1/subscriptions/00000000-0000-0000-0000-00000000ffff", headers=auth_headers
    )
    assert response.status_code == 404


# --- authorization isolation --------------------------------------------------------


async def test_cannot_read_another_users_subscription(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    theirs = await _create_subscription(client, other_auth_headers, their_account["id"])
    response = await client.get(f"/api/v1/subscriptions/{theirs['id']}", headers=auth_headers)
    assert response.status_code == 404


async def test_cannot_update_another_users_subscription(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    theirs = await _create_subscription(client, other_auth_headers, their_account["id"])
    response = await client.put(
        f"/api/v1/subscriptions/{theirs['id']}",
        headers=auth_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


async def test_cannot_deactivate_another_users_subscription(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    theirs = await _create_subscription(client, other_auth_headers, their_account["id"])

    response = await client.delete(f"/api/v1/subscriptions/{theirs['id']}", headers=auth_headers)
    assert response.status_code == 404

    still_theirs = await client.get(
        f"/api/v1/subscriptions/{theirs['id']}", headers=other_auth_headers
    )
    assert still_theirs.json()["data"]["is_active"] is True


async def test_list_never_leaks_another_users_subscriptions(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_account = await _create_account(client, other_auth_headers)
    await _create_subscription(client, other_auth_headers, their_account["id"], name="Theirs")
    account = await _create_account(client, auth_headers)
    await _create_subscription(client, auth_headers, account["id"], name="Mine")

    response = await client.get("/api/v1/subscriptions", headers=auth_headers)
    names = [s["name"] for s in response.json()["data"]]
    assert names == ["Mine"]


# --- monthly / yearly cost + next renewal via the API -------------------------------


async def test_spec_worked_example_four_subscriptions(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today()
    amounts = {"Netflix": 64900, "Spotify": 11900, "Adobe": 167500, "GitHub": 40000}

    for name, amount in amounts.items():
        sub = await _create_subscription(
            client,
            auth_headers,
            account["id"],
            name=name,
            amount_minor=amount,
            frequency="monthly",
            start_date=today.isoformat(),
        )
        assert sub["monthly_cost_minor"] == amount
        assert sub["yearly_cost_minor"] == amount * 12

    response = await client.get("/api/v1/subscriptions", headers=auth_headers)
    subs = response.json()["data"]
    monthly_total = sum(s["monthly_cost_minor"] for s in subs)
    yearly_total = sum(s["yearly_cost_minor"] for s in subs)
    assert monthly_total == 284300  # Rs. 2,843
    assert yearly_total == 3411600  # Rs. 34,116


async def test_next_renewal_advances_after_generation(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    today = date.today()
    subscription = await _create_subscription(
        client, auth_headers, account["id"], frequency="daily", start_date=today.isoformat()
    )
    assert subscription["next_renewal_date"] == today.isoformat()

    await _generate(client, auth_headers)

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    assert after.json()["data"]["next_renewal_date"] == (today + timedelta(days=1)).isoformat()


# --- unused-subscription evidence: no supporting data --------------------------------


async def test_unused_claim_omitted_when_never_billed(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    subscription = await _create_subscription(
        client, auth_headers, account["id"], category_id=food_id
    )
    # No generate call at all - zero billing history.
    assert subscription["is_possibly_unused"] is None
    assert "hasn't been billed yet" in subscription["unused_reason"]


async def test_unused_claim_omitted_when_no_category_set(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        frequency="daily",
        start_date=(date.today() - timedelta(days=100)).isoformat(),
    )
    await _generate(client, auth_headers)

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    data = after.json()["data"]
    assert data["is_possibly_unused"] is None
    assert "No category" in data["unused_reason"]


async def test_unused_claim_omitted_when_recently_created(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    today = date.today()
    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        category_id=food_id,
        frequency="daily",
        start_date=today.isoformat(),
    )
    await _generate(client, auth_headers)  # bills exactly once, today

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    data = after.json()["data"]
    assert data["is_possibly_unused"] is None
    assert "day(s) of billing history" in data["unused_reason"]


async def test_unused_claim_omitted_when_just_under_the_minimum_age(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    today = date.today()
    start = today - timedelta(days=59)  # MIN_SUBSCRIPTION_AGE_DAYS is 60
    await _create_subscription(
        client,
        auth_headers,
        account["id"],
        category_id=food_id,
        frequency="daily",
        start_date=start.isoformat(),
    )
    generated = await _generate(client, auth_headers)
    assert len(generated) == 60  # start..today inclusive

    response = await client.get("/api/v1/subscriptions", headers=auth_headers)
    data = response.json()["data"][0]
    assert data["is_possibly_unused"] is None


# --- unused-subscription evidence: supporting data exists -----------------------------


async def test_flagged_possibly_unused_with_sufficient_history_and_no_other_activity(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    start = date.today() - timedelta(days=65)
    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        category_id=food_id,
        frequency="daily",
        start_date=start.isoformat(),
    )
    await _generate(client, auth_headers)

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    data = after.json()["data"]
    assert data["is_possibly_unused"] is True
    assert "No other transactions in this category" in data["unused_reason"]


async def test_not_flagged_when_other_category_activity_exists(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    start = date.today() - timedelta(days=65)
    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        category_id=food_id,
        frequency="daily",
        start_date=start.isoformat(),
    )
    await _generate(client, auth_headers)

    # A real, manual transaction in the same category, recently - genuine
    # supporting evidence that the category is still active.
    recent = date.today() - timedelta(days=5)
    await _create_transaction(
        client,
        auth_headers,
        account_id=account["id"],
        type="expense",
        amount_minor=50000,
        category_id=food_id,
        occurred_at=f"{recent.isoformat()}T12:00:00Z",
        description="Grocery run",
    )

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    data = after.json()["data"]
    assert data["is_possibly_unused"] is False
    assert "Found 1 other transaction" in data["unused_reason"]


async def test_subscriptions_own_generated_charges_never_count_as_other_activity(
    client: AsyncClient, auth_headers: dict
) -> None:
    # The subscription bills itself dozens of times over 65 days - none of
    # those charges may count as "other" activity in its own category,
    # or it could never legitimately be flagged.
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    start = date.today() - timedelta(days=65)
    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        category_id=food_id,
        frequency="daily",
        start_date=start.isoformat(),
    )
    generated = await _generate(client, auth_headers)
    assert len(generated) == 66  # its own charges - must be excluded from the check

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    assert after.json()["data"]["is_possibly_unused"] is True


async def test_another_recurring_transactions_charges_in_the_same_category_count_as_activity(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    start = date.today() - timedelta(days=65)
    subscription = await _create_subscription(
        client,
        auth_headers,
        account["id"],
        category_id=food_id,
        frequency="daily",
        start_date=start.isoformat(),
    )
    # A second, unrelated recurring transaction in the same category,
    # billing recently.
    await client.post(
        "/api/v1/recurring-transactions",
        headers=auth_headers,
        json={
            "name": "Weekly groceries",
            "account_id": account["id"],
            "type": "expense",
            "amount_minor": 30000,
            "category_id": food_id,
            "frequency": "weekly",
            "start_date": (date.today() - timedelta(days=6)).isoformat(),
        },
    )
    await _generate(client, auth_headers)

    after = await client.get(f"/api/v1/subscriptions/{subscription['id']}", headers=auth_headers)
    data = after.json()["data"]
    assert data["is_possibly_unused"] is False
    assert "Found 1 other transaction" in data["unused_reason"]
