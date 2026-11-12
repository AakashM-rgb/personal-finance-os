"""Upgrade/downgrade of migration a3f9c1d2e7b4 (sessions.family_id) against the
test database: no session row is ever lost, and every pre-existing row is
backfilled into its own family.

Runs Alembic in a subprocess because env.py drives its own event loop. Always
leaves the database at head, and drops pooled connections afterwards so no
other test reuses a statement prepared against the pre-migration schema."""

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
REVISION = "a3f9c1d2e7b4"
PREVIOUS_REVISION = "5d7e1c2a9b30"


def _alembic(*args: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": get_settings().test_database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Only the exit status is surfaced: Alembic's output can include the URL.
    assert result.returncode == 0, f"alembic {' '.join(args)} failed"


@pytest_asyncio.fixture
async def at_previous_revision(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    await db_session.close()
    _alembic("downgrade", PREVIOUS_REVISION)
    try:
        yield
    finally:
        await db_session.close()
        _alembic("upgrade", "head")
        assert db_session.bind is not None
        await db_session.bind.dispose()  # type: ignore[union-attr]


async def _columns(db: AsyncSession) -> set[str]:
    result = await db.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'sessions'")
    )
    return set(result.scalars().all())


async def _insert_user_with_sessions(db: AsyncSession, count: int) -> list[uuid.UUID]:
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, full_name, is_active, "
            "created_at, updated_at) VALUES (:id, :email, 'x', 'Migration Test', true, "
            ":now, :now)"
        ),
        {"id": user_id, "email": f"{user_id}@example.com", "now": now},
    )
    session_ids = [uuid.uuid4() for _ in range(count)]
    for session_id in session_ids:
        await db.execute(
            text(
                "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at, "
                "created_at, updated_at) VALUES (:id, :user_id, 'hash', :expires, :now, :now)"
            ),
            {
                "id": session_id,
                "user_id": user_id,
                "expires": now + timedelta(days=30),
                "now": now,
            },
        )
    await db.commit()
    return session_ids


async def test_upgrade_backfills_each_existing_session_into_its_own_family(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    assert "family_id" not in await _columns(db_session)
    session_ids = await _insert_user_with_sessions(db_session, 3)
    await db_session.close()

    _alembic("upgrade", REVISION)

    rows = (await db_session.execute(text("SELECT id, family_id FROM sessions"))).all()
    assert {row.id for row in rows} == set(session_ids)
    assert all(row.family_id == row.id for row in rows)

    nullable = await db_session.scalar(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'sessions' AND column_name = 'family_id'"
        )
    )
    assert nullable == "NO"
    index = await db_session.scalar(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_sessions_family_id'")
    )
    assert index == 1


async def test_downgrade_drops_only_the_column_and_keeps_every_session(
    at_previous_revision: None, db_session: AsyncSession
) -> None:
    session_ids = await _insert_user_with_sessions(db_session, 2)
    await db_session.close()
    _alembic("upgrade", REVISION)
    await db_session.close()

    _alembic("downgrade", PREVIOUS_REVISION)

    assert "family_id" not in await _columns(db_session)
    remaining = (await db_session.execute(text("SELECT id FROM sessions"))).scalars().all()
    assert set(remaining) == set(session_ids)
    index = await db_session.scalar(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_sessions_family_id'")
    )
    assert index is None
