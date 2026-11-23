"""Migration d7a1e4c9b3f2: the public schema is closed to Supabase's Data API
roles, while the backend -- which connects as the tables' owner -- keeps full
access.

Two groups:

* Tests that need nothing but the test database: RLS on every table at head
  (including tables a future migration adds, which is what makes a forgotten
  `ENABLE ROW LEVEL SECURITY` fail CI), no FORCE, no permissive policies, the
  backend still working, the downgrade contract, flag validation, and a single
  Alembic head.
* Tests that need the `anon`/`authenticated` roles Supabase creates. They use
  the roles if they exist, create them if the test role may (CI's superuser),
  and otherwise skip -- unless REQUIRE_SUPABASE_ROLE_TESTS=1, which CI sets so
  they can never be skipped there unnoticed. Roles the tests create are
  dropped again afterwards; pre-existing ones are left alone.

Always leaves the database at head with the hardening applied."""

import importlib.util
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from types import ModuleType

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.database import Base
from tests.alembic_runner import BACKEND_DIR, run_alembic
from tests.conftest import test_engine
from tests.f001_ledger_seed import PUBLIC_SCHEMA_SQL_PATH, sql_queries

REVISION = "d7a1e4c9b3f2"
PREVIOUS_REVISION = "c8e4a1f6b2d9"
API_ROLES = ("anon", "authenticated")
REVERT = ("-x", "rls_hardening=revert")
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def _alembic(*args: str) -> None:
    assert run_alembic(*args).returncode == 0, f"alembic {' '.join(args)} failed"


def _alembic_refuses(*args: str, reason: str) -> None:
    result = run_alembic(*args)
    assert result.returncode != 0, f"alembic {' '.join(args)} unexpectedly succeeded"
    assert "PublicSchemaProtectionRefused" in result.stderr, "failed for another reason"
    assert reason in result.stderr, f"refusal did not mention {reason!r}"


async def _scalar(sql: str, **params: object) -> object:
    async with test_engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar()


async def _tables_without_rls() -> list[str]:
    async with test_engine.connect() as conn:
        return list(
            (
                await conn.execute(
                    text(
                        "SELECT c.relname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                        "AND NOT c.relrowsecurity ORDER BY 1"
                    )
                )
            ).scalars()
        )


async def _granted(role: str) -> list[str]:
    """Every table privilege `role` holds in public, as 'PRIVILEGE table'."""
    async with test_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT p.privilege || ' ' || c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace, "
                "unnest(CAST(:privs AS text[])) p(privilege) "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm') "
                "AND has_table_privilege(:role, c.oid, p.privilege) ORDER BY 1"
            ),
            {"role": role, "privs": list(PRIVILEGES)},
        )
        return list(rows.scalars())


async def _release_connections() -> None:
    """The migration takes ACCESS EXCLUSIVE locks; pooled connections from the
    test would otherwise make it wait on its own test."""
    await test_engine.dispose()


@pytest_asyncio.fixture
async def back_at_head() -> AsyncGenerator[None, None]:
    await _release_connections()
    try:
        yield
    finally:
        await _release_connections()
        _alembic("upgrade", "head")
        assert await _tables_without_rls() == []


# --- what head looks like, on any database ---------------------------------------------------


async def test_every_public_table_has_rls_at_head() -> None:
    """The guard for future migrations: a new table created without
    `ENABLE ROW LEVEL SECURITY` fails here, and so fails CI."""
    assert await _tables_without_rls() == []


async def test_every_model_table_is_covered() -> None:
    """The check above is only meaningful if it sees the real schema."""
    async with test_engine.connect() as conn:
        protected = set(
            (
                await conn.execute(
                    text(
                        "SELECT c.relname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"
                    )
                )
            ).scalars()
        )
    assert set(Base.metadata.tables) | {"alembic_version"} <= protected


async def test_rls_is_not_forced_so_the_owner_keeps_access() -> None:
    forced = await _scalar(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relforcerowsecurity"
    )
    assert forced == 0


async def test_no_policy_opens_a_table_back_up() -> None:
    """No policies is the design: RLS with none denies every non-owner role.
    A permissive policy added to make something work would undo that."""
    assert await _scalar("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'") == 0


