from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


def _months_ago(reference: datetime, months_ago: int) -> datetime:
    """The 15th of the month that is `months_ago` months before `reference`'s
    month, at noon UTC - a date safely inside that calendar month regardless
    of month length, avoiding any day-offset/boundary ambiguity."""
    total_months = reference.year * 12 + (reference.month - 1) - months_ago
    year, month0 = divmod(total_months, 12)
    return datetime(year, month0 + 1, 15, 12, 0, tzinfo=UTC)


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 1000000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def _create_category(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("icon", "🏷️")
    payload.setdefault("color", "#123456")
    response = await client.post("/api/v1/categories", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_transaction(client: AsyncClient, headers: dict, **payload) -> dict:
    response = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_budget(
    client: AsyncClient, headers: dict, category_id: str, amount_minor: int
) -> dict:
    response = await client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"category_id": category_id, "amount_minor": amount_minor},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# --- creation / validation -------------------------------------------------------


async def test_create_budget_for_category(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 500000)

    assert budget["category_id"] == food_id
    assert budget["category_name"] == "Food"
    assert budget["currency"] == "INR"  # the user's base currency, not fabricated
    assert budget["amount_minor"] == 500000
    assert budget["spent_minor"] == 0
    assert budget["remaining_minor"] == 500000
    assert budget["percent_used"] == 0.0
    assert budget["status"] == "healthy"
    assert budget["warning_message"] is None


async def test_create_rejects_duplicate_category(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_budget(client, auth_headers, food_id, 500000)

    response = await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": food_id, "amount_minor": 100000},
    )
    assert response.status_code == 409


async def test_create_rejects_unknown_category(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": "00000000-0000-0000-0000-00000000ffff", "amount_minor": 100000},
    )
    assert response.status_code == 422


async def test_create_rejects_zero_or_negative_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    for bad_amount in [0, -500]:
        response = await client.post(
            "/api/v1/budgets",
            headers=auth_headers,
            json={"category_id": food_id, "amount_minor": bad_amount},
        )
        assert response.status_code == 422


async def test_cannot_budget_another_users_custom_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    their_category = await _create_category(client, other_auth_headers, name="Their Category")
    response = await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": their_category["id"], "amount_minor": 100000},
    )
    assert response.status_code == 422


# --- spending progress from real transactions -------------------------------------


async def test_spending_progress_matches_spec_example(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Spec example: Food ₹3,240 / ₹5,000 -> 64.8%
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_budget(client, auth_headers, food_id, 500000)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=324000, category_id=food_id,
    )

    response = await client.get("/api/v1/budgets", headers=auth_headers)
    budget = response.json()["data"][0]
    assert budget["spent_minor"] == 324000
    assert budget["percent_used"] == 64.8
    assert budget["remaining_minor"] == 176000
    assert budget["status"] == "healthy"  # under the 70% warning threshold


async def test_status_progression_across_thresholds(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)  # ₹1000 limit

    async def _spend(amount_minor: int) -> dict:
        await _create_transaction(
            client, auth_headers, account_id=account["id"], type="expense",
            amount_minor=amount_minor, category_id=food_id,
        )
        response = await client.get(f"/api/v1/budgets/{budget['id']}", headers=auth_headers)
        assert response.status_code == 200
        return response.json()["data"]

    healthy = await _spend(50000)  # 50%
    assert healthy["status"] == "healthy"
    assert healthy["warning_message"] is None

    warning = await _spend(25000)  # cumulative 75%
    assert warning["status"] == "warning"
    assert warning["warning_message"] == "You've used 75% of your Food budget."

    near_limit = await _spend(17000)  # cumulative 92%
    assert near_limit["status"] == "near_limit"
    assert "92%" in near_limit["warning_message"]

    exceeded = await _spend(20000)  # cumulative 112%
    assert exceeded["status"] == "exceeded"
    assert "exceeded" in exceeded["warning_message"].lower()
    assert exceeded["remaining_minor"] == -12000


async def test_projected_month_amount_is_present_and_derived_from_real_spending(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 500000)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=30000, category_id=food_id,
    )

    response = await client.get(f"/api/v1/budgets/{budget['id']}", headers=auth_headers)
    data = response.json()["data"]
    expected = round((data["spent_minor"] / data["days_elapsed"]) * data["days_in_month"])
    assert data["projected_month_minor"] == expected


async def test_transfers_do_not_affect_budget_spending(
    client: AsyncClient, auth_headers: dict
) -> None:
    source = await _create_account(client, auth_headers, name="Source")
    destination = await _create_account(client, auth_headers, name="Destination")
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_budget(client, auth_headers, food_id, 500000)

    await _create_transaction(
        client, auth_headers, account_id=source["id"], transfer_account_id=destination["id"],
        type="transfer", amount_minor=100000,
    )

    response = await client.get("/api/v1/budgets", headers=auth_headers)
    assert response.json()["data"][0]["spent_minor"] == 0


# --- update / delete ---------------------------------------------------------------


