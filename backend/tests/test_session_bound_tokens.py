"""Access tokens bound to a session family (H2): revoking a session cuts off
its access tokens immediately, while refresh-token rotation - including the
rotations other tabs sharing the cookie trigger - never does."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import TokenType, decode_token
from app.models.session import Session
from app.models.user import User

settings = get_settings()

ME_URL = "/api/v1/auth/me"


def _token(response: Response) -> str:
    return response.json()["data"]["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _me_status(client: AsyncClient, token: str) -> int:
    return (await client.get(ME_URL, headers=_bearer(token))).status_code


async def _register(client: AsyncClient, payload: dict) -> Response:
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200, response.text
    return response


async def _login(client: AsyncClient, payload: dict) -> Response:
    response = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert response.status_code == 200, response.text
    return response


def _use_cookies(client: AsyncClient, cookies: dict[str, str]) -> None:
    """Replaces the jar outright: setting a name the server already set adds
    a second entry (different domain/path) rather than overwriting it."""
    client.cookies.clear()
    client.cookies.set("refresh_token", cookies["refresh_token"])
    client.cookies.set("csrf_token", cookies["csrf_token"])


async def _refresh_with(client: AsyncClient, cookies: dict[str, str]) -> Response:
    _use_cookies(client, cookies)
    return await client.post(
        "/api/v1/auth/refresh", headers={"x-csrf-token": cookies["csrf_token"]}
    )


def _cookies(response: Response) -> dict[str, str]:
    return {
        "refresh_token": response.cookies["refresh_token"],
        "csrf_token": response.cookies["csrf_token"],
    }


def _forge(claims: dict) -> str:
    """A correctly signed access token with arbitrary claims."""
    now = datetime.now(UTC)
    payload = {
        "type": TokenType.ACCESS.value,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **claims,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# --- Token contents -------------------------------------------------------------


async def test_register_login_and_refresh_tokens_carry_the_session_family_id(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    logged_in = await _login(client, register_payload)
    refreshed = await _refresh_with(client, _cookies(logged_in))
    assert refreshed.status_code == 200

    rows = (await db_session.execute(select(Session))).scalars().all()
    families = {row.family_id for row in rows}

    register_sid = uuid.UUID(decode_token(_token(registered))["sid"])
    login_sid = uuid.UUID(decode_token(_token(logged_in))["sid"])
    refresh_sid = uuid.UUID(decode_token(_token(refreshed))["sid"])

    assert {register_sid, login_sid} == families
    assert register_sid != login_sid  # every login starts its own family
    assert refresh_sid == login_sid  # rotation keeps the family


async def test_rotation_keeps_the_family_on_the_replacement_row(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    refreshed = await _refresh_with(client, _cookies(registered))
    assert refreshed.status_code == 200

    rows = (await db_session.execute(select(Session))).scalars().all()
    assert len(rows) == 2
    assert rows[0].family_id == rows[1].family_id
    assert sum(row.revoked_at is None for row in rows) == 1


# --- Rotation never cuts off tabs ------------------------------------------------


async def test_a_refresh_does_not_invalidate_the_access_token_it_replaces(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    refreshed = await _refresh_with(client, _cookies(registered))

    assert await _me_status(client, _token(registered)) == 200
    assert await _me_status(client, _token(refreshed)) == 200


async def test_tabs_sharing_one_cookie_keep_working_across_each_others_rotations(
    client: AsyncClient, register_payload: dict
) -> None:
    """Tab A holds a token while tab B refreshes, then tab A refreshes with
    the cookie B's rotation left behind - nobody's token is cut off and no
    reuse is detected."""
    registered = await _register(client, register_payload)
    tab_a_token = _token(registered)

    tab_b = await _refresh_with(client, _cookies(registered))
    assert tab_b.status_code == 200
    assert await _me_status(client, tab_a_token) == 200

    tab_a = await _refresh_with(client, _cookies(tab_b))
    assert tab_a.status_code == 200

    for token in (tab_a_token, _token(tab_b), _token(tab_a)):
        assert await _me_status(client, token) == 200


# --- Revocation cuts off access tokens immediately ---------------------------------


async def test_logout_invalidates_that_familys_access_tokens_immediately(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    refreshed = await _refresh_with(client, _cookies(registered))

    _use_cookies(client, _cookies(refreshed))
    logout = await client.post(
        "/api/v1/auth/logout", headers={"x-csrf-token": refreshed.cookies["csrf_token"]}
    )
    assert logout.status_code == 200

    # Both the pre-rotation and post-rotation tokens belong to the family.
    assert await _me_status(client, _token(registered)) == 401
    assert await _me_status(client, _token(refreshed)) == 401


async def test_logout_leaves_other_devices_access_tokens_working(
    client: AsyncClient, register_payload: dict
) -> None:
    laptop = await _register(client, register_payload)
    phone = await _login(client, register_payload)

    _use_cookies(client, _cookies(phone))
    logout = await client.post(
        "/api/v1/auth/logout", headers={"x-csrf-token": phone.cookies["csrf_token"]}
    )
    assert logout.status_code == 200

    assert await _me_status(client, _token(phone)) == 401
    assert await _me_status(client, _token(laptop)) == 200


async def test_logout_all_invalidates_every_devices_access_tokens(
    client: AsyncClient, register_payload: dict
) -> None:
    laptop = await _register(client, register_payload)
    phone = await _login(client, register_payload)

    response = await client.post("/api/v1/auth/logout-all", headers=_bearer(_token(laptop)))
    assert response.status_code == 200

    assert await _me_status(client, _token(laptop)) == 401
    assert await _me_status(client, _token(phone)) == 401


async def test_password_change_invalidates_old_access_tokens_and_keeps_the_new_one(
    client: AsyncClient, register_payload: dict
) -> None:
    laptop = await _register(client, register_payload)
    phone = await _login(client, register_payload)

    changed = await client.post(
        "/api/v1/auth/change-password",
        headers=_bearer(_token(laptop)),
        json={
            "current_password": register_payload["password"],
            "new_password": "brandnewpass456",
            "confirm_password": "brandnewpass456",
        },
    )
    assert changed.status_code == 200

    assert await _me_status(client, _token(phone)) == 401
    assert await _me_status(client, _token(laptop)) == 401
    assert await _me_status(client, _token(changed)) == 200


async def test_refresh_token_reuse_invalidates_every_access_token(
    client: AsyncClient, register_payload: dict
) -> None:
    laptop = await _register(client, register_payload)
    phone = await _login(client, register_payload)
    rotated = await _refresh_with(client, _cookies(laptop))
    assert rotated.status_code == 200

    replay = await _refresh_with(client, _cookies(laptop))
    assert replay.status_code == 401

    for response in (laptop, phone, rotated):
        assert await _me_status(client, _token(response)) == 401


async def test_an_expired_session_family_rejects_its_access_tokens(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    await db_session.execute(
        update(Session).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    assert await _me_status(client, _token(registered)) == 401


async def test_revocation_applies_to_every_protected_route_not_just_auth(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    headers = _bearer(_token(registered))
    assert (await client.get("/api/v1/accounts", headers=headers)).status_code == 200

    await client.post("/api/v1/auth/logout-all", headers=headers)

    assert (await client.get("/api/v1/accounts", headers=headers)).status_code == 401


# --- Malformed, legacy and cross-user tokens ----------------------------------------


async def test_a_legacy_token_without_sid_is_rejected(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    user_id = registered.json()["data"]["user"]["id"]

    assert await _me_status(client, _forge({"sub": user_id})) == 401


async def test_a_malformed_sid_is_rejected(client: AsyncClient, register_payload: dict) -> None:
    registered = await _register(client, register_payload)
    user_id = registered.json()["data"]["user"]["id"]

    for bad_sid in ("not-a-uuid", "", 12345, None):
        assert await _me_status(client, _forge({"sub": user_id, "sid": bad_sid})) == 401


async def test_an_unknown_session_family_is_rejected(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    user_id = registered.json()["data"]["user"]["id"]

    token = _forge({"sub": user_id, "sid": str(uuid.uuid4())})
    assert await _me_status(client, token) == 401


async def test_another_users_session_family_cannot_authenticate_a_token(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    await _register(client, register_payload)
    other = await _register(
        client,
        {"email": "other.user@example.com", "password": "correcthorse123", "full_name": "Other"},
    )
    victim_id = await db_session.scalar(
        select(User.id).where(User.email == register_payload["email"])
    )
    other_sid = decode_token(_token(other))["sid"]

    token = _forge({"sub": str(victim_id), "sid": other_sid})
    assert await _me_status(client, token) == 401