async def test_the_backend_role_owns_every_table() -> None:
    """Why the backend needs no policy: an owner is exempt from its own RLS."""
    not_owned = await _scalar(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
        "AND NOT pg_has_role(current_user, c.relowner, 'USAGE')"
    )
    assert not_owned == 0


async def test_the_backend_still_reads_and_writes_with_rls_on(client: AsyncClient) -> None:
    assert await _tables_without_rls() == []
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "rls-owner@example.com", "password": "correcthorse123", "full_name": "R"},
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['data']['access_token']}"}
    created = await client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Main Bank", "type": "bank_account", "balance_minor": 10_000_00},
    )
    assert created.status_code == 201, created.text
    expense = await client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "account_id": created.json()["data"]["id"],
            "type": "expense",
            "amount_minor": 250_00,
        },
    )
    assert expense.status_code == 201, expense.text
    accounts = await client.get("/api/v1/accounts", headers=headers)
    assert accounts.json()["data"][0]["balance_minor"] == 9_750_00


async def test_no_function_lives_in_public() -> None:
    """PostgreSQL grants EXECUTE on every new function to PUBLIC by a built-in
    default that the migration's per-schema revoke cannot remove, so a
    function here would be callable by anon over Supabase's RPC endpoint. A
    migration that adds one must make that decision deliberately."""
    count = await _scalar(
        "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public'"
    )
    assert count == 0


async def test_a_held_lock_makes_the_migration_fail_fast_and_change_nothing(
    back_at_head: None,
) -> None:
    """ENABLE/DISABLE ROW LEVEL SECURITY needs an ACCESS EXCLUSIVE lock. With
    another session holding a lock on one table, the migration must give up
    after its lock timeout and roll back -- not hang the release."""
    async with test_engine.connect() as holder:
        await holder.begin()
        await holder.execute(text("SELECT 1 FROM users LIMIT 1"))  # holds ACCESS SHARE
        result = run_alembic(*REVERT, "downgrade", PREVIOUS_REVISION)
        await holder.rollback()

    assert result.returncode != 0
    assert "lock timeout" in result.stderr
    await _release_connections()
    assert await _scalar("SELECT version_num FROM alembic_version") == REVISION
    assert await _tables_without_rls() == []


async def _exposure_summary() -> dict:
    async with test_engine.connect() as conn:
        row = (await conn.execute(text(sql_queries(PUBLIC_SCHEMA_SQL_PATH)[0]))).mappings().one()
        return dict(row)


async def test_the_exposure_check_reports_a_clean_head() -> None:
    summary = await _exposure_summary()

    assert summary["alembic_revision"] == REVISION
    assert summary["tables"] == len(Base.metadata.tables) + 1
    for column in (
        "tables_without_rls",
        "tables_with_forced_rls",
        "policies",
        "api_role_relation_grants",
        "api_role_column_grants",
        "api_role_default_grants",
        "functions_in_public",
    ):
        assert summary[column] == 0, column


def test_there_is_exactly_one_head_and_it_is_this_revision() -> None:
    result = run_alembic("heads")
    assert result.returncode == 0
    heads = [line for line in result.stdout.splitlines() if "(head)" in line]
    assert heads == [f"{REVISION} (head)"]


def test_this_revision_follows_the_card_balance_correction() -> None:
    migration = _load_migration()
    assert migration.down_revision == PREVIOUS_REVISION


# --- downgrade contract ----------------------------------------------------------------------


async def test_a_plain_downgrade_keeps_the_protection(back_at_head: None) -> None:
    """Moving the revision pointer back (for example the F-001 rollback,
    which downgrades past this revision) must not quietly re-expose data."""
    _alembic("downgrade", PREVIOUS_REVISION)

    assert await _scalar("SELECT version_num FROM alembic_version") == PREVIOUS_REVISION
    assert await _tables_without_rls() == []


async def test_revert_disables_rls_and_upgrade_restores_it(back_at_head: None) -> None:
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)
    assert len(await _tables_without_rls()) == len(Base.metadata.tables) + 1  # + alembic_version
    await _release_connections()

    _alembic("upgrade", REVISION)
    assert await _tables_without_rls() == []


