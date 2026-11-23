# Release runbook: `fix/credit-card-ledger-semantics`

The step-by-step operator checklist for releasing this branch: Data API containment, a tested
backup, the eight commits, then the two migrations (`c8e4a1f6b2d9` F-001 correction,
`d7a1e4c9b3f2` RLS) and the backend and frontend. The reasoning behind each safeguard is in
[DEPLOYMENT.md](DEPLOYMENT.md) (sections 4 and 10). This page lists what to do, in order.

**Status (re-verified read-only on 2026-11-23).** Nothing has been done in production. Production
Supabase (`zomkpjmpodescgprigxr`, PostgreSQL 17.11) is at `a3f9c1d2e7b4`. Its Data API is running,
all 20 `public` tables have RLS off, and `anon`/`authenticated` hold 320 table grants plus 24
default grants. It has 1 user, 1 session, 0 accounts, 0 credit cards and 0 transactions. Render
(`personal-finance-os`, free plan) deploys `feat/automatic-transaction-sync` at `3b07a95` with
auto-deploy on. Vercel's production branch is the **same** branch. Every production step below
needs the owner's explicit approval at the time it is done.

## Conventions (read once)

- **Shell: Windows PowerShell 5.1.** Every command below was checked on this machine.
- **`curl` is not curl in PowerShell 5.1.** It is an alias for `Invoke-WebRequest`. Always type
  `curl.exe`.
- **Never type a secret on a command line.** PSReadLine saves every line you type to
  `%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt`. Secrets are read
  with `Read-Host -AsSecureString`, which echoes nothing, and are passed through environment
  variables or variables.
- **Two windows, never mixed.**
  - The **PROD** window holds the production connection (`PG*` variables). Its title says PROD.
  - The **LOCAL** window holds only the throwaway restore cluster. Open it fresh, and confirm
    `Get-ChildItem Env:PG*, Env:ALEMBIC_DATABASE_URL -ErrorAction SilentlyContinue` prints
    nothing.
  - libpq reads `PGHOST`/`PGUSER`/`PGPASSWORD`, so a command that forgets `-h` connects wherever
    those point.
- **PostgreSQL tools:** `$env:Path = "C:\Program Files\PostgreSQL\18\bin;$env:Path"` in each
  window. Client 18 is newer than server 17, which is what `pg_dump` requires.
- **Python: no activation.** From `D:\finance-app\backend`, run
  `.\.venv\Scripts\python.exe -m alembic …`. This avoids `Activate.ps1` and execution-policy
  prompts, and it can't pick up another Python. The venv has the lock's versions (alembic
  1.20.1, SQLAlchemy 2.1.9, asyncpg 0.32.0, Python 3.13).
- **Two URL forms for the same database.**
  - `psql`/`pg_dump` use libpq (`PG*` variables, `sslmode=require`).
  - Alembic uses SQLAlchemy's `postgresql+asyncpg://…?ssl=require`.
  - Neither accepts the other's form, so §2 sets both.
- **Don't pipe `pg_ctl start`** (`| Out-Null`): the server inherits the pipe and the command
  never returns.

## 0. Order of operations

