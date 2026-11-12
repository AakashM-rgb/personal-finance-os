import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.core.rate_limit import limiter
from app.models.audit_log import AuditLog
from app.models.login_failure import LoginFailure
from app.models.user import User
from app.services import auth_service, login_throttle

CHANGE_PASSWORD_URL = "/api/v1/auth/change-password"
NEW_PASSWORD = "brandnewpass456"


async def _register(client: AsyncClient, payload: dict) -> Response:
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200, response.text
    return response


def _bearer(response: Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _change(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    current: str,
    new: str = NEW_PASSWORD,
    confirm: str | None = None,
) -> Response:
    return await client.post(
        CHANGE_PASSWORD_URL,
        headers=headers,
        json={
            "current_password": current,
            "new_password": new,
            "confirm_password": new if confirm is None else confirm,
        },
    )


async def _login(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_change_password_succeeds_and_never_returns_password_material(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)

    response = await _change(client, _bearer(registered), current=register_payload["password"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is None
    assert body["data"]["access_token"]
    assert body["data"]["user"]["email"] == register_payload["email"]
    assert "refresh_token" in response.cookies
    assert "password" not in response.text.lower()
    assert register_payload["password"] not in response.text
    assert NEW_PASSWORD not in response.text


async def test_change_password_updates_the_stored_hash(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    user_query = select(User).where(User.email == register_payload["email"])
    hash_before = (await db_session.execute(user_query)).scalar_one().password_hash

    await _change(client, _bearer(registered), current=register_payload["password"])

    db_session.expire_all()
    hash_after = (await db_session.execute(user_query)).scalar_one().password_hash
    assert hash_after != hash_before
    assert NEW_PASSWORD not in hash_after


async def test_old_password_stops_working_and_new_password_logs_in(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    await _change(client, _bearer(registered), current=register_payload["password"])

    old_login = await _login(client, register_payload["email"], register_payload["password"])
    assert old_login.status_code == 401

    new_login = await _login(client, register_payload["email"], NEW_PASSWORD)
    assert new_login.status_code == 200


async def test_incorrect_current_password_is_rejected_on_that_field_without_a_401(
    client: AsyncClient, register_payload: dict
) -> None:
    """A 401 here would make the frontend treat the session as expired and
    try to refresh it - the caller is authenticated, the input is wrong."""
    registered = await _register(client, register_payload)

    response = await _change(client, _bearer(registered), current="notmypassword1")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["message"] == "Your current password is incorrect."
    assert "current_password" in error["field_errors"]

    still_old = await _login(client, register_payload["email"], register_payload["password"])
    assert still_old.status_code == 200


async def test_failed_change_attempt_is_persisted_to_the_audit_log(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    await _change(client, _bearer(registered), current="notmypassword1")

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "user.password_change_failed" in actions
    assert "user.password_changed" not in actions


async def test_confirmation_mismatch_is_rejected(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)

    response = await _change(
        client,
        _bearer(registered),
        current=register_payload["password"],
        confirm="somethingelse789",
    )

    assert response.status_code == 422
    assert "confirm_password" in response.json()["error"]["field_errors"]
    still_old = await _login(client, register_payload["email"], register_payload["password"])
    assert still_old.status_code == 200


async def test_weak_new_password_is_rejected_by_the_shared_strength_rules(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    headers = _bearer(registered)

    for weak in ("short1", "onlyletters", "1234567890"):
        response = await _change(client, headers, current=register_payload["password"], new=weak)
        assert response.status_code == 422, weak
        assert "new_password" in response.json()["error"]["field_errors"]


async def test_new_password_identical_to_current_is_rejected(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)

    response = await _change(
        client,
        _bearer(registered),
        current=register_payload["password"],
        new=register_payload["password"],
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["message"] == "New password must be different from your current password."
    assert "new_password" in error["field_errors"]


async def test_unknown_fields_are_rejected(client: AsyncClient, register_payload: dict) -> None:
    registered = await _register(client, register_payload)

    response = await client.post(
        CHANGE_PASSWORD_URL,
        headers=_bearer(registered),
        json={
            "current_password": register_payload["password"],
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
            "user_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 422


async def test_change_password_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        CHANGE_PASSWORD_URL,
        json={
            "current_password": "correcthorse123",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert response.status_code == 401


async def test_change_password_revokes_every_other_refresh_session(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    original_refresh = registered.cookies["refresh_token"]
    original_csrf = registered.cookies["csrf_token"]

    second_device = await _login(client, register_payload["email"], register_payload["password"])
    second_refresh = second_device.cookies["refresh_token"]
    second_csrf = second_device.cookies["csrf_token"]

    changed = await _change(client, _bearer(second_device), current=register_payload["password"])
    assert changed.status_code == 200

    for refresh_token, csrf_token in (
        (original_refresh, original_csrf),
        (second_refresh, second_csrf),
    ):
        client.cookies.set("refresh_token", refresh_token)
        client.cookies.set("csrf_token", csrf_token)
        response = await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": csrf_token})
        assert response.status_code == 401


async def test_change_password_keeps_the_caller_signed_in_with_one_fresh_session(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    await _login(client, register_payload["email"], register_payload["password"])

    changed = await _change(client, _bearer(registered), current=register_payload["password"])
    new_headers = _bearer(changed)

    sessions = await client.get("/api/v1/auth/sessions", headers=new_headers)
    assert sessions.status_code == 200
    assert len(sessions.json()["data"]) == 1

    new_csrf = changed.cookies["csrf_token"]
    client.cookies.set("refresh_token", changed.cookies["refresh_token"])
    client.cookies.set("csrf_token", new_csrf)
    refreshed = await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": new_csrf})
    assert refreshed.status_code == 200


async def test_change_password_does_not_affect_another_users_sessions_or_password(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    other_payload = {
        "email": "other.user@example.com",
        "password": "correcthorse123",
        "full_name": "Other User",
    }
    other = await _register(client, other_payload)
    other_refresh = other.cookies["refresh_token"]
    other_csrf = other.cookies["csrf_token"]

    await _change(client, _bearer(registered), current=register_payload["password"])

    client.cookies.set("refresh_token", other_refresh)
    client.cookies.set("csrf_token", other_csrf)
    refreshed = await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": other_csrf})
    assert refreshed.status_code == 200

    other_login = await _login(client, other_payload["email"], other_payload["password"])
    assert other_login.status_code == 200


async def test_successful_change_is_audit_logged(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    await _change(client, _bearer(registered), current=register_payload["password"])

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert "user.password_changed" in actions


# --- Per-account throttle (H1) ------------------------------------------------
# The per-IP limiter is switched off in these tests, modelling an attacker who
# rotates IPs - the case the per-account throttle exists for.

MAX_FAILURES = 3
WINDOW_MINUTES = 15


@pytest.fixture
def throttle_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(login_throttle.settings, "login_account_max_failures", MAX_FAILURES)
    monkeypatch.setattr(login_throttle.settings, "login_account_window_minutes", WINDOW_MINUTES)


async def _fail_changes(client: AsyncClient, headers: dict[str, str], times: int) -> list[int]:
    return [
        (await _change(client, headers, current="notmypassword1")).status_code for _ in range(times)
    ]


@pytest.mark.usefixtures("throttle_settings")
async def test_wrong_current_passwords_throttle_changes_even_with_the_right_password(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    headers = _bearer(registered)

    assert await _fail_changes(client, headers, MAX_FAILURES) == [422] * MAX_FAILURES

    throttled = await _change(client, headers, current=register_payload["password"])
    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "rate_limited"
    # Refused before any password check, so the password is still unchanged.
    still_old = await _login(client, register_payload["email"], register_payload["password"])
    assert still_old.status_code == 200


@pytest.mark.usefixtures("throttle_settings")
async def test_failures_below_the_threshold_do_not_throttle(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    headers = _bearer(registered)

    await _fail_changes(client, headers, MAX_FAILURES - 1)
    response = await _change(client, headers, current=register_payload["password"])
    assert response.status_code == 200


@pytest.mark.usefixtures("throttle_settings")
async def test_the_password_change_throttle_recovers_when_the_window_passes(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    headers = _bearer(registered)
    await _fail_changes(client, headers, MAX_FAILURES)

    await db_session.execute(
        update(LoginFailure).values(
            created_at=datetime.now(UTC) - timedelta(minutes=WINDOW_MINUTES + 1)
        )
    )
    await db_session.commit()

    response = await _change(client, headers, current=register_payload["password"])
    assert response.status_code == 200


@pytest.mark.usefixtures("throttle_settings")
async def test_a_successful_change_clears_the_failure_count(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    await _fail_changes(client, _bearer(registered), MAX_FAILURES - 1)

    changed = await _change(client, _bearer(registered), current=register_payload["password"])
    assert changed.status_code == 200

    count = await db_session.scalar(select(func.count()).select_from(LoginFailure))
    assert count == 0


@pytest.mark.usefixtures("throttle_settings")
async def test_password_change_failures_never_lock_normal_login(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    await _fail_changes(client, _bearer(registered), MAX_FAILURES + 2)

    login = await _login(client, register_payload["email"], register_payload["password"])
    assert login.status_code == 200


@pytest.mark.usefixtures("throttle_settings")
async def test_login_failures_never_lock_password_changes(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    for _ in range(MAX_FAILURES + 1):
        await _login(client, register_payload["email"], "wrong-password-123")

    response = await _change(client, _bearer(registered), current=register_payload["password"])
    assert response.status_code == 200


@pytest.mark.usefixtures("throttle_settings")
async def test_the_password_change_throttle_is_per_account(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    other_payload = {
        "email": "other.user@example.com",
        "password": "correcthorse123",
        "full_name": "Other User",
    }
    other = await _register(client, other_payload)

    await _fail_changes(client, _bearer(registered), MAX_FAILURES)

    response = await _change(client, _bearer(other), current=other_payload["password"])
    assert response.status_code == 200


def test_the_password_change_key_is_distinct_from_every_login_key() -> None:
    user_id = uuid.uuid4()
    key = login_throttle.password_change_key(user_id)
    assert key == login_throttle.password_change_key(user_id)
    assert key != login_throttle.password_change_key(uuid.uuid4())
    assert key != login_throttle.account_key(f"password-change:{user_id}")
    assert str(user_id) not in key


@pytest.mark.usefixtures("throttle_settings")
async def test_throttled_change_attempts_are_audit_logged(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    registered = await _register(client, register_payload)
    await _fail_changes(client, _bearer(registered), MAX_FAILURES + 1)

    actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
    assert actions.count("user.password_change_failed") == MAX_FAILURES
    assert "user.password_change_throttled" in actions


# --- Concurrency (M1) and Argon2 cost (M3) ------------------------------------


@pytest.mark.usefixtures("throttle_settings")
async def test_concurrent_changes_never_both_succeed(
    client: AsyncClient, register_payload: dict
) -> None:
    registered = await _register(client, register_payload)
    headers = _bearer(registered)
    candidates = ["firstnewpass111", "secondnewpass222"]

    responses = await asyncio.gather(
        *(_change(client, headers, current=register_payload["password"], new=p) for p in candidates)
    )

    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == 1
    # The loser is refused while the winner holds the lock (429) or, if it
    # runs after, fails the check against the winner's new hash (422).
    assert set(statuses) - {200} <= {422, 429}

    winner = candidates[statuses.index(200)]
    loser = candidates[1 - statuses.index(200)]
    assert (await _login(client, register_payload["email"], winner)).status_code == 200
    assert (await _login(client, register_payload["email"], loser)).status_code == 401
    old = await _login(client, register_payload["email"], register_payload["password"])
    assert old.status_code == 401


async def test_the_current_password_is_checked_against_the_latest_committed_hash(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    """A request whose user object was loaded before another change
    committed must not be able to change the password with the old one."""
    registered = await _register(client, register_payload)
    stale_user = await db_session.scalar(
        select(User).where(User.email == register_payload["email"])
    )
    assert stale_user is not None
    await db_session.commit()

    changed = await _change(client, _bearer(registered), current=register_payload["password"])
    assert changed.status_code == 200

    with pytest.raises(ValidationAppError):
        await auth_service.change_password(
            db_session,
            user=stale_user,
            current_password=register_payload["password"],
            new_password="attackerpass999",
            confirm_password="attackerpass999",
            user_agent=None,
            ip_address=None,
        )
    assert (await _login(client, register_payload["email"], NEW_PASSWORD)).status_code == 200


async def test_a_successful_change_runs_only_one_password_verification(
    client: AsyncClient, register_payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered = await _register(client, register_payload)
    calls: list[str] = []
    real_verify = auth_service.verify_password

    def counting_verify(plain: str, hashed: str) -> bool:
        calls.append(plain)
        return real_verify(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", counting_verify)

    response = await _change(client, _bearer(registered), current=register_payload["password"])
    assert response.status_code == 200
    assert len(calls) == 1
