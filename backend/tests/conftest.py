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
from app.core.database import Base, get_db
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
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


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