async def test_upgrade_is_idempotent(back_at_head: None) -> None:
    """A re-run after a plain downgrade finds RLS already on and grants already
    revoked, and must still succeed."""
    _alembic("downgrade", PREVIOUS_REVISION)
    await _release_connections()
    _alembic("upgrade", REVISION)
    assert await _tables_without_rls() == []


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("-x", "rls_hardening=yes"), "must be 'revert'"),
        (("-x", "rls_hardening_typo=revert"), "Unknown option"),
    ],
)
async def test_a_mistyped_flag_is_refused(
    back_at_head: None, args: tuple[str, str], reason: str
) -> None:
    _alembic_refuses(*args, "downgrade", PREVIOUS_REVISION, reason=reason)
    assert await _scalar("SELECT version_num FROM alembic_version") == REVISION


def test_offline_sql_rendering_is_refused() -> None:
    """The migration inspects live roles and tables; rendering it blind as
    SQL would skip every safeguard."""
    result = run_alembic("upgrade", f"{PREVIOUS_REVISION}:{REVISION}", "--sql")
    assert result.returncode != 0
    assert "PublicSchemaProtectionRefused" in result.stderr


# --- with Supabase's Data API roles present --------------------------------------------------


def _load_migration() -> ModuleType:
    path = next((BACKEND_DIR / "migrations" / "versions").glob(f"{REVISION}_*.py"))
    spec = importlib.util.spec_from_file_location(f"migration_{REVISION}", Path(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _can_create_roles() -> bool:
    return bool(
        await _scalar("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
    )


def _skip_or_fail(reason: str) -> None:
    if os.environ.get("REQUIRE_SUPABASE_ROLE_TESTS") == "1":
        pytest.fail(f"{reason}, but REQUIRE_SUPABASE_ROLE_TESTS=1")
    pytest.skip(reason)


@pytest_asyncio.fixture
async def supabase_roles(back_at_head: None) -> AsyncGenerator[None, None]:
    """`anon`/`authenticated` holding exactly what Supabase hands them by
    default: every privilege on every table and default privileges for new
    ones -- the state production was found in -- with RLS off."""
    async with test_engine.connect() as conn:
        existing = set(
            (
                await conn.execute(
                    text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:r)"),
                    {"r": list(API_ROLES)},
                )
            ).scalars()
        )
    created = [role for role in API_ROLES if role not in existing]
    if created and not await _can_create_roles():
        _skip_or_fail("the anon/authenticated roles are absent and the test role can't create them")

    async with test_engine.begin() as conn:
        for role in created:
            await conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
    await _release_connections()
    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)
    async with test_engine.begin() as conn:
        me = (await conn.execute(text("SELECT quote_ident(current_user)"))).scalar_one()
        for role in API_ROLES:
            await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
            await conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}"))
            # A column-level grant too: has_table_privilege can't see these.
            await conn.execute(text(f"GRANT SELECT (email) ON users TO {role}"))
            await conn.execute(
                text(
                    f"ALTER DEFAULT PRIVILEGES FOR ROLE {me} IN SCHEMA public "
                    f"GRANT ALL ON TABLES TO {role}"
                )
            )
    await _release_connections()
    try:
        yield
    finally:
        await _release_connections()
        _alembic("upgrade", "head")
        if created:
            async with test_engine.begin() as conn:
                await conn.execute(text(f"DROP OWNED BY {', '.join(created)}"))
                for role in created:
                    await conn.execute(text(f"DROP ROLE {role}"))
        await _release_connections()


async def _as_role(conn: AsyncConnection, role: str, sql: str) -> object:
    await conn.execute(text(f"SET LOCAL ROLE {role}"))
    return (await conn.execute(text(sql))).scalar()


async def test_the_unhardened_state_really_is_exposed(supabase_roles: None) -> None:
    """Proves the fixture reproduces the finding, so the tests below prove
    something: before the migration, anon can read users."""
    async with test_engine.connect() as conn:
        await conn.begin()
        assert await _as_role(conn, "anon", "SELECT count(*) FROM users") is not None
        await conn.rollback()


