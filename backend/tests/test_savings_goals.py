from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


def _iso_date(dt: datetime) -> str:
    return dt.date().isoformat()


async def _create_goal(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {
        "name": "New Laptop",
        "target_amount_minor": 15000000,
        "current_amount_minor": 4500000,
        "currency": "INR",
        "target_date": _iso_date(datetime.now(UTC) + timedelta(days=300)),
    }
    payload.update(overrides)
    response = await client.post("/api/v1/goals", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


# --- creation / validation ---------------------------------------------------------


async def test_create_goal_matches_spec_example(client: AsyncClient, auth_headers: dict) -> None:
    goal = await _create_goal(client, auth_headers)

    assert goal["name"] == "New Laptop"
    assert goal["target_amount_minor"] == 15000000
    assert goal["current_amount_minor"] == 4500000
    assert goal["currency"] == "INR"
    assert goal["remaining_minor"] == 10500000  # Rs. 1,05,000
    assert goal["progress_percent"] == 30.0
    assert goal["is_completed"] is False


async def test_create_rejects_current_amount_over_target(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Overfunded",
            "target_amount_minor": 10000,
            "current_amount_minor": 20000,
            "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_zero_or_negative_target(
    client: AsyncClient, auth_headers: dict
) -> None:
    for bad_amount in [0, -500]:
        response = await client.post(
            "/api/v1/goals",
            headers=auth_headers,
            json={
                "name": "Bad target",
                "target_amount_minor": bad_amount,
                "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
            },
        )
        assert response.status_code == 422


async def test_create_rejects_negative_current_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Bad current",
            "target_amount_minor": 10000,
            "current_amount_minor": -1,
            "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_blank_name(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "",
            "target_amount_minor": 10000,
            "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
        },
    )
    assert response.status_code == 422


async def test_create_rejects_unsupported_currency(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Bad currency",
            "target_amount_minor": 10000,
            "currency": "XXX",
            "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
        },
    )
    assert response.status_code == 422


async def test_create_requires_target_date(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={"name": "No date", "target_amount_minor": 10000},
    )
    assert response.status_code == 422


async def test_create_rejects_unknown_fields(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/goals",
        headers=auth_headers,
        json={
            "name": "Extra field",
            "target_amount_minor": 10000,
            "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
            "user_id": "00000000-0000-0000-0000-00000000ffff",
        },
    )
    assert response.status_code == 422


async def test_create_defaults_current_amount_to_zero(
    client: AsyncClient, auth_headers: dict
) -> None:
    # current_amount_minor omitted entirely -> defaults to 0.
    payload = {
        "name": "Fresh start",
        "target_amount_minor": 10000,
        "target_date": _iso_date(datetime.now(UTC) + timedelta(days=30)),
    }
    response = await client.post("/api/v1/goals", headers=auth_headers, json=payload)
    assert response.status_code == 201
    fresh = response.json()["data"]
    assert fresh["current_amount_minor"] == 0
    assert fresh["progress_percent"] == 0.0


# --- CRUD ---------------------------------------------------------------------------


