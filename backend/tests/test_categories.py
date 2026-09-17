from httpx import AsyncClient


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


async def test_new_user_sees_default_system_categories(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.get("/api/v1/categories", headers=auth_headers)
    assert response.status_code == 200
    categories = response.json()["data"]
    names = {c["name"] for c in categories}
    assert {"Food", "Transport", "Rent", "Other"}.issubset(names)
    assert all(c["is_system"] for c in categories)


async def test_create_custom_category(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#a3e635"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["name"] == "Pet Care"
    assert data["color"] == "#A3E635"  # normalized to uppercase
    assert data["is_system"] is False
    assert data["is_active"] is True


async def test_create_category_rejects_invalid_color(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "not-a-color"},
    )
    assert response.status_code == 422


async def test_create_category_with_valid_parent(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Fine Dining", "icon": "🍽️", "color": "#F97316", "parent_id": food_id},
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["parent_id"] == food_id


async def test_create_category_with_unknown_parent_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={
            "name": "Fine Dining",
            "icon": "🍽️",
            "color": "#F97316",
            "parent_id": "00000000-0000-0000-0000-00000000ffff",
        },
    )
    assert response.status_code == 422


async def test_update_own_category(client: AsyncClient, auth_headers: dict) -> None:
    create_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    category_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/categories/{category_id}",
        headers=auth_headers,
        json={"name": "Pet Supplies", "budget_minor": 200000},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Pet Supplies"
    assert data["budget_minor"] == 200000


async def test_cannot_update_system_category(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    response = await client.put(
        f"/api/v1/categories/{food_id}",
        headers=auth_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 403


async def test_cannot_delete_system_category(client: AsyncClient, auth_headers: dict) -> None:
    food_id = await _get_category_id(client, auth_headers, "Food")
    response = await client.delete(f"/api/v1/categories/{food_id}", headers=auth_headers)
    assert response.status_code == 403


async def test_cannot_update_other_users_category(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    category_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/categories/{category_id}",
        headers=other_auth_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


async def test_self_parent_rejected(client: AsyncClient, auth_headers: dict) -> None:
    create_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    category_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/categories/{category_id}",
        headers=auth_headers,
        json={"parent_id": category_id},
    )
    assert response.status_code == 422


async def test_parent_cycle_rejected(client: AsyncClient, auth_headers: dict) -> None:
    parent_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Parent", "icon": "📁", "color": "#111111"},
    )
    parent_id = parent_response.json()["data"]["id"]

    child_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Child", "icon": "📁", "color": "#222222", "parent_id": parent_id},
    )
    child_id = child_response.json()["data"]["id"]

    # Trying to make Parent a child of its own child must be rejected.
    response = await client.put(
        f"/api/v1/categories/{parent_id}",
        headers=auth_headers,
        json={"parent_id": child_id},
    )
    assert response.status_code == 422


async def test_delete_category_soft_deletes_and_hides_from_default_list(
    client: AsyncClient, auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    category_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(
        f"/api/v1/categories/{category_id}", headers=auth_headers
    )
    assert delete_response.status_code == 200

    list_response = await client.get("/api/v1/categories", headers=auth_headers)
    ids = [c["id"] for c in list_response.json()["data"]]
    assert category_id not in ids

    get_response = await client.get(f"/api/v1/categories/{category_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["is_active"] is False


async def test_custom_categories_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Mine Only", "icon": "🔒", "color": "#000000"},
    )

    theirs_response = await client.get("/api/v1/categories", headers=other_auth_headers)
    names = {c["name"] for c in theirs_response.json()["data"]}
    assert "Mine Only" not in names


async def test_duplicate_category_name_for_same_user_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    first = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐾", "color": "#123456"},
    )
    assert second.status_code == 409, second.text
    error = second.json()["error"]
    assert error["code"] == "conflict"


async def test_same_category_name_allowed_for_different_users(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    mine = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    assert mine.status_code == 201, mine.text

    theirs = await client.post(
        "/api/v1/categories",
        headers=other_auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    assert theirs.status_code == 201, theirs.text


async def test_system_categories_unaffected_by_duplicate_name_constraint(
    client: AsyncClient, auth_headers: dict
) -> None:
    # System categories (user_id IS NULL) are seeded with distinct names and
    # remain readable/listable as before - the new per-user uniqueness rule
    # must not raise on the normal list/read path for them.
    list_response = await client.get("/api/v1/categories", headers=auth_headers)
    assert list_response.status_code == 200
    names = [c["name"] for c in list_response.json()["data"]]
    assert len(names) == len(set(names))


async def test_renaming_category_to_existing_name_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    other = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Supplies", "icon": "🐾", "color": "#123456"},
    )
    other_id = other.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/categories/{other_id}",
        headers=auth_headers,
        json={"name": "Pet Care"},
    )
    assert response.status_code == 409, response.text


async def test_renaming_category_to_own_current_name_is_a_noop(
    client: AsyncClient, auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    category_id = create_response.json()["data"]["id"]

    response = await client.put(
        f"/api/v1/categories/{category_id}",
        headers=auth_headers,
        json={"name": "Pet Care", "budget_minor": 100000},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "Pet Care"


async def test_deleted_category_name_can_be_reused(
    client: AsyncClient, auth_headers: dict
) -> None:
    create_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    category_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(
        f"/api/v1/categories/{category_id}", headers=auth_headers
    )
    assert delete_response.status_code == 200

    recreate_response = await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Pet Care", "icon": "🐶", "color": "#A3E635"},
    )
    assert recreate_response.status_code == 201, recreate_response.text


async def test_concurrent_duplicate_category_creation_cannot_both_succeed(
    client: AsyncClient, auth_headers: dict
) -> None:
    import asyncio

    payload = {"name": "Race Category", "icon": "🏁", "color": "#654321"}
    responses = await asyncio.gather(
        client.post("/api/v1/categories", headers=auth_headers, json=payload),
        client.post("/api/v1/categories", headers=auth_headers, json=payload),
    )
    status_codes = sorted(r.status_code for r in responses)
    assert status_codes == [201, 409], [r.text for r in responses]

    list_response = await client.get("/api/v1/categories", headers=auth_headers)
    matching = [c for c in list_response.json()["data"] if c["name"] == "Race Category"]
    assert len(matching) == 1
