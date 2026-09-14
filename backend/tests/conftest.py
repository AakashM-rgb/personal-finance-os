"""Test fixtures: an isolated test database (finance_app_test), truncated
between tests, and an httpx AsyncClient wired to the ASGI app."""

import os

os.environ.setdefault("ENVIRONMENT", "test")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.main import app

settings = get_settings()

test_engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    # Rate limits are process-global; without this, unrelated tests hitting the
    # same auth endpoint would trip each other's limits. Limiter.reset() logs a
    # warning rather than raising if the backing storage doesn't support it.
    limiter.reset()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database() -> AsyncGenerator[None, None]:
    yield
    async with test_engine.begin() as conn:
        # `categories` holds migration-seeded system defaults (user_id IS NULL)
        # that must survive for the life of the test database. A blanket
        # TRUNCATE ... CASCADE on `users` cascades into every table with an FK
        # to it - including categories - regardless of whether "categories"
        # is named in the TRUNCATE list, wiping the seeded defaults after the
        # first test. Deleting rows instead of truncating tables relies on the
        # FK ondelete behavior already declared on the models (CASCADE for
        # sessions/accounts/user_settings/owned categories, SET NULL for
        # audit_logs), so only user-owned data is ever removed; categories
        # with user_id IS NULL are never touched because NULL never matches
        # a cascade-delete condition.
        await conn.execute(text("DELETE FROM audit_logs"))
        await conn.execute(text("DELETE FROM users"))


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def register_payload() -> dict:
    return {
        "email": "jane.doe@example.com",
        "password": "correcthorse123",
        "full_name": "Jane Doe",
    }


async def _register(client: AsyncClient, *, email: str, full_name: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse123", "full_name": full_name},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Registers a fresh user and returns an Authorization header for them."""
    data = await _register(client, email="owner@example.com", full_name="Owner")
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest_asyncio.fixture
async def other_auth_headers(client: AsyncClient) -> dict[str, str]:
    """A second, independent user - for cross-user authorization tests."""
    data = await _register(client, email="intruder@example.com", full_name="Intruder")
    return {"Authorization": f"Bearer {data['access_token']}"}
