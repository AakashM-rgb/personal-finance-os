from httpx import AsyncClient


async def test_get_settings_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/settings")
    assert response.status_code == 401


async def test_get_settings_returns_defaults_for_a_new_user(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.get("/api/v1/settings", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == {"currency": "INR", "theme": "system", "ai_enabled": True}


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
    assert response.json()["data"] == {"currency": "EUR", "theme": "light", "ai_enabled": True}


async def test_settings_are_isolated_per_user(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await client.patch("/api/v1/settings", headers=auth_headers, json={"currency": "GBP"})

    own_response = await client.get("/api/v1/settings", headers=auth_headers)
    other_response = await client.get("/api/v1/settings", headers=other_auth_headers)

    assert own_response.json()["data"]["currency"] == "GBP"
    # The second user's own settings must be untouched by the first user's change.
    assert other_response.json()["data"]["currency"] == "INR"
