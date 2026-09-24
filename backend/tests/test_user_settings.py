from httpx import AsyncClient

DEFAULT_NOTIFICATION_PREFERENCES = {
    "budget_warnings": True,
    "payment_reminders": True,
    "goal_milestones": True,
    "unusual_spending": True,
    "recurring_reminders": True,
}


async def test_get_settings_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/settings")
    assert response.status_code == 401


async def test_get_settings_returns_defaults_for_a_new_user(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.get("/api/v1/settings", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "currency": "INR",
        "theme": "system",
        "ai_enabled": True,
        "ai_categorization_enabled": False,
        "notification_preferences": DEFAULT_NOTIFICATION_PREFERENCES,
    }


async def test_patch_settings_requires_authentication(client: AsyncClient) -> None:
    response = await client.patch("/api/v1/settings", json={"currency": "USD"})
    assert response.status_code == 401


async def test_patch_settings_updates_currency(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"currency": "USD"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["currency"] == "USD"

    get_response = await client.get("/api/v1/settings", headers=auth_headers)
    assert get_response.json()["data"]["currency"] == "USD"


async def test_patch_settings_rejects_unsupported_currency(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"currency": "XYZ"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_patch_settings_updates_theme(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.patch("/api/v1/settings", headers=auth_headers, json={"theme": "dark"})
    assert response.status_code == 200
    assert response.json()["data"]["theme"] == "dark"

    get_response = await client.get("/api/v1/settings", headers=auth_headers)
    assert get_response.json()["data"]["theme"] == "dark"


async def test_patch_settings_rejects_invalid_theme(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"theme": "midnight"}
    )
    assert response.status_code == 422


async def test_patch_settings_toggles_ai_enabled(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["data"]["ai_enabled"] is False

    get_response = await client.get("/api/v1/settings", headers=auth_headers)
    assert get_response.json()["data"]["ai_enabled"] is False


async def test_disabling_ai_actually_blocks_the_assistant(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The whole point of this setting: it must gate real tool access, not
    just be a UI-only flag (see app.services.ai_assistant_service). Disabled
    AI access is refused in-band with a 200 explaining why - not an HTTP
    error - and crucially no tool is ever invoked."""
    await client.patch("/api/v1/settings", headers=auth_headers, json={"ai_enabled": False})

    response = await client.post(
        "/api/v1/ai/assistant", headers=auth_headers, json={"message": "How much did I spend?"}
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["tools_used"] == []
    assert "turned off" in body["answer"].lower()


async def test_ai_categorization_enabled_defaults_to_false(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.get("/api/v1/settings", headers=auth_headers)
    assert response.json()["data"]["ai_categorization_enabled"] is False


async def test_patch_settings_enables_ai_categorization(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    assert response.status_code == 200
    assert response.json()["data"]["ai_categorization_enabled"] is True

    get_response = await client.get("/api/v1/settings", headers=auth_headers)
    assert get_response.json()["data"]["ai_categorization_enabled"] is True


async def test_patch_settings_disables_ai_categorization_again(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["data"]["ai_categorization_enabled"] is False

    get_response = await client.get("/api/v1/settings", headers=auth_headers)
    assert get_response.json()["data"]["ai_categorization_enabled"] is False


async def test_ai_categorization_enabled_is_independent_of_ai_enabled(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The two AI settings must never move together - one PATCH only ever
    changes the field it names (see app.services.user_settings_service)."""
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_enabled": False}
    )
    assert response.json()["data"]["ai_enabled"] is False
    assert response.json()["data"]["ai_categorization_enabled"] is False

    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    assert response.json()["data"]["ai_categorization_enabled"] is True
    # ai_enabled must remain untouched by the ai_categorization_enabled patch.
    assert response.json()["data"]["ai_enabled"] is False


async def test_ai_categorization_enabled_is_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )

    own_response = await client.get("/api/v1/settings", headers=auth_headers)
    other_response = await client.get("/api/v1/settings", headers=other_auth_headers)

    assert own_response.json()["data"]["ai_categorization_enabled"] is True
    # The second user's own setting must be untouched by the first user's change.
    assert other_response.json()["data"]["ai_categorization_enabled"] is False


async def test_settings_response_never_exposes_an_anthropic_api_key(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Phase F4 (Test Area 13): the AI categorization toggle is a plain
    boolean - the server-side ANTHROPIC_API_KEY (app.core.config) must
    never appear on this or any other user-facing response, in any field
    name or value."""
    response = await client.get("/api/v1/settings", headers=auth_headers)
    data = response.json()["data"]

    assert set(data) == {
        "currency",
        "theme",
        "ai_enabled",
        "ai_categorization_enabled",
        "notification_preferences",
    }
    for key in data:
        assert "key" not in key.lower()
        assert "secret" not in key.lower()
        assert "anthropic" not in key.lower()


async def test_patch_settings_rejects_unknown_field(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"is_admin": True}
    )
    assert response.status_code == 422


async def test_patch_settings_partial_update_leaves_other_fields_untouched(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.patch("/api/v1/settings", headers=auth_headers, json={"currency": "EUR"})
    response = await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"theme": "light"}
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "currency": "EUR",
        "theme": "light",
        "ai_enabled": True,
        "ai_categorization_enabled": False,
        "notification_preferences": DEFAULT_NOTIFICATION_PREFERENCES,
    }


async def test_patch_settings_disables_one_notification_category(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"budget_warnings": False}},
    )
    assert response.status_code == 200
    prefs = response.json()["data"]["notification_preferences"]
    assert prefs["budget_warnings"] is False
    # Every other category is left exactly as it was - a partial patch,
    # not a wholesale replace.
    assert prefs["payment_reminders"] is True
    assert prefs["goal_milestones"] is True
    assert prefs["unusual_spending"] is True
    assert prefs["recurring_reminders"] is True

    get_response = await client.get("/api/v1/settings", headers=auth_headers)
    assert get_response.json()["data"]["notification_preferences"]["budget_warnings"] is False


async def test_patch_settings_re_enables_a_disabled_category(
    client: AsyncClient, auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"unusual_spending": False}},
    )
    response = await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"unusual_spending": True}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["notification_preferences"]["unusual_spending"] is True


async def test_patch_settings_rejects_unknown_notification_preference_field(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"totally_made_up_category": False}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_patch_settings_rejects_non_boolean_notification_preference_value(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"budget_warnings": "yes please"}},
    )
    assert response.status_code == 422


async def test_notification_preferences_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={"notification_preferences": {"budget_warnings": False}},
    )

    own_response = await client.get("/api/v1/settings", headers=auth_headers)
    other_response = await client.get("/api/v1/settings", headers=other_auth_headers)

    assert own_response.json()["data"]["notification_preferences"]["budget_warnings"] is False
    assert other_response.json()["data"]["notification_preferences"]["budget_warnings"] is True


async def test_settings_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.patch("/api/v1/settings", headers=auth_headers, json={"currency": "GBP"})

    own_response = await client.get("/api/v1/settings", headers=auth_headers)
    other_response = await client.get("/api/v1/settings", headers=other_auth_headers)

    assert own_response.json()["data"]["currency"] == "GBP"
    # The second user's own settings must be untouched by the first user's change.
    assert other_response.json()["data"]["currency"] == "INR"
