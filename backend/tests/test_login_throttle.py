"""Per-account login throttle (app.services.login_throttle).

The per-IP limiter is switched off in these tests: that models an attacker
who can rotate or spoof client IPs at will - exactly the case the
per-account throttle exists for. Its own engagement is covered in
test_rate_limiting.py.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.models.audit_log import AuditLog
from app.models.login_failure import LoginFailure
from app.services import login_throttle

MAX_FAILURES = 3
WINDOW_MINUTES = 15
UNREGISTERED_EMAIL = "nobody-here@example.com"


@pytest.fixture(autouse=True)
def _throttle_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(login_throttle.settings, "login_account_max_failures", MAX_FAILURES)
    monkeypatch.setattr(login_throttle.settings, "login_account_window_minutes", WINDOW_MINUTES)


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def _fail(client: AsyncClient, email: str, times: int) -> list[int]:
    return [(await _login(client, email, "wrong-password-123")).status_code for _ in range(times)]


async def _age_failures(db: AsyncSession, minutes: int) -> None:
    await db.execute(
        update(LoginFailure).values(created_at=datetime.now(UTC) - timedelta(minutes=minutes))
    )
    await db.commit()


async def test_repeated_failures_throttle_the_account_even_for_the_right_password(
    client: AsyncClient, register_payload: dict
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)

    assert await _fail(client, register_payload["email"], MAX_FAILURES) == [401] * MAX_FAILURES

    # Accepting the correct password now would turn the throttle into an
    # oracle that confirms a guess - so it's refused too.
    response = await _login(client, register_payload["email"], register_payload["password"])
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "access_token" not in response.text


async def test_registered_and_unregistered_emails_get_identical_responses(
    client: AsyncClient, register_payload: dict
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)

    def summarize(responses: list) -> list[tuple[int, dict]]:
        return [(r.status_code, r.json()) for r in responses]

    attempts = MAX_FAILURES + 2
    registered = [
        await _login(client, register_payload["email"], "wrong-1234567") for _ in range(attempts)
    ]
    unregistered = [
        await _login(client, UNREGISTERED_EMAIL, "wrong-1234567") for _ in range(attempts)
    ]

    assert summarize(registered) == summarize(unregistered)
    assert [r.status_code for r in registered] == [401] * MAX_FAILURES + [429, 429]


async def test_a_valid_login_succeeds_below_the_limit_and_clears_failures(
    client: AsyncClient, register_payload: dict
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    email = register_payload["email"]

    await _fail(client, email, MAX_FAILURES - 1)
    assert (await _login(client, email, register_payload["password"])).status_code == 200

    # The success reset the counter: a fresh run of failures starts from zero.
    assert await _fail(client, email, MAX_FAILURES - 1) == [401] * (MAX_FAILURES - 1)
    assert (await _login(client, email, register_payload["password"])).status_code == 200


async def test_the_throttle_is_per_account(client: AsyncClient, register_payload: dict) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    await _fail(client, UNREGISTERED_EMAIL, MAX_FAILURES + 1)

    response = await _login(client, register_payload["email"], register_payload["password"])
    assert response.status_code == 200


async def test_email_case_variants_share_one_counter(
    client: AsyncClient, register_payload: dict
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    email = register_payload["email"]

    for variant in (email.upper(), email.title(), email):
        assert (await _login(client, variant, "wrong-password-123")).status_code == 401

    assert (await _login(client, email, register_payload["password"])).status_code == 429


async def test_the_lock_expires_with_the_window_and_never_becomes_permanent(
    client: AsyncClient, register_payload: dict, db_session: AsyncSession
) -> None:
    await client.post("/api/v1/auth/register", json=register_payload)
    email = register_payload["email"]
    await _fail(client, email, MAX_FAILURES)

    # Attempts refused while throttled are not recorded, so they can't
    # extend the lock beyond the window.
    assert await _fail(client, email, 5) == [429] * 5
    count = await db_session.scalar(select(func.count()).select_from(LoginFailure))
    assert count == MAX_FAILURES

    await _age_failures(db_session, WINDOW_MINUTES + 1)
    assert (await _login(client, email, register_payload["password"])).status_code == 200


async def test_concurrent_attempts_cannot_overshoot_the_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    attempts = MAX_FAILURES + 5
    responses = await asyncio.gather(
        *(_login(client, UNREGISTERED_EMAIL, "wrong-password-123") for _ in range(attempts))
    )

    # Attempts that overlap one already in flight are refused outright
    # (never queued), so at most MAX_FAILURES ever reach a password check.
    statuses = [r.status_code for r in responses]
    assert set(statuses) <= {401, 429}
    assert 1 <= statuses.count(401) <= MAX_FAILURES
    count = await db_session.scalar(select(func.count()).select_from(LoginFailure))
    assert count == statuses.count(401)


async def test_stored_failures_never_contain_the_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _fail(client, UNREGISTERED_EMAIL, 1)

    keys = (await db_session.scalars(select(LoginFailure.account_key))).all()
    assert keys == [login_throttle.account_key(UNREGISTERED_EMAIL)]
    assert "nobody" not in keys[0] and "@" not in keys[0]


async def test_failures_older_than_the_window_are_pruned(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _fail(client, UNREGISTERED_EMAIL, 2)
    await _age_failures(db_session, WINDOW_MINUTES + 1)

    await _fail(client, "someone-else@example.com", 1)

    count = await db_session.scalar(select(func.count()).select_from(LoginFailure))
    assert count == 1


async def test_throttled_attempts_are_audit_logged(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _fail(client, UNREGISTERED_EMAIL, MAX_FAILURES + 1)

    entries = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "user.login_throttled"))
    ).all()
    assert len(entries) == 1
