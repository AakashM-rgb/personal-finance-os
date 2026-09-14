from httpx import AsyncClient


async def test_register_creates_user_and_returns_access_token(
    client: AsyncClient, register_payload: dict
) -> None:
    response = await client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user"]["email"] == register_payload["email"]
    assert "access_token" in body
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert "refresh_token" in response.cookies


async def test_register_rejects_duplicate_email(
    client: AsyncClient, register_payload: dict
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    response = await client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_register_rejects_weak_password(client: AsyncClient, register_payload: dict) -> None:
    register_payload["password"] = "short"
    response = await client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 422


async def test_login_succeeds_with_correct_credentials(
    client: AsyncClient, register_payload: dict
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": register_payload["email"], "password": register_payload["password"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == register_payload["email"]


async def test_login_rejects_wrong_password(client: AsyncClient, register_payload: dict) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": register_payload["email"], "password": "totally-wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_login_rejects_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_returns_the_authenticated_user_only(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    access_token = register_response.json()["data"]["access_token"]

    other_user = {
        "email": "other.user@example.com",
        "password": "correcthorse123",
        "full_name": "Other User",
    }
    await client.post("/api/v1/auth/register", json=other_user)

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    # Must return the token owner's own data, never the other registered user's.
    assert response.json()["data"]["email"] == register_payload["email"]


async def test_refresh_requires_csrf_token(client: AsyncClient, register_payload: dict) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


async def test_refresh_rotates_tokens_and_revokes_the_old_one(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    old_refresh_cookie = register_response.cookies["refresh_token"]
    csrf_token = register_response.cookies["csrf_token"]

    refresh_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token}
    )
    assert refresh_response.status_code == 200
    new_refresh_cookie = refresh_response.cookies["refresh_token"]
    new_csrf_token = refresh_response.cookies["csrf_token"]
    assert new_refresh_cookie != old_refresh_cookie

    # The rotated-out refresh token must no longer work, even with a valid CSRF token.
    client.cookies.set("refresh_token", old_refresh_cookie)
    replay_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": new_csrf_token}
    )
    assert replay_response.status_code == 401


async def test_logout_revokes_session_so_refresh_then_fails(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    csrf_token = register_response.cookies["csrf_token"]

    logout_response = await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf_token})
    assert logout_response.status_code == 200

    refresh_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token}
    )
    assert refresh_response.status_code == 401
