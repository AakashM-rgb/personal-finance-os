"""Runs Alembic against the test database for migration tests.

A subprocess because env.py drives its own event loop, which can't nest inside
pytest-asyncio's. Callers assert on the exit status and on stderr for a named
refusal, never on stdout, which can include the database URL."""

import os
import subprocess
import sys
from pathlib import Path

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": get_settings().test_database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
