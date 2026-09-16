"""Verifies rate limiting on authentication endpoints actually engages -
by genuinely exceeding the configured limit and observing a real 429,
never by asserting the decorator is merely present in source. Limits are
read from the live settings so this stays correct regardless of the
configured .env values."""

from httpx import AsyncClient

from app.core.config import get_settings

settings = get_settings()


def _limit_count(rate_limit: str) -> int:
    """"5/minute" -> 5."""
    return int(rate_limit.split("/", 1)[0])


async def test_login_is_rate_limited(client: AsyncClient) -> None:
    limit = _limit_count(settings.login_rate_limit)
    payload = {"email": "nobody@example.com", "password": "wrong-password-123"}

    statuses = [
        (await client.post("/api/v1/auth/login", json=payload)).status_code
        for _ in range(limit + 1)
    ]
    # Every request up to the limit is a normal auth failure (401); only
    # once the limit is exceeded does the rate limiter itself respond.
    assert statuses[:limit] == [401] * limit
    assert statuses[limit] == 429


async def test_register_is_rate_limited(client: AsyncClient) -> None:
    limit = _limit_count(settings.register_rate_limit)

    statuses = []
    for i in range(limit + 1):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"rl-register-{i}@example.com",
                "password": "correcthorse123",
                "full_name": "Rate Limit Test",
            },
        )
        statuses.append(response.status_code)

    assert statuses[:limit] == [200] * limit
    assert statuses[limit] == 429


async def test_refresh_is_rate_limited(client: AsyncClient, register_payload: dict) -> None:
    limit = _limit_count(settings.refresh_rate_limit)
    await client.post("/api/v1/auth/register", json=register_payload)

    statuses = []
    for _ in range(limit + 1):
        response = await client.post(
            "/api/v1/auth/refresh", headers={"x-csrf-token": client.cookies["csrf_token"]}
        )
        statuses.append(response.status_code)
        if response.status_code != 200:
            break

    assert statuses.count(200) == limit
    assert statuses[-1] == 429


async def test_rate_limit_response_never_exposes_internals(client: AsyncClient) -> None:
    limit = _limit_count(settings.login_rate_limit)
    payload = {"email": "nobody@example.com", "password": "wrong-password-123"}
    for _ in range(limit):
        await client.post("/api/v1/auth/login", json=payload)

    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert "traceback" not in response.text.lower()
    assert "slowapi" not in response.text.lower()