async def test_update_budget_amount_recomputes_status(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense",
        amount_minor=95000, category_id=food_id,
    )

    before = await client.get(f"/api/v1/budgets/{budget['id']}", headers=auth_headers)
    assert before.json()["data"]["status"] == "near_limit"

    response = await client.put(
        f"/api/v1/budgets/{budget['id']}", headers=auth_headers, json={"amount_minor": 500000}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["amount_minor"] == 500000
    assert data["status"] == "healthy"


async def test_update_rejects_category_id_change(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)
    transport_id = await _get_category_id(client, auth_headers, "Transport")

    response = await client.put(
        f"/api/v1/budgets/{budget['id']}",
        headers=auth_headers,
        json={"amount_minor": 100000, "category_id": transport_id},
    )
    assert response.status_code == 422  # category_id isn't an accepted field


async def test_delete_budget_is_a_real_removal(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)

    response = await client.delete(f"/api/v1/budgets/{budget['id']}", headers=auth_headers)
    assert response.status_code == 200

    get_response = await client.get(f"/api/v1/budgets/{budget['id']}", headers=auth_headers)
    assert get_response.status_code == 404

    list_response = await client.get("/api/v1/budgets", headers=auth_headers)
    assert list_response.json()["data"] == []


async def test_deleted_budget_category_can_be_rebudgeted(
    client: AsyncClient, auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)
    await client.delete(f"/api/v1/budgets/{budget['id']}", headers=auth_headers)

    response = await client.post(
        "/api/v1/budgets",
        headers=auth_headers,
        json={"category_id": food_id, "amount_minor": 200000},
    )
    assert response.status_code == 201


# --- authorization / isolation -----------------------------------------------------


async def test_cannot_get_other_users_budget(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)

    response = await client.get(f"/api/v1/budgets/{budget['id']}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_cannot_update_other_users_budget(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)

    response = await client.put(
        f"/api/v1/budgets/{budget['id']}", headers=other_auth_headers, json={"amount_minor": 1}
    )
    assert response.status_code == 404


async def test_cannot_delete_other_users_budget(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    budget = await _create_budget(client, auth_headers, food_id, 100000)

    response = await client.delete(f"/api/v1/budgets/{budget['id']}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_budgets_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_budget(client, auth_headers, food_id, 100000)

    theirs = await client.get("/api/v1/budgets", headers=other_auth_headers)
    assert theirs.json()["data"] == []


async def test_budget_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/budgets")
    assert response.status_code == 401


# --- suggestions ---------------------------------------------------------------


async def test_suggestion_uses_average_of_historical_months(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    transport_id = await _get_category_id(client, auth_headers, "Transport")
    now = datetime.now(UTC)

    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=200000,
        category_id=transport_id, occurred_at=_months_ago(now, 1).isoformat(),
    )
    await _create_transaction(
        client, auth_headers, account_id=account["id"], type="expense", amount_minor=100000,
        category_id=transport_id, occurred_at=_months_ago(now, 2).isoformat(),
    )

    response = await client.get("/api/v1/budgets/suggestions", headers=auth_headers)
    suggestions = {s["category_id"]: s for s in response.json()["data"]}
    assert transport_id in suggestions
    suggestion = suggestions[transport_id]
    assert suggestion["suggested_amount_minor"] == 150000  # average of 200000 and 100000
    assert "2 month" in suggestion["based_on"]


async def test_suggestion_excludes_categories_with_existing_budget(
    client: AsyncClient, auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_budget(client, auth_headers, food_id, 500000)

    response = await client.get("/api/v1/budgets/suggestions", headers=auth_headers)
    suggested_ids = {s["category_id"] for s in response.json()["data"]}
    assert food_id not in suggested_ids


async def test_suggestion_falls_back_to_category_default_with_no_history(
    client: AsyncClient, auth_headers: dict
) -> None:
    category = await _create_category(
        client, auth_headers, name="Pet Care", budget_minor=250000
    )

    response = await client.get("/api/v1/budgets/suggestions", headers=auth_headers)
    suggestions = {s["category_id"]: s for s in response.json()["data"]}
    assert category["id"] in suggestions
    assert suggestions[category["id"]]["suggested_amount_minor"] == 250000
    assert suggestions[category["id"]]["based_on"] == "this category's default budget"


async def test_suggestion_omitted_with_no_history_and_no_default(
    client: AsyncClient, auth_headers: dict
) -> None:
    category = await _create_category(client, auth_headers, name="Unused Category")

    response = await client.get("/api/v1/budgets/suggestions", headers=auth_headers)
    suggested_ids = {s["category_id"] for s in response.json()["data"]}
    assert category["id"] not in suggested_ids


async def test_suggestions_never_leak_across_users(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, other_auth_headers)
    transport_id = await _get_category_id(client, other_auth_headers, "Transport")
    now = datetime.now(UTC)
    last_month_reference = now.replace(day=1) - timedelta(days=1)
    await _create_transaction(
        client, other_auth_headers, account_id=account["id"], type="expense", amount_minor=999999,
        category_id=transport_id, occurred_at=last_month_reference.isoformat(),
    )

    response = await client.get("/api/v1/budgets/suggestions", headers=auth_headers)
    for suggestion in response.json()["data"]:
        assert suggestion["suggested_amount_minor"] != 999999