async def test_list_goals_starts_empty(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/goals", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_get_goal_by_id(client: AsyncClient, auth_headers: dict) -> None:
    created = await _create_goal(client, auth_headers)
    response = await client.get(f"/api/v1/goals/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


async def test_get_unknown_goal_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/goals/00000000-0000-0000-0000-00000000ffff", headers=auth_headers
    )
    assert response.status_code == 404


async def test_update_goal_amounts_and_name(client: AsyncClient, auth_headers: dict) -> None:
    created = await _create_goal(client, auth_headers)
    response = await client.put(
        f"/api/v1/goals/{created['id']}",
        headers=auth_headers,
        json={"name": "New Laptop (updated)", "current_amount_minor": 6000000},
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["name"] == "New Laptop (updated)"
    assert updated["current_amount_minor"] == 6000000
    assert updated["target_amount_minor"] == 15000000  # untouched


async def test_update_rejects_current_amount_pushed_over_target(
    client: AsyncClient, auth_headers: dict
) -> None:
    created = await _create_goal(
        client, auth_headers, target_amount_minor=10000, current_amount_minor=5000
    )
    response = await client.put(
        f"/api/v1/goals/{created['id']}",
        headers=auth_headers,
        json={"current_amount_minor": 20000},
    )
    assert response.status_code == 422


async def test_update_rejects_target_amount_dropped_below_current(
    client: AsyncClient, auth_headers: dict
) -> None:
    created = await _create_goal(
        client, auth_headers, target_amount_minor=10000, current_amount_minor=8000
    )
    response = await client.put(
        f"/api/v1/goals/{created['id']}",
        headers=auth_headers,
        json={"target_amount_minor": 5000},
    )
    assert response.status_code == 422


async def test_update_unknown_goal_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.put(
        "/api/v1/goals/00000000-0000-0000-0000-00000000ffff",
        headers=auth_headers,
        json={"name": "Nope"},
    )
    assert response.status_code == 404


async def test_delete_goal(client: AsyncClient, auth_headers: dict) -> None:
    created = await _create_goal(client, auth_headers)
    response = await client.delete(f"/api/v1/goals/{created['id']}", headers=auth_headers)
    assert response.status_code == 200

    follow_up = await client.get(f"/api/v1/goals/{created['id']}", headers=auth_headers)
    assert follow_up.status_code == 404


async def test_delete_unknown_goal_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.delete(
        "/api/v1/goals/00000000-0000-0000-0000-00000000ffff", headers=auth_headers
    )
    assert response.status_code == 404


# --- authorization isolation --------------------------------------------------------


async def test_cannot_read_another_users_goal(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _create_goal(client, other_auth_headers)
    response = await client.get(f"/api/v1/goals/{theirs['id']}", headers=auth_headers)
    assert response.status_code == 404


async def test_cannot_update_another_users_goal(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _create_goal(client, other_auth_headers)
    response = await client.put(
        f"/api/v1/goals/{theirs['id']}",
        headers=auth_headers,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


async def test_cannot_delete_another_users_goal(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _create_goal(client, other_auth_headers)
    response = await client.delete(f"/api/v1/goals/{theirs['id']}", headers=auth_headers)
    assert response.status_code == 404

    still_there = await client.get(f"/api/v1/goals/{theirs['id']}", headers=other_auth_headers)
    assert still_there.status_code == 200


async def test_list_never_leaks_another_users_goals(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await _create_goal(client, other_auth_headers, name="Their goal")
    await _create_goal(client, auth_headers, name="My goal")

    response = await client.get("/api/v1/goals", headers=auth_headers)
    names = [goal["name"] for goal in response.json()["data"]]
    assert names == ["My goal"]


# --- edge cases: dates and completion -----------------------------------------------


async def test_goal_already_completed(client: AsyncClient, auth_headers: dict) -> None:
    goal = await _create_goal(
        client, auth_headers, target_amount_minor=10000, current_amount_minor=10000
    )
    assert goal["is_completed"] is True
    assert goal["remaining_minor"] == 0
    assert goal["progress_percent"] == 100.0
    assert goal["required_monthly_savings_minor"] == 0
    assert goal["required_weekly_savings_minor"] == 0


async def test_goal_completed_even_with_a_past_target_date(
    client: AsyncClient, auth_headers: dict
) -> None:
    goal = await _create_goal(
        client,
        auth_headers,
        target_amount_minor=10000,
        current_amount_minor=10000,
        target_date=_iso_date(datetime.now(UTC) - timedelta(days=10)),
    )
    assert goal["is_completed"] is True
    assert goal["days_remaining"] < 0
    assert goal["required_monthly_savings_minor"] == 0
    assert goal["required_weekly_savings_minor"] == 0


async def test_target_date_today_with_remaining_balance(
    client: AsyncClient, auth_headers: dict
) -> None:
    goal = await _create_goal(
        client,
        auth_headers,
        target_amount_minor=10000,
        current_amount_minor=4000,
        target_date=_iso_date(datetime.now(UTC)),
    )
    assert goal["days_remaining"] == 0
    assert goal["is_completed"] is False
    assert goal["required_monthly_savings_minor"] is None
    assert goal["required_weekly_savings_minor"] is None


async def test_target_date_in_the_past_with_remaining_balance(
    client: AsyncClient, auth_headers: dict
) -> None:
    goal = await _create_goal(
        client,
        auth_headers,
        target_amount_minor=10000,
        current_amount_minor=4000,
        target_date=_iso_date(datetime.now(UTC) - timedelta(days=5)),
    )
    assert goal["days_remaining"] == -5
    assert goal["is_completed"] is False
    assert goal["required_monthly_savings_minor"] is None
    assert goal["required_weekly_savings_minor"] is None


async def test_zero_current_amount(client: AsyncClient, auth_headers: dict) -> None:
    goal = await _create_goal(client, auth_headers, current_amount_minor=0)
    assert goal["progress_percent"] == 0.0
    assert goal["remaining_minor"] == goal["target_amount_minor"]
    assert goal["is_completed"] is False


async def test_current_amount_equal_to_target_amount(
    client: AsyncClient, auth_headers: dict
) -> None:
    goal = await _create_goal(
        client, auth_headers, target_amount_minor=50000, current_amount_minor=50000
    )
    assert goal["progress_percent"] == 100.0
    assert goal["remaining_minor"] == 0
    assert goal["is_completed"] is True


async def test_very_small_remaining_amount_rounds_to_zero_per_period(
    client: AsyncClient, auth_headers: dict
) -> None:
    goal = await _create_goal(
        client,
        auth_headers,
        target_amount_minor=100000,
        current_amount_minor=99999,
        target_date=_iso_date(datetime.now(UTC) + timedelta(days=365)),
    )
    assert goal["remaining_minor"] == 1
    assert goal["required_monthly_savings_minor"] == 0
    assert goal["required_weekly_savings_minor"] == 0


async def test_required_savings_pace_for_a_future_target_date(
    client: AsyncClient, auth_headers: dict
) -> None:
    goal = await _create_goal(
        client,
        auth_headers,
        target_amount_minor=15000000,
        current_amount_minor=4500000,
        target_date=_iso_date(datetime.now(UTC) + timedelta(days=300)),
    )
    assert goal["remaining_minor"] == 10500000
    assert goal["required_monthly_savings_minor"] == 1050000
    assert goal["required_weekly_savings_minor"] == 245000