async def test_upgrade_revokes_every_api_role_privilege(supabase_roles: None) -> None:
    _alembic("upgrade", REVISION)

    for role in API_ROLES:
        assert await _granted(role) == [], role
        column_grants = await _scalar(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND has_any_column_privilege(:role, c.oid, 'SELECT')",
            role=role,
        )
        assert column_grants == 0, role
    assert await _tables_without_rls() == []


async def test_the_exposure_check_sees_the_exposure_and_then_its_removal(
    supabase_roles: None,
) -> None:
    before = await _exposure_summary()
    assert before["tables_without_rls"] == before["tables"]
    assert before["api_role_relation_grants"] > 0
    assert before["api_role_column_grants"] > 0
    assert before["api_role_default_grants"] > 0
    await _release_connections()

    _alembic("upgrade", REVISION)

    after = await _exposure_summary()
    for column in (
        "tables_without_rls",
        "api_role_relation_grants",
        "api_role_column_grants",
        "api_role_default_grants",
    ):
        assert after[column] == 0, column


@pytest.mark.parametrize("role", API_ROLES)
async def test_an_api_role_cannot_touch_users_after_upgrade(
    supabase_roles: None, role: str
) -> None:
    _alembic("upgrade", REVISION)

    for statement in (
        "SELECT count(*) FROM users",
        "UPDATE users SET full_name = full_name",
        "TRUNCATE sessions",
    ):
        async with test_engine.connect() as conn:
            await conn.begin()
            with pytest.raises((ProgrammingError, DBAPIError), match="permission denied"):
                await _as_role(conn, role, statement)
            await conn.rollback()


async def test_rls_still_hides_rows_if_a_grant_is_restored_by_mistake(
    supabase_roles: None, client: AsyncClient
) -> None:
    """Defense in depth: with RLS on and no policy, even a re-granted SELECT
    returns nothing to a non-owner role."""
    _alembic("upgrade", REVISION)
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "rls-depth@example.com", "password": "correcthorse123", "full_name": "D"},
    )
    assert registered.status_code == 200

    async with test_engine.connect() as conn:
        await conn.begin()
        assert (await conn.execute(text("SELECT count(*) FROM users"))).scalar() == 1
        await conn.execute(text("GRANT SELECT ON users TO anon"))
        assert await _as_role(conn, "anon", "SELECT count(*) FROM users") == 0
        await conn.rollback()


async def test_tables_created_later_are_not_granted_to_api_roles(supabase_roles: None) -> None:
    """The default privileges that exposed every new table are gone."""
    _alembic("upgrade", REVISION)

    async with test_engine.connect() as conn:
        await conn.begin()
        await conn.execute(text("CREATE TABLE public.rls_probe_future_table (id int)"))
        for role in API_ROLES:
            for privilege in PRIVILEGES:
                granted = (
                    await conn.execute(
                        text(
                            "SELECT has_table_privilege(:role, 'public.rls_probe_future_table', :p)"
                        ),
                        {"role": role, "p": privilege},
                    )
                ).scalar()
                assert granted is False, f"{role} {privilege}"
        await conn.rollback()


async def test_revert_never_regrants_api_roles(supabase_roles: None) -> None:
    _alembic("upgrade", REVISION)
    await _release_connections()

    _alembic(*REVERT, "downgrade", PREVIOUS_REVISION)

    for role in API_ROLES:
        assert await _granted(role) == [], role


async def test_a_non_owner_migrating_role_is_refused_before_any_change() -> None:
    """ENABLE ROW LEVEL SECURITY needs ownership, and a REVOKE by a non-owner
    silently removes nothing, so the migration must refuse up front."""
    if not await _can_create_roles():
        _skip_or_fail("the test role can't create a non-owner role to migrate as")
    migration = _load_migration()
    probe = f"rls_probe_{uuid.uuid4().hex[:8]}"
    async with test_engine.begin() as conn:
        await conn.execute(text(f"CREATE ROLE {probe} NOLOGIN"))
    try:
        async with test_engine.connect() as conn:
            await conn.begin()
            await conn.execute(text(f"SET LOCAL ROLE {probe}"))
            with pytest.raises(migration.PublicSchemaProtectionRefused, match="not owned"):
                await conn.run_sync(migration._require_ownership)
            await conn.rollback()
    finally:
        async with test_engine.begin() as conn:
            await conn.execute(text(f"DROP ROLE {probe}"))
