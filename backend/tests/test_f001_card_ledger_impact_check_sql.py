"""Guards scripts/sql/f001_card_ledger_impact_check.sql, the read-only check
an operator runs against a shared (staging/production) database before the
credit-card balance correction. It must stay provably read-only: only
SELECT/WITH queries, transaction control, and SET LOCAL timeouts."""

import re
from pathlib import Path

from tests.conftest import test_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = REPO_ROOT / "scripts" / "sql" / "f001_card_ledger_impact_check.sql"

_ALLOWED_META_COMMAND = re.compile(r"^\\echo\s")
_ALLOWED_SET_LOCAL = re.compile(
    r"^SET LOCAL (statement_timeout|lock_timeout|idle_in_transaction_session_timeout) = '\d+s'$"
)
# Word-bounded, so column names such as updated_at never match UPDATE.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|COPY|CALL|DO|"
    r"VACUUM|ANALYZE|REINDEX|CLUSTER|LOCK|COMMIT|PREPARE|EXECUTE|NOTIFY|LISTEN|REFRESH|"
    r"nextval|setval|set_config|pg_sleep|pg_advisory_\w+|pg_terminate_backend|pg_cancel_backend|"
    r"dblink\w*|lo_\w+|pg_read_\w+)\b",
    re.IGNORECASE,
)


def _sql_lines() -> list[str]:
    lines = []
    for raw in SQL_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.split("--", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _statements() -> list[str]:
    body = "\n".join(line for line in _sql_lines() if not line.lstrip().startswith("\\"))
    return [" ".join(s.split()) for s in body.split(";") if s.strip()]


def test_psql_meta_commands_are_echo_only() -> None:
    meta = [line.strip() for line in _sql_lines() if line.lstrip().startswith("\\")]
    assert meta, "expected the section \\echo headers"
    assert all(_ALLOWED_META_COMMAND.match(m) for m in meta), meta


def test_contains_only_read_only_statements() -> None:
    statements = _statements()
    assert statements[0] == "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert statements[-1] == "ROLLBACK"
    for statement in statements[1:-1]:
        is_query = statement.upper().startswith(("SELECT ", "WITH "))
        assert is_query or _ALLOWED_SET_LOCAL.match(statement), statement
        assert _FORBIDDEN.search(statement) is None, statement
    queries = [s for s in statements if s.upper().startswith(("SELECT ", "WITH "))]
    assert len(queries) == 3


async def test_runs_cleanly_against_the_current_schema() -> None:
    script = "\n".join(line for line in _sql_lines() if not line.lstrip().startswith("\\"))
    async with test_engine.connect() as conn:
        raw = await conn.get_raw_connection()
        # Simple-query protocol runs the whole script, BEGIN ... ROLLBACK
        # included; PostgreSQL itself rejects any write inside READ ONLY.
        await raw.driver_connection.execute(script)
