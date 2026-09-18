"""Endpoint-level tests for /api/v1/merchant-rules - ownership, the
upsert-not-duplicate behavior, and validation."""

from httpx import AsyncClient


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def _create_rule(client: AsyncClient, headers: dict, *, merchant: str, category_id: str):
    response = await client.post(
        "/api/v1/merchant-rules",
        headers=headers,
        json={"merchant": merchant, "category_id": category_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# --- CRUD --------------------------------------------------------------------


async def test_create_merchant_rule(client: AsyncClient, auth_headers: dict) -> None:
    education_id = await _get_category_id(client, auth_headers, "Education")
    rule = await _create_rule(
        client, auth_headers, merchant="UPI/DR/399/ABC EDUCATION PVT LTD", category_id=education_id
    )
    assert rule["merchant_key"] == "Abc Education"  # normalized, not the raw narration
    assert rule["category_id"] == education_id
    assert rule["category_name"] == "Education"


async def test_list_own_rules(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.get("/api/v1/merchant-rules", headers=auth_headers)
    assert response.status_code == 200
    rules = response.json()["data"]
    assert response.json()["meta"]["count"] == len(rules)
    assert any(r["merchant_key"] == "Swiggy" for r in rules)


async def test_update_own_rule(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    shopping_id = await _get_category_id(client, auth_headers, "Shopping")
    rule = await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.patch(
        f"/api/v1/merchant-rules/{rule['id']}",
        headers=auth_headers,
        json={"category_id": shopping_id},
    )
    assert response.status_code == 200
    assert response.json()["data"]["category_id"] == shopping_id
    assert response.json()["data"]["merchant_key"] == "Swiggy"


async def test_delete_own_rule(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    rule = await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.delete(f"/api/v1/merchant-rules/{rule['id']}", headers=auth_headers)
    assert response.status_code == 200

    listed = await client.get("/api/v1/merchant-rules", headers=auth_headers)
    assert listed.json()["data"] == []


# --- ownership -----------------------------------------------------------------


async def test_user_b_cannot_view_user_a_rule(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    rule = await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.get(f"/api/v1/merchant-rules/{rule['id']}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_user_b_cannot_update_user_a_rule(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    their_shopping_id = await _get_category_id(client, other_auth_headers, "Shopping")
    rule = await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.patch(
        f"/api/v1/merchant-rules/{rule['id']}",
        headers=other_auth_headers,
        json={"category_id": their_shopping_id},
    )
    assert response.status_code == 404


async def test_user_b_cannot_delete_user_a_rule(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    rule = await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.delete(
        f"/api/v1/merchant-rules/{rule['id']}", headers=other_auth_headers
    )
    assert response.status_code == 404

    # User A's rule is untouched.
    still_there = await client.get(f"/api/v1/merchant-rules/{rule['id']}", headers=auth_headers)
    assert still_there.status_code == 200


async def test_user_b_rule_list_never_includes_user_a_rules(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)

    response = await client.get("/api/v1/merchant-rules", headers=other_auth_headers)
    assert response.json()["data"] == []


async def test_different_users_can_have_different_rules_for_the_same_merchant(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    shopping_id = await _get_category_id(client, other_auth_headers, "Shopping")

    mine = await _create_rule(client, auth_headers, merchant="Swiggy", category_id=food_id)
    theirs = await _create_rule(
        client, other_auth_headers, merchant="Swiggy", category_id=shopping_id
    )

    assert mine["category_name"] == "Food"
    assert theirs["category_name"] == "Shopping"

    mine_listed = await client.get("/api/v1/merchant-rules", headers=auth_headers)
    theirs_listed = await client.get("/api/v1/merchant-rules", headers=other_auth_headers)
    assert [r["id"] for r in mine_listed.json()["data"]] == [mine["id"]]
    assert [r["id"] for r in theirs_listed.json()["data"]] == [theirs["id"]]


# --- upsert / duplicate handling ------------------------------------------------


async def test_duplicate_user_merchant_rule_updates_instead_of_duplicating(
    client: AsyncClient, auth_headers: dict
) -> None:
    shopping_id = await _get_category_id(client, auth_headers, "Shopping")
    education_id = await _get_category_id(client, auth_headers, "Education")

    first = await _create_rule(
        client, auth_headers, merchant="ABC EDUCATION", category_id=shopping_id
    )
    second = await _create_rule(
        client, auth_headers, merchant="ABC EDUCATION", category_id=education_id
    )

    assert first["id"] == second["id"]  # same row, repointed - never a duplicate
    assert second["category_id"] == education_id

    listed = await client.get("/api/v1/merchant-rules", headers=auth_headers)
    matching = [r for r in listed.json()["data"] if r["merchant_key"] == "Abc Education"]
    assert len(matching) == 1


# --- validation ------------------------------------------------------------------


async def test_create_rule_rejects_extra_fields(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    response = await client.post(
        "/api/v1/merchant-rules",
        headers=auth_headers,
        json={"merchant": "Swiggy", "category_id": food_id, "pin": "1234"},
    )
    assert response.status_code == 422


async def test_create_rule_rejects_nonexistent_category(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/merchant-rules",
        headers=auth_headers,
        json={"merchant": "Swiggy", "category_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 422


async def test_create_rule_rejects_another_users_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/categories",
        headers=other_auth_headers,
        json={"name": "Their Custom Category", "icon": "🎯", "color": "#123456"},
    )
    their_category_id = response.json()["data"]["id"]

    result = await client.post(
        "/api/v1/merchant-rules",
        headers=auth_headers,
        json={"merchant": "Swiggy", "category_id": their_category_id},
    )
    assert result.status_code == 422


async def test_unauthenticated_requests_are_rejected(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/merchant-rules")).status_code == 401
    assert (await client.post("/api/v1/merchant-rules", json={})).status_code == 401
