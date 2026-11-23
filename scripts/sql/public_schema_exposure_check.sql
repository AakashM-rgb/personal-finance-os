-- Public-schema exposure check for Supabase's Data API (migration d7a1e4c9b3f2).
-- READ ONLY: only SELECTs, inside a READ ONLY transaction that ends in ROLLBACK.
-- Output: table names and counts only, never row data.
--
-- Run it before the release (it reports the exposure), right after the migration (every
-- count must be 0 and every table must show rls_enabled = true), and periodically
-- afterwards: Supabase's own tooling creates objects as supabase_admin, whose default
-- privileges still grant anon/authenticated, and a migration could forget RLS.
--
-- Grants are read straight from the ACLs (aclexplode) rather than tested privilege by
-- privilege, so roles that don't exist (local PostgreSQL, CI) simply count as 0. Grantee
-- PUBLIC is counted too, because anon inherits whatever PUBLIC is granted.
--
-- supabase_admin_default_grants is expected to stay above 0 on Supabase: those are
-- supabase_admin's own default privileges, which postgres cannot change and which apply only
-- to objects supabase_admin creates. Part 2 shows whether any such object exists. The
-- split is by grantor name, not current_user, so the result is the same whoever runs it.
--
-- Usage (URL from an environment variable, never typed on the command line):
--   psql "$DB_URL" -X -v ON_ERROR_STOP=1 -f scripts/sql/public_schema_exposure_check.sql
-- Guarded by backend/tests/test_f001_card_ledger_impact_check_sql.py (read-only rules) and
-- backend/tests/test_rls_hardening.py (what it reports).

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '120s';

\echo 'Part 1: summary (after d7a1e4c9b3f2 every count must be 0, except supabase_admin_default_grants)'
WITH api_grantees AS (
    SELECT oid AS grantee FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
    UNION ALL SELECT 0  -- PUBLIC
),
public_relations AS (
    SELECT c.oid, c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity, c.relacl
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
)
SELECT
    (SELECT version_num FROM alembic_version) AS alembic_revision,
    (SELECT count(*) FROM public_relations WHERE relkind IN ('r', 'p')) AS tables,
    (SELECT count(*) FROM public_relations WHERE relkind IN ('r', 'p') AND NOT relrowsecurity)
        AS tables_without_rls,
    (SELECT count(*) FROM public_relations WHERE relforcerowsecurity) AS tables_with_forced_rls,
    (SELECT count(*) FROM pg_policies WHERE schemaname = 'public') AS policies,
    (SELECT count(*) FROM public_relations r, aclexplode(r.relacl) a
      WHERE a.grantee IN (SELECT grantee FROM api_grantees)) AS api_role_relation_grants,
    (SELECT count(*) FROM pg_attribute att JOIN public_relations r ON r.oid = att.attrelid,
            aclexplode(att.attacl) a
      WHERE att.attacl IS NOT NULL AND a.grantee IN (SELECT grantee FROM api_grantees))
        AS api_role_column_grants,
    (SELECT count(*) FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace,
            aclexplode(d.defaclacl) a
      WHERE n.nspname = 'public' AND a.grantee IN (SELECT grantee FROM api_grantees)
        AND pg_get_userbyid(d.defaclrole) <> 'supabase_admin')
        AS api_role_default_grants,
    (SELECT count(*) FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace,
            aclexplode(d.defaclacl) a
      WHERE n.nspname = 'public' AND a.grantee IN (SELECT grantee FROM api_grantees)
        AND pg_get_userbyid(d.defaclrole) = 'supabase_admin')
        AS supabase_admin_default_grants,
    (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public') AS functions_in_public;

\echo 'Part 2: per relation'
SELECT c.relname AS relation,
       c.relkind AS kind,
       c.relrowsecurity AS rls_enabled,
       pg_get_userbyid(c.relowner) AS owner,
       (SELECT count(*) FROM aclexplode(c.relacl) a
         WHERE a.grantee = 0
            OR a.grantee IN (SELECT oid FROM pg_roles WHERE rolname IN ('anon', 'authenticated')))
           AS api_role_grants
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
ORDER BY c.relname;

ROLLBACK;
