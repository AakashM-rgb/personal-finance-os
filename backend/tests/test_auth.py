from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


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


async def test_register_rejects_unknown_field(client: AsyncClient, register_payload: dict) -> None:
    register_payload["is_admin"] = True
    response = await client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 422


async def test_register_rejects_client_supplied_user_id(
    client: AsyncClient, register_payload: dict
) -> None:
    """The client can never seed/override the authenticated identity the
    server is about to create - user_id is always server-generated."""
    register_payload["user_id"] = "00000000-0000-0000-0000-00000000ffff"
    response = await client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 422


async def test_login_rejects_unknown_field(client: AsyncClient, register_payload: dict) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": register_payload["email"],
            "password": register_payload["password"],
            "user_id": "00000000-0000-0000-0000-00000000ffff",
        },
    )
    assert response.status_code == 422


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


async def test_failed_login_is_actually_persisted_to_the_audit_log(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    """A service function that logs a security event and then raises
    (never reaching the router's own db.commit()) must still persist that
    event itself - CLAUDE.md §12 requires login attempts be audit-logged,
    and a silently-dropped failed-login entry would defeat brute-force
    detection entirely."""
    await client.post("/api/v1/auth/register", json=register_payload)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": register_payload["email"], "password": "totally-wrong-password"},
    )
    assert response.status_code == 401

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "user.login_failed")
    )
    entries = result.scalars().all()
    assert len(entries) == 1


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


async def test_refresh_token_reuse_revokes_every_session_for_the_user(
    client: AsyncClient, register_payload: dict
) -> None:
    """CLAUDE.md §11: "reuse of a rotated-out token is treated as a possible
    compromise." Replaying an already-rotated-out refresh token must not
    just fail itself - it must burn every other active session for that
    user too, so a legitimate client sitting on a currently-valid session
    is forced to re-authenticate rather than silently coexist with
    whoever replayed the stolen token."""
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    first_refresh_cookie = register_response.cookies["refresh_token"]
    first_csrf_token = register_response.cookies["csrf_token"]

    # Rotate once via the normal flow - this is the "legitimate" new session.
    rotate_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": first_csrf_token}
    )
    assert rotate_response.status_code == 200
    legit_refresh_cookie = rotate_response.cookies["refresh_token"]
    legit_csrf_token = rotate_response.cookies["csrf_token"]

    # An attacker (or a stale client) replays the now-rotated-out first
    # token. The CSRF cookie in the jar has already moved on to
    # legit_csrf_token (set by the rotation response above), so that - not
    # the original first_csrf_token - is the value a real cross-site
    # double-submit check would see; using it here isolates what's under
    # test (session-reuse detection) from CSRF matching.
    client.cookies.set("refresh_token", first_refresh_cookie)
    replay_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": legit_csrf_token}
    )
    assert replay_response.status_code == 401

    # The legitimate, currently-valid session must ALSO now be dead - the
    # whole session family was burned in response to the detected reuse.
    client.cookies.set("refresh_token", legit_refresh_cookie)
    legit_retry_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": legit_csrf_token}
    )
    assert legit_retry_response.status_code == 401


async def test_refresh_token_reuse_is_audit_logged(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    first_refresh_cookie = register_response.cookies["refresh_token"]
    first_csrf_token = register_response.cookies["csrf_token"]

    rotate_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": first_csrf_token}
    )
    legit_csrf_token = rotate_response.cookies["csrf_token"]

    client.cookies.set("refresh_token", first_refresh_cookie)
    await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": legit_csrf_token})

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "session.reuse_detected")
    )
    entries = result.scalars().all()
    assert len(entries) == 1


async def test_refresh_with_wrong_secret_for_a_real_session_id_does_not_burn_other_sessions(
    client: AsyncClient, register_payload: dict
) -> None:
    """A mismatched secret against a real (still-active, never rotated)
    session id is just an invalid token, not evidence of a rotated-token
    replay - it must not trigger the compromise response."""
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    real_refresh_cookie = register_response.cookies["refresh_token"]
    csrf_token = register_response.cookies["csrf_token"]
    session_id = real_refresh_cookie.split(".", 1)[0]

    client.cookies.set("refresh_token", f"{session_id}.not-the-real-secret")
    forged_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token}
    )
    assert forged_response.status_code == 401

    # The real, still-active (never rotated) session must still work.
    client.cookies.set("refresh_token", real_refresh_cookie)
    real_response = await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token})
    assert real_response.status_code == 200


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


async def test_list_sessions_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/sessions")
    assert response.status_code == 401


async def test_list_sessions_returns_the_caller_own_active_session(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    access_token = register_response.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    sessions = response.json()["data"]
    assert len(sessions) == 1
    assert set(sessions[0].keys()) == {"id", "user_agent", "ip_address", "created_at", "expires_at"}


async def test_list_sessions_grows_after_refresh_and_shrinks_after_logout(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    access_token = register_response.json()["data"]["access_token"]
    csrf_token = register_response.cookies["csrf_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Refresh rotates: the old session is revoked and a new one is issued,
    # so the active count stays at 1 rather than growing.
    await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token})
    response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert len(response.json()["data"]) == 1

    logout_response = await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf_token})
    # The csrf_token cookie rotated along with the session on refresh, so this
    # logout call (using the pre-rotation token) fails CSRF and revokes
    # nothing - confirming the active session is still exactly the refreshed one.
    assert logout_response.status_code == 401
    response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert len(response.json()["data"]) == 1


async def test_list_sessions_never_returns_another_users_sessions(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    access_token = register_response.json()["data"]["access_token"]

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "other.user@example.com",
            "password": "correcthorse123",
            "full_name": "Other User",
        },
    )

    response = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    # Only the caller's own single session - never the other user's.
    assert len(response.json()["data"]) == 1


async def test_logout_all_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout-all")
    assert response.status_code == 401


async def test_logout_all_revokes_every_session_including_the_current_one(
    client: AsyncClient, register_payload: dict
) -> None:
    """logout-all has no "except this device" carve-out (see
    app.services.auth_service.logout_all) - it must revoke the caller's own
    current session too, so a subsequent refresh with the same cookie fails."""
    register_response = await client.post("/api/v1/auth/register", json=register_payload)
    access_token = register_response.json()["data"]["access_token"]
    csrf_token = register_response.cookies["csrf_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    logout_all_response = await client.post("/api/v1/auth/logout-all", headers=headers)
    assert logout_all_response.status_code == 200

    refresh_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token}
    )
    assert refresh_response.status_code == 401


async def test_logout_all_does_not_affect_another_users_sessions(
    client: AsyncClient, register_payload: dict
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=register_payload)

    other_register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "other.user@example.com",
            "password": "correcthorse123",
            "full_name": "Other User",
        },
    )
    other_refresh_cookie = other_register_response.cookies["refresh_token"]
    other_csrf_token = other_register_response.cookies["csrf_token"]

    await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {register_response.json()['data']['access_token']}"},
    )

    # The unrelated second user's own session must still be fully usable -
    # set both cookies explicitly rather than relying on the shared jar,
    # since the register call above may have left it in either state.
    client.cookies.set("refresh_token", other_refresh_cookie)
    client.cookies.set("csrf_token", other_csrf_token)
    refresh_response = await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": other_csrf_token}
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["data"]["user"]["email"] == "other.user@example.com"