| # | Step | Changes | Reversible? |
|---|---|---|---|
| 1 | Contain: turn the Supabase Data API off | Supabase setting | Yes (toggle) |
| 2 | Back up, test the restore, rehearse the migration on the copy | Nothing in prod (read-only dump) | — |
| 3 | Create the 8 commits; push the **fix** branch; CI green | Local git, then GitHub (a branch Render doesn't deploy) | Yes |
| 4 | Pre-flight: read Render and Vercel settings | Nothing | — |
| 5 | Render: auto-deploy **off**, then **suspend** | Render setting | Yes |
| 6 | Migrate out of band, verify | Production database | See Rollback |
| 7 | Fast-forward the deployed branch | GitHub; **starts the Vercel production deploy** | Yes |
| 8 | Render (still suspended): build command, `PYTHON_VERSION`, health check path | Render settings | Yes |
| 9 | Resume through the gate | Render | Yes |
| 10 | Post-deployment verification | Nothing | — |
| 11 | The production user changes their password | User data | No |
| 12 | Auto-deploy back on | Render setting | Yes |

Why this order differs from the previous draft:
- **Merge (7) only while the backend is suspended.** Vercel deploys the merged branch to
  production immediately. The new frontend calls `/auth/delete-account` and reads
  `over_limit_minor`, which the old backend doesn't have.
- **Render settings (8) only after the migration.** On 2026-11-14 a settings change started a
  deploy by itself (`trigger: service_updated`). Before the merge, that deploy would build the old
  commit, which has no `requirements.lock`. After the merge but before the migration, the new code
  would migrate from the start command, during the old-instance overlap.

## 1. Contain: turn the Supabase Data API off

The app never uses Supabase's REST API. The backend connects to PostgreSQL directly with
`DATABASE_URL`, auth is the app's own, and receipts are on disk or S3. Turning the Data API off
therefore changes nothing for users. Do it before anything else.

1. **Open the right project.** Go to
   `https://supabase.com/dashboard/project/zomkpjmpodescgprigxr`.
   - The address bar must contain `zomkpjmpodescgprigxr`.
   - `ghzgqdbeqoklktnocvet` is staging: stop and pick the other project.
2. **Record the "before" state** in a new PowerShell window.
   - Project Settings → **API Keys**: copy the **publishable** key. Older projects call it
     **anon**, and it starts `sb_publishable_` or `eyJ`.
   - Never use the **secret** / **service_role** key.
   ```powershell
   $sec = Read-Host 'Paste the publishable key (input is hidden)' -AsSecureString
   $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
   $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
   [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
   curl.exe -s -o NUL -w "HTTP %{http_code}`n" "https://zomkpjmpodescgprigxr.supabase.co/rest/v1/users?select=id&limit=0" -H "apikey: $key"
   ```
   - *Expected now:* `HTTP 200`. That is the exposure (`limit=0` reads no rows).
   - Any other code (`401` = wrong key) means the probe itself is broken. Fix the key before
     going on, or step 5 proves nothing.
3. **Find the setting.** Left sidebar → **Integrations** → **Data API**, or go to
   `https://supabase.com/dashboard/project/zomkpjmpodescgprigxr/integrations/data_api/overview`.
   *Expected:* a page with an **Enable Data API** switch, and the API URL and exposed schemas
   below it (on the Settings tab).
4. **Turn it off.**
   - Switch **Enable Data API** off.
   - If a confirmation dialog appears, confirm it. If there's a **Save** button, click it and wait
     for the success message.
   - *Expected:* the switch is still off after reloading the page (F5).
5. **Prove it.** Run the `curl.exe` line again in the same window. Press the up arrow: it reuses
   `$key` and contains no secret.
   - *Expected:* anything but `HTTP 200`, often 404 or 503. Containment is proven only by this
     result.
   - `HTTP 200` means it is still exposed. Repeat step 4, or remove `public` from **Exposed
     schemas** on the Settings tab.
6. **Check for past access.**
   - Left sidebar → **Logs** → **API Gateway**, filtered to paths starting `/rest/v1/`. Or use
     **Logs Explorer** with:
     ```sql
     select timestamp, request.method, request.path, response.status_code
     from edge_logs
       cross join unnest(metadata) as m
       cross join unnest(m.request) as request
       cross join unnest(m.response) as response
     where request.path like '/rest/v1/%'
     order by timestamp desc
     limit 200
     ```
   - Click any row to see its full metadata, including the client IP.
   - *Expected:* only your own two requests from steps 2 and 5. Anything else means the exposure
     was used: other IPs, other tables, or any `POST`/`PATCH`/`DELETE`. Save those entries, treat
     the production data as read, and make §11 urgent.
   - Log retention depends on the plan (about 1 day on Free), so older access is not visible here.
   - Independent evidence (read-only, 2026-11-23): `extensions.pg_stat_statements`, collecting
     since 2026-11-11 10:51 UTC, shows no PostgREST data query, only its connection housekeeping.
     That covers the period from 2026-11-11 only, and only while statements weren't evicted from
     the stats.
7. **Clear the key:** `Remove-Variable sec, key, b` and close the window.

Report the step 5 result before continuing. The exposure is not contained until it is non-200.

## 2. Back up, test the restore, rehearse

### 2.1 Open the PROD window (read-only use in this section)

Supabase Dashboard → **Connect** (top bar) → **Session pooler**. Note the host, the port (5432)
and the user (`postgres.zomkpjmpodescgprigxr`). The database is `postgres`.

- Use the **session** pooler. The transaction pooler (port 6543) breaks asyncpg's prepared
  statements.
- The direct host `db.zomkpjmpodescgprigxr.supabase.co` is IPv6-only unless the IPv4 add-on is
  on.
- **Don't click "Reset database password".** The Render backend's `DATABASE_URL` uses the
  current password, and resetting it takes production down. If you don't have the password, stop
  and decide that separately.

```powershell
$Host.UI.RawUI.WindowTitle = 'PROD zomkpjmpodescgprigxr'
$env:Path = "C:\Program Files\PostgreSQL\18\bin;$env:Path"
$env:PGHOST = Read-Host 'Session pooler host (from Connect)'
$env:PGPORT = '5432'
$env:PGDATABASE = 'postgres'
$env:PGUSER = 'postgres.zomkpjmpodescgprigxr'
$env:PGSSLMODE = 'require'
$sec = Read-Host 'Database password (input is hidden)' -AsSecureString
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b); Remove-Variable sec, b
psql -X -At -c "select current_user, current_database(), (select version_num from alembic_version)"
```

*Expected:* `postgres|postgres|a3f9c1d2e7b4`. The pooler routes by the project ref in `PGUSER`, so
a wrong ref fails to log in rather than reaching another project.

### 2.2 Back up (read-only for the database)

```powershell
$dir = "$env:USERPROFILE\finance-release-backup"
New-Item -ItemType Directory -Force $dir | Out-Null
icacls $dir /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" | Out-Null
$dump = Join-Path $dir ("prod-public-{0}.dump" -f (Get-Date -Format 'yyyyMMdd-HHmm'))
pg_dump --format=custom --schema=public --no-password --file="$dump"; "pg_dump exit=$LASTEXITCODE"
(pg_restore --list "$dump" | Select-String ' TABLE DATA public ').Count
Get-FileHash $dump -Algorithm SHA256
$dump
```

*Expected:* `pg_dump exit=0`, then `20` (the 20 tables, `alembic_version` included), then a hash
to note in the deploy record.

Why these choices:
- **`--schema=public`.** Every application table lives in `public`, and no table default uses an
  extension. Supabase's own schemas (auth, storage, vault, …) are platform-managed, the app
  doesn't use them, and they don't restore into plain PostgreSQL.
- **Owners and ACLs are kept** (no `--no-owner`/`--no-acl`). The rehearsal in 2.4 then reproduces
  production's grants exactly.

Protecting the file:
- It holds password hashes, and `icacls` limits the folder to your Windows user.
- Windows Home has no EFS, so keep it on a BitLocker-protected drive or in an encrypted archive.
- Never put it in the repository. Delete it once the release is settled.
- Supabase's own backups (Database → Backups) depend on the plan. Check that page; don't assume
  one exists.

### 2.3 Test the restore (LOCAL window, a new PowerShell window)

```powershell
$Host.UI.RawUI.WindowTitle = 'LOCAL restore test'
Get-ChildItem Env:PG*, Env:ALEMBIC_DATABASE_URL -ErrorAction SilentlyContinue   # must print nothing
$env:Path = "C:\Program Files\PostgreSQL\18\bin;$env:Path"
$dump = '<paste the path the PROD window printed>'
$rt = "$env:USERPROFILE\finance-release-backup\restore-test"
initdb -D $rt -U restore --auth=trust -E UTF8
pg_ctl -D $rt -o "-p 55433 -c listen_addresses=127.0.0.1" -l "$rt.log" -w start
psql -h 127.0.0.1 -p 55433 -U restore -d postgres -X -q -v ON_ERROR_STOP=1 -c "CREATE ROLE postgres LOGIN BYPASSRLS" -c "CREATE ROLE supabase_admin NOLOGIN" -c "CREATE ROLE anon NOLOGIN" -c "CREATE ROLE authenticated NOLOGIN" -c "CREATE ROLE service_role NOLOGIN BYPASSRLS" -c "CREATE DATABASE prod_copy OWNER postgres"
pg_restore -h 127.0.0.1 -p 55433 -U restore -d prod_copy --clean --if-exists --exit-on-error "$dump"; "pg_restore exit=$LASTEXITCODE"
```

The pre-created roles are exactly the ones production's `public` ACLs name (checked 2026-11-23).
`postgres` is a non-superuser with BYPASSRLS, as on Supabase. `--clean --if-exists` is needed
because the dump re-creates schema `public`, which a new database already has.

**Compare row counts.** Run the same query in both windows. In PROD use `psql -X -At -c $counts`,
and in LOCAL use `psql -h 127.0.0.1 -p 55433 -U postgres -d prod_copy -X -At -c $counts`.

```powershell
$counts = "SELECT table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from public.%I', table_name), false, true, '')))[1]::text::bigint AS row_count FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1;"
```

*Expected:* identical lists, for example `users|1`, `sessions|1`, `audit_logs|1`, `accounts|0`,
`transactions|0`. A backup you haven't restored is not a backup.

**Confirm the grants came across.** In LOCAL:
`psql -h 127.0.0.1 -p 55433 -U postgres -d prod_copy -X -f D:\finance-app\scripts\sql\public_schema_exposure_check.sql`.
Part 1 must show production's baseline: 20 tables, 20 without RLS, 320 relation grants, 24 + 24
default grants.

### 2.4 Rehearse the migration on the copy (LOCAL window)

Run this from the committed tree after §3 if you can. Before §3 the working tree has the same
content.

```powershell
Set-Location D:\finance-app
psql -h 127.0.0.1 -p 55433 -U postgres -d prod_copy -X -v ON_ERROR_STOP=1 -f scripts\sql\f001_card_ledger_impact_check.sql
$env:ALEMBIC_DATABASE_URL = 'postgresql+asyncpg://postgres@127.0.0.1:55433/prod_copy'
Set-Location backend
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
Set-Location ..
psql -h 127.0.0.1 -p 55433 -U postgres -d prod_copy -X -v ON_ERROR_STOP=1 -f scripts\sql\f001_card_ledger_post_migration_check.sql
psql -h 127.0.0.1 -p 55433 -U postgres -d prod_copy -X -v ON_ERROR_STOP=1 -f scripts\sql\public_schema_exposure_check.sql
```

*Expected* (this exact sequence was run on 2026-11-23 against a Supabase-like copy at
`a3f9c1d2e7b4`):
- **Impact check:** `credit_card_accounts = 0` and `cards_needing_correction = 0`.
- **`alembic current`:** `a3f9c1d2e7b4` before the upgrade, `d7a1e4c9b3f2 (head)` after it.
- **Upgrade:** it logs `a3f9c1d2e7b4 -> c8e4a1f6b2d9` and then `c8e4a1f6b2d9 -> d7a1e4c9b3f2`.
- **Post-migration check:**
  - Part 1 has a summary row with `mode = none`.
  - Part 2 shows all zeros.
  - Part 3 shows `card_legs_written_in_window = 0`.
- **Exposure check:**
  - Part 1 shows `tables = 21` (the new `data_correction_runs`), and every other count is 0 except
    `supabase_admin_default_grants = 24`.
  - Part 2 shows `rls_enabled = t` and `api_role_grants = 0` on every row.
- **Optional downgrade check:**
  - `.\.venv\Scripts\python.exe -m alembic downgrade c8e4a1f6b2d9` followed by the exposure check
    must still show all zeros, so the protection is kept.
  - Then run `… upgrade head` again.

Any refusal here would also happen in production. Fix it before touching production.

**Clean up:**
```powershell
Remove-Item Env:ALEMBIC_DATABASE_URL
pg_ctl -D $rt stop -m fast
Remove-Item -Recurse -Force $rt, "$rt.log"
```

## 3. The eight commits, the push and CI (approval required)

`$env:USERPROFILE\finance-release-prep\` holds the plan (`commit_plan.py`), the
`receipt_service.py` variant for commit 3 (`receipt_service.commit3.py`, with its SHA-256 pinned
in the script) and `commit_release.ps1`.

The script:
- checks the branch, `HEAD = fe7fec5`, the 102 pending files against the plan, the variant's hash,
  and an empty index;
- creates the 8 commits, checking each commit's file list against the plan;
- swaps `receipt_service.py` for commit 3 and restores it, even on failure;
- ends by requiring a clean tree, which proves `HEAD`'s tree is exactly the tested working tree.

It never pushes. It was run end to end on a throwaway clone on 2026-11-23.

```powershell
Set-Location D:\finance-app
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\finance-release-prep\commit_release.ps1" -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\finance-release-prep\commit_release.ps1"
git log --oneline fe7fec5..HEAD          # 8 lines
git status --porcelain                    # nothing
git rev-parse HEAD                        # the release SHA; write it down
```

Git's "LF will be replaced by CRLF" warnings are expected (`core.autocrlf=true`) and harmless.

**Push the fix branch for CI** (approval):
`git push -u origin fix/credit-card-ledger-semantics`.
- Render doesn't deploy this branch.
- Vercel builds a *Preview* deployment of it. Its Preview `BACKEND_ORIGIN` points at a backend;
  don't use the preview for testing before §9.
- Then open `https://github.com/AakashM-rgb/personal-finance-os/actions`. The **CI** run for the
  release SHA must show **backend** and **frontend** both green.

## 4. Pre-flight (read-only dashboard checks)

- **Render** → `personal-finance-os` → **Environment.** Compare names only; never copy values
  anywhere.
  - `ENVIRONMENT` is `production`.
  - `CORS_ORIGINS` lists `https://personal-finance-os-six-sandy.vercel.app` and contains **no
    `*`**. The new backend refuses to start in production with a wildcard, and the deploy in §9
    would then fail.
  - `DATABASE_URL`, `TEST_DATABASE_URL` and `JWT_SECRET_KEY` exist.
  - `PYTHON_VERSION` is absent today (added in §8).
- **Vercel** → `personal-finance-os` → Settings → **Environment Variables**: `BACKEND_ORIGIN`
  (Production) is `https://personal-finance-os-ug9o.onrender.com`, and `NEXT_PUBLIC_API_URL` is
  not set.
- **Vercel** → Settings → **Git**: the Production Branch is `feat/automatic-transaction-sync`.

## 5. Stop writes (approval)

1. Render Dashboard → `personal-finance-os` → **Settings** → **Build & Deploy** → **Auto-Deploy**
   → **Off** → Save. Confirm it reads Off.
2. Same page, bottom → **Suspend Web Service** → confirm.
   - *Expected:* the service header shows **Suspended**, and
     `curl.exe -s -o NUL -w "HTTP %{http_code}`n" https://personal-finance-os-ug9o.onrender.com/api/v1/health`
     no longer returns 200.
   - Record the time.

## 6. Migrate out of band (PROD window, approval)

Use the PROD window from §2.1 (re-open it the same way if it was closed).

1. **Pre-migration checks** (read-only):
   ```powershell
   Set-Location D:\finance-app
   git status --porcelain; git rev-parse HEAD          # clean, and the release SHA from §3
   psql -X -At -c "select version_num from alembic_version"     # a3f9c1d2e7b4
   psql -X -At -c $counts                                        # write the numbers down
   psql -X -v ON_ERROR_STOP=1 -f scripts\sql\f001_card_ledger_impact_check.sql
   psql -X -v ON_ERROR_STOP=1 -f scripts\sql\public_schema_exposure_check.sql
   ```
   (`$counts` is defined in §2.3; define it in this window too.)
   - **Hard gate:** the impact check must show `credit_card_accounts = 0`. With any card, the free
     plan's resume path (§9) can briefly run the old code on corrected data. Stop, and don't use
     this procedure.
   - Keep the exposure check output as the "before" record: 20 / 320 / 24 / 24.
2. **Migrate:**
   ```powershell
   Set-Location D:\finance-app\backend
   $env:ALEMBIC_DATABASE_URL = "postgresql+asyncpg://$($env:PGUSER):$([uri]::EscapeDataString($env:PGPASSWORD))@$($env:PGHOST):$($env:PGPORT)/$($env:PGDATABASE)?ssl=require"
   .\.venv\Scripts\python.exe -m alembic current       # must print a3f9c1d2e7b4: confirms the target
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m alembic current       # d7a1e4c9b3f2 (head)
   Remove-Item Env:ALEMBIC_DATABASE_URL
   ```
   - Never print `$env:ALEMBIC_DATABASE_URL`. `migrations/env.py` escapes the `%` from
     percent-encoding.
   - No `-x` flag is needed with zero cards.
   - Both revisions run in **one transaction**, so a refusal or error in either changes nothing.
     `PublicSchemaProtectionRefused: … not owned by the migrating role` means the user isn't
     `postgres`. `lock timeout` means another session holds a lock (with the service suspended,
     usually a dashboard SQL tab): close it and re-run.
3. **Verify** (read-only):
   ```powershell
   Set-Location D:\finance-app
   psql -X -v ON_ERROR_STOP=1 -f scripts\sql\f001_card_ledger_post_migration_check.sql
   psql -X -v ON_ERROR_STOP=1 -f scripts\sql\public_schema_exposure_check.sql
   psql -X -At -c $counts
   ```
   - **Post-migration check:** the summary row has `mode = none`, Part 2 shows all zeros, and
     `card_legs_written_in_window = 0`.
   - **Exposure check:** the same results as the §2.4 rehearsal.
   - **Counts:** the same as step 1, except `audit_logs` +1 and the new `data_correction_runs` = 1.

## 7. Fast-forward the deployed branch (approval; this is the frontend production deploy)

```powershell
Set-Location D:\finance-app
git fetch origin
git merge-base --is-ancestor origin/feat/automatic-transaction-sync HEAD; "fast-forward possible: $($LASTEXITCODE -eq 0)"
git push origin fix/credit-card-ledger-semantics:feat/automatic-transaction-sync
git ls-remote origin refs/heads/feat/automatic-transaction-sync     # must equal git rev-parse HEAD
```

- Without `--force`, the push is refused unless it is a fast-forward. The deployed branch then
  carries exactly the SHA CI tested.
- **Vercel starts a production build now** (the backend is suspended, so the site is down
  meanwhile).
- Render does nothing: it is suspended and auto-deploy is off.
- Check the build with
  `vercel ls personal-finance-os --environment production` (in `frontend\`): the newest is
  **Ready**. Then run `vercel inspect <that url> --logs`; it must show
  `Commit: <release SHA short>`.

## 8. Render settings, still suspended (approval)

These may start a build by themselves. That's now harmless: the database is already at head, so
the start command's `alembic upgrade head` does nothing.

1. **Settings → Build & Deploy → Build Command** → `pip install -c requirements.lock .` → Save.
   The root directory is `backend/`, where the lock is.
2. **Environment → Add Environment Variable** → `PYTHON_VERSION` = `3.13.13` → Save. Pick **Save
   only** if offered.
   - It must be fully qualified.
   - Without it this service builds with 3.14.3, its creation-date default. The lock is tested on
     3.13 only.
   - `backend/.python-version` is not relied on, because Render reads that file from the repo root.
3. **Settings → Health Checks → Health Check Path** → `/api/v1/health` → Save. The endpoint is
   liveness only, with no database access.
4. Leave the start command as it is.

## 9. Resume through the gate (approval)

1. **Settings → Resume Web Service.**
2. Render's docs don't say whether a resume rebuilds the latest commit or restarts the last deploy.
   Open **Events** and the newest deploy.
   - If its commit is not the release SHA, click **Manual Deploy → Deploy latest commit** right
     away.
   - Until that deploy is live, the old code serves the migrated data. That is acceptable only
     because of the §6 zero-card gate. Don't use the app meanwhile.
3. **Gate.** All of these must hold before you use or announce the service. If any fails, suspend
   again (the data stays correct), read the log and fix forward.
   - The live deploy's commit is the release SHA, and its status is **Live**.
   - The build log shows Python **3.13.13** and `pip install -c requirements.lock .`.
   - The start log shows alembic with no `Running upgrade` line, then `Uvicorn running`.
   - `curl.exe -sS -i https://personal-finance-os-ug9o.onrender.com/api/v1/health` returns
     `HTTP/1.1 200`, the body `{"data":{"status":"ok"},"error":null,"meta":null}` and an
     `x-request-id` header. A cold start takes about a minute, so retry.

## 10. Post-deployment verification

Work through the checklist in the release report. Its core:

- [ ] Data API is still off (the §1 `curl.exe` is non-200), and the exposure check is still all
      zeros.
- [ ] `curl.exe -sI https://personal-finance-os-ug9o.onrender.com/api/v1/health` shows
      `x-content-type-options: nosniff`, `x-frame-options: DENY` and `x-request-id`.
- [ ] `curl.exe -sI https://personal-finance-os-six-sandy.vercel.app/` shows
      `content-security-policy` and `strict-transport-security`.
- [ ] In a browser:
  - register a throwaway account, log in, **reload and stay signed in**, then add an expense and
    see it on the dashboard;
  - add a credit card: a card expense raises "owed", and a bank → card payment lowers it and
    leaves net worth unchanged;
  - delete the throwaway account (Settings → Security), then confirm the login fails.
- [ ] Render logs show no traceback and no unexpected 5xx since the deploy. The browser console
      shows no CORS error.

## 11. The exposed account (approval)

The one production user's password hash and session were readable, and writable, while the Data
API was open. Once §1 and §6 are done, that user changes their password in Settings → Security.
That revokes every session, including any minted from leaked data.

## 12. Restore the deploy settings

Turn **Auto-Deploy** back on only after §10 passes.

## Rollback

**Code and database are rolled back differently.**

- **Code** (a Render redeploy of the previous deploy, or Vercel's promote-previous) is instant and
  touches no data.
  - The previous backend is the pre-fix ledger code. Once card transactions exist, never roll the
    backend back past this release without also reverting the correction.
  - The previous frontend lacks account deletion, but is otherwise compatible.
- **Database** changes are reverted only by a migration downgrade or a restore:
  - **`d7a1e4c9b3f2` (RLS): never revert it to recover from an app problem.** The app doesn't
    depend on it (the owner bypasses RLS), so it cannot be the cause.
    - A plain `alembic downgrade` past it deliberately leaves RLS on and the grants revoked
      (rehearsed 2026-11-23).
    - `-x rls_hardening=revert` disables RLS but still never re-grants.
    - Neither re-opens the Data API by itself.
  - **`c8e4a1f6b2d9` (F-001):** `alembic -x card_balance_correction=revert downgrade a3f9c1d2e7b4`
    subtracts exactly the recorded correction. With 0 cards it changes no balance.
  - **Restore** from the §2 dump is the last resort.
    - Restore into a **new** Supabase project, or after a deliberate decision, never as a reflex.
    - A restore is only consistent because writes were stopped, and it discards everything written
      since.

**Failure handling.**

| Symptom | Meaning | Action |
|---|---|---|
| §1 curl still 200 | Data API still serving | Re-check the toggle; or remove `public` from Exposed schemas |
| Migration refuses (`CardBalanceCorrectionRefused` / `PublicSchemaProtectionRefused`) | Nothing changed (one transaction) | Read the message, fix the cause, re-run |
| `lock timeout` during migration | Another session holds a lock | Close it (dashboard SQL tabs), re-run |
| `alembic current` in §6 doesn't print `a3f9c1d2e7b4` first | Wrong target or wrong URL | Stop; `Remove-Item Env:ALEMBIC_DATABASE_URL`; re-check §2.1 |
| Deploy fails after resume | Render keeps the previous (pre-fix) image | Suspend, read the build/start log (Python version, lock install, `CORS_ORIGINS`), fix forward |
| Health 200 but API calls fail | DB connectivity or config | Find the request in Render logs by `X-Request-Id`; don't touch the migrations |
| Exposure check shows grants after the release | Someone re-granted, or Supabase created objects | Investigate first; the Data API toggle (§1) is the immediate fix |
