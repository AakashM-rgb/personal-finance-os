"""protect the public schema from Supabase's Data API roles (RLS + revoke)

Production runs on Supabase, which serves an auto-generated REST API
(PostgREST) over the `public` schema as the roles `anon` and `authenticated`.
This app never uses that API -- the backend connects straight to PostgreSQL
with DATABASE_URL and authorizes every query itself, at the repository layer
-- but Supabase's default privileges had granted both roles every privilege
on every table the migrations created, and no table had row level security.
Anyone holding the project's publishable key could therefore read or rewrite
every row (including users.password_hash and sessions), or truncate tables.

Upgrade, in the migration's single transaction:

1. Refuses, naming them, if any table in `public` is not owned by the
   migrating role (and that role is not a superuser): ENABLE ROW LEVEL
   SECURITY needs ownership, and a REVOKE by a non-owner silently removes
   nothing.
2. For each Data API role that exists (`anon`, `authenticated`), revokes
   every privilege on every table, sequence and function in `public`, and
   revokes the default privileges the migrating role would otherwise hand
   those roles on objects it creates later.
3. Enables row level security on every table in `public`, with no policies.
4. Verifies the result before committing: if either role still holds any
   table, column or default privilege, or any table is left without RLS, it
   raises and the whole transaction rolls back.

Every ALTER waits at most 10 s for its lock (`LOCK_TIMEOUT`) and otherwise
fails, rolling back the whole upgrade, including c8e4a1f6b2d9's correction when
both run in one `alembic upgrade head`. Retry once the blocking session ends.

On a database without those roles (local development, CI by default) steps 2
and the role half of step 4 are skipped, so the migration runs everywhere.

Why the backend keeps working with no policies: it connects as the role that
owns the tables (`postgres` on Supabase, which also has BYPASSRLS; the
migrating role locally and in CI). A table's owner is not subject to its RLS
unless FORCE ROW LEVEL SECURITY is set, which is deliberately not done here:
there is no requirement for it and it would lock out the owner. With RLS on
and no policy, every other non-BYPASSRLS role sees no rows even if a grant is
later restored by mistake -- the two layers back each other up.

Deliberately left alone:
- `service_role`: its key is secret, server-side only, and bypasses RLS by
  design. Not used by this app; keep it out of every client.
- USAGE on schema `public`, which Supabase's own tooling expects.
- `supabase_admin`'s default privileges: only that role or a superuser can
  change them, `postgres` cannot, and they apply only to objects
  `supabase_admin` itself creates -- never to tables these migrations create.
- Future tables still need RLS enabled by the migration that creates them;
  default privileges cannot do that. tests/test_rls_hardening.py fails if any
  table at head lacks it, so a forgotten one fails CI.
- Functions: PostgreSQL grants EXECUTE on every new function to PUBLIC by a
  built-in default that a per-schema default-privilege revoke cannot remove,
  so a function added to `public` would be callable by `anon` over RPC. There
  are none, and tests/test_rls_hardening.py fails if a migration adds one.

Downgrade keeps the protection by default -- removing it would re-create the
exposure -- and only disables RLS when the operator passes
`-x rls_hardening=revert`. It never re-grants anything to `anon` or
`authenticated`; restoring Data API access is a deliberate, manual decision.

Revision ID: d7a1e4c9b3f2
Revises: c8e4a1f6b2d9
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.engine import Connection

revision: str = "d7a1e4c9b3f2"
down_revision: str | Sequence[str] | None = "c8e4a1f6b2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"
DATA_API_ROLES = ("anon", "authenticated")
MODE_ARG = "rls_hardening"
# Every table privilege PostgreSQL defines. Each is checked individually, and
# MAINTAIN only from PostgreSQL 17 (Supabase grants it; CI runs 16), because
# has_table_privilege rejects a privilege name the server does not know.
_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
_MAINTAIN_SINCE = 170000
# ENABLE/DISABLE ROW LEVEL SECURITY takes an ACCESS EXCLUSIVE lock on each
# table. c8e4a1f6b2d9 runs first in the same transaction and resets
# lock_timeout to the default (wait forever), so without this one stale session
# holding any table lock would stall the whole release instead of failing it.
LOCK_TIMEOUT = "10s"
# Column-level privileges a role can hold (has_table_privilege doesn't see them).
_COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")


class PublicSchemaProtectionRefused(RuntimeError):
    """Raised before or instead of committing, so Alembic rolls everything back."""


def _quote(bind: Connection, identifier: str) -> str:
    return bind.dialect.identifier_preparer.quote(identifier)


def _mode() -> str | None:
    raw = context.get_x_argument(as_dictionary=True)
    unknown = {k for k in raw if k.startswith(MODE_ARG) and k != MODE_ARG}
    if unknown:
        raise PublicSchemaProtectionRefused(f"Unknown option(s): {', '.join(sorted(unknown))}.")
    mode = raw.get(MODE_ARG)
    if mode is not None and mode != "revert":
        raise PublicSchemaProtectionRefused(f"-x {MODE_ARG} must be 'revert', got '{mode}'.")
    return mode


def _tables(bind: Connection) -> list[str]:
    return list(
        bind.execute(
            sa.text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind IN ('r', 'p') ORDER BY c.relname"
            ),
            {"schema": SCHEMA},
        ).scalars()
    )


def _existing_api_roles(bind: Connection) -> list[str]:
    return list(
        bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles) ORDER BY rolname"),
            {"roles": list(DATA_API_ROLES)},
        ).scalars()
    )


def _require_ownership(bind: Connection) -> None:
    is_superuser = bind.execute(
        sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    if is_superuser:
        return
    foreign = list(
        bind.execute(
            sa.text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind IN ('r', 'p') "
                "AND NOT pg_has_role(current_user, c.relowner, 'USAGE') ORDER BY c.relname"
            ),
            {"schema": SCHEMA},
        ).scalars()
    )
    if foreign:
        raise PublicSchemaProtectionRefused(
            f"Table(s) in {SCHEMA} not owned by the migrating role: {', '.join(foreign)}. "
            "Run this migration as their owner (the role the backend connects as). "
            "Nothing was changed."
        )


def _table_privileges(bind: Connection) -> tuple[str, ...]:
    version = int(bind.execute(sa.text("SHOW server_version_num")).scalar_one())
    return _TABLE_PRIVILEGES + (("MAINTAIN",) if version >= _MAINTAIN_SINCE else ())


def _revoke_api_roles(bind: Connection, roles: list[str]) -> None:
    grantees = ", ".join(_quote(bind, role) for role in roles)
    schema = _quote(bind, SCHEMA)
    me = _quote(bind, bind.execute(sa.text("SELECT current_user")).scalar_one())
    for object_kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        bind.execute(sa.text(f"REVOKE ALL ON ALL {object_kind} IN SCHEMA {schema} FROM {grantees}"))
        bind.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {me} IN SCHEMA {schema} "
                f"REVOKE ALL ON {object_kind} FROM {grantees}"
            )
        )


def _remaining_grants(bind: Connection, roles: list[str]) -> list[str]:
    remaining = []
    privileges = _table_privileges(bind)
    for role in roles:
        for privilege in privileges:
            tables = bind.execute(
                sa.text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :schema AND c.relkind IN ('r', 'p', 'v', 'm') "
                    "AND has_table_privilege(:role, c.oid, :privilege)"
                ),
                {"schema": SCHEMA, "role": role, "privilege": privilege},
            ).scalars()
            remaining.extend(f"{role} {privilege} on {table}" for table in tables)
        # A table-level REVOKE also drops column-level grants (PostgreSQL docs);
        # verified rather than assumed.
        for privilege in _COLUMN_PRIVILEGES:
            tables = bind.execute(
                sa.text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :schema AND c.relkind IN ('r', 'p', 'v', 'm') "
                    "AND has_any_column_privilege(:role, c.oid, :privilege)"
                ),
                {"schema": SCHEMA, "role": role, "privilege": privilege},
            ).scalars()
            remaining.extend(f"{role} column {privilege} on {table}" for table in tables)
        defaults = bind.execute(
            sa.text(
                "SELECT count(*) FROM pg_default_acl d "
                "JOIN pg_namespace n ON n.oid = d.defaclnamespace, aclexplode(d.defaclacl) a "
                "WHERE n.nspname = :schema AND d.defaclrole = "
                "(SELECT oid FROM pg_roles WHERE rolname = current_user) "
                "AND a.grantee = (SELECT oid FROM pg_roles WHERE rolname = :role)"
            ),
            {"schema": SCHEMA, "role": role},
        ).scalar()
        if defaults:
            remaining.append(f"{role}: {defaults} default privilege(s) for future objects")
    return remaining


def _tables_without_rls(bind: Connection) -> list[str]:
    return list(
        bind.execute(
            sa.text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind IN ('r', 'p') "
                "AND NOT c.relrowsecurity ORDER BY c.relname"
            ),
            {"schema": SCHEMA},
        ).scalars()
    )


def upgrade() -> None:
    if context.is_offline_mode():
        raise PublicSchemaProtectionRefused(
            "This revision inspects live roles and tables; it can't be rendered as offline SQL."
        )
    _mode()  # reject typos in the flag on the way up too
    bind = op.get_bind()
    bind.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    _require_ownership(bind)

    roles = _existing_api_roles(bind)
    if roles:
        _revoke_api_roles(bind, roles)

    for table in _tables(bind):
        qualified = f"{_quote(bind, SCHEMA)}.{_quote(bind, table)}"
        bind.execute(sa.text(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY"))

    problems = _remaining_grants(bind, roles) + [
        f"{table} has no row level security" for table in _tables_without_rls(bind)
    ]
    if problems:
        raise PublicSchemaProtectionRefused(
            "The public schema is still exposed after hardening: "
            + "; ".join(problems)
            + ". Nothing was committed."
        )


def downgrade() -> None:
    if context.is_offline_mode():
        raise PublicSchemaProtectionRefused(
            "This revision inspects live tables; it can't be rendered as offline SQL."
        )
    if _mode() != "revert":
        # Moving the revision pointer back must not silently re-expose data:
        # RLS stays on and the revoked grants stay revoked. The owner-run
        # backend is unaffected either way.
        return
    bind = op.get_bind()
    bind.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    _require_ownership(bind)
    for table in _tables(bind):
        qualified = f"{_quote(bind, SCHEMA)}.{_quote(bind, table)}"
        bind.execute(sa.text(f"ALTER TABLE {qualified} DISABLE ROW LEVEL SECURITY"))
