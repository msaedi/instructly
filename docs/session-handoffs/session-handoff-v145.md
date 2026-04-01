# InstaInstru Session Handoff v145
*Generated: March 31, 2026*
*Previous: v144 | Current: v145 | Next: v146*

## 🎯 Session v145 Summary

**Production Database Hardening — Password Rotation, Dedicated Pooler Migration, Script Safety, Backup Verification, Silent Bug Discovery**

Audited the January 2026 data protection infrastructure (82 days unverified), discovered and fixed a silent region embeddings failure, rotated all database passwords, migrated both environments off Supabase's shared Supavisor pooler to dedicated PgBouncer (eliminating a circuit-breaker DoS vector), hardened destructive scripts with tiered hostname confirmation, removed dead service-URL code, and made the backup verification workflow actually verify.

| Objective | Status |
|-----------|--------|
| **Audit January data protection work (82 days old)** | ✅ Both agents confirmed backup workflows healthy |
| **Password rotation (preview + prod)** | ✅ 48-char URL-safe random passwords |
| **Dedicated PgBouncer pooler migration** | ✅ Both environments off shared Supavisor |
| **IPv4 add-on enabled** | ✅ Both Supabase projects |
| **Fix `options` startup parameter for PgBouncer** | ✅ PR #369 + follow-up merged |
| **Script hardening (hostname blocklist, CI guard, SITE_MODE fix)** | ✅ PR merged |
| **Dead service-URL code removal** | ✅ resolve_service_db_url + 4 config fields removed |
| **Backup verification hardening** | ✅ PR merged |
| **Region embeddings silent failure discovered and fixed** | ✅ 262/262 on both environments |
| **Flower auth verified** | ✅ Strong passwords on both services |

---

## 🔒 Data Protection Audit (January 2026 Work)

Reviewed the data protection handoff from January 7, 2026. Two independent agents audited the backup infrastructure, destructive scripts, database roles, GitHub secrets, and weak passwords.

### Backup Workflow Health
- Daily backups: 100% success rate over 82 days (zero failures since Jan 7 setup day)
- Weekly verification: 100% reported success — but actually masking 53 `pg_restore` errors via `|| true`
- Verification was querying non-existent `services` table (should be `instructor_services`)
- pg17 dump restored into pg14 container (version mismatch)

### Weak Passwords Found
- Preview and prod postgres passwords: 23-char, human-readable, word-based
- Preview and prod shared the SAME password (reuse across projects)
- Flower default: `admin:password` (verified and confirmed already set to strong on Render)
- `service_role` in local `.env`: `ServicePassword` — investigated and confirmed dead/unused

### Script Safety Gaps
- `reset_schema.py` bypassed `database_config.py` entirely with its own `resolve_db_url()`
- `prep_db.py` had same issue (own resolver, not using `DatabaseConfig`)
- `SITE_MODE=prod` on production server SKIPPED the interactive confirmation (backwards)
- `--force --yes` could silently destroy production on both scripts
- No CI guard — non-INT targets could run in GitHub Actions
- No hostname detection — scripts didn't validate if URL pointed to Supabase

---

## 🔑 Password Rotation + Dedicated Pooler Migration

### Password Rotation Process (learned from preview, applied to prod)

**Critical lesson learned:** Supabase's shared Supavisor pooler has a **circuit breaker** that blocks ALL connections (not just the bad one) after repeated auth failures. During preview rotation, Render bounced with old credentials before the new password propagated, tripping the circuit breaker and locking us out for ~15 minutes.

**Correct rotation sequence (established through trial and error):**
1. Pause Render service FIRST
2. Change password in Supabase dashboard
3. Update Render env vars
4. Update GitHub secrets
5. Wait 1-2 minutes for propagation
6. Test from terminal BEFORE resuming Render
7. Resume Render

### Dedicated PgBouncer Migration

Discovered that the shared Supavisor's circuit breaker is a denial-of-service vector — anyone with the project ref who sends wrong passwords can lock out ALL connections, including the app. Tested and confirmed that the dedicated PgBouncer (included with Micro Compute) uses **fail2ban instead** — bans only the offending IP, not everyone.

**Connection string changes (both environments):**

| Component | Old (shared Supavisor) | New (dedicated PgBouncer / direct) |
|-----------|----------------------|-----------------------------------|
| Username | `postgres.PROJECT_REF` | `postgres` |
| Hostname | `aws-X-us-east-1.pooler.supabase.com` | `db.PROJECT_REF.supabase.co` |
| Transaction pooler (port 6543) | Supavisor | PgBouncer |
| Session/direct (port 5432) | Supavisor session mode | Direct PostgreSQL connection |
| Scheme | `postgresql://` | `postgresql://` (not `postgres://` — SQLAlchemy rejects it) |

**IPv4 add-on** ($4/month per project) required because `db.PROJECT_REF.supabase.co` is IPv6-only by default, and Render is IPv4-only.

### PgBouncer Compatibility Fix — PR #369 + Follow-up

PgBouncer rejects the PostgreSQL `options` startup parameter (`FATAL: unsupported startup parameter: options`). Our engines used it to set per-engine `statement_timeout`.

**Fix:** Replaced startup `options` with post-connect `SET statement_timeout` via SQLAlchemy `@event.listens_for(engine, "connect")`. Per-engine timeouts preserved: API 30s, Worker 120s, Scheduler 15s, Alembic 0.

**Follow-up fix (Codex review):** The `SET` runs in autocommit context so pool `ROLLBACK` on check-in doesn't revert the timeout. Uses parameterized query (`%s`) instead of f-string.

### Key Files
```
backend/app/database/engines.py          # Post-connect SET statement_timeout
backend/alembic/env.py                   # Alembic migration timeout
backend/app/core/config_production.py    # Legacy options removed
```

---

## 🔍 Service URL Investigation — Silent Bug Discovery

### The Dead Feature

`preview_service_database_url` and `prod_service_database_url` were in local `.env`, pointing to `service_role:ServicePassword@pooler.supabase.com`. Investigation across two agents confirmed:

1. `service_role` is a **Supabase API-level concept** (JWT), not a PostgreSQL database role
2. The connection string was **completely invalid** — connecting with it returns "There is no user 'service_role' in the database"
3. The feature was added in October 2025 to "bypass RLS during seeding" but **never actually worked**
4. `prep_db.py` silently fell back to the regular `db_url` via config hierarchy (`PREVIEW_DATABASE_URL` wins over `DATABASE_URL` when `SITE_MODE=preview`)

### The Silent Failure

One code path did NOT fall back: `populate_region_embeddings()` at line 375 used `create_engine(target)` directly (bypassing config resolution). This connected with the invalid service_role URL, but an `except Exception` handler silently caught the failure and returned.

**Result:** Region name embeddings (used for NL search location resolution) were **never populated on either environment**. 262 regions, 0 embeddings — for months. Discovered by grepping the rebuild logs and confirmed via SQL query.

**Fix:** Removed the dead service URL entries from `.env`. With them gone, `seed_db_url` falls back to `db_url` (the postgres URL), and `populate_region_embeddings` connects successfully. Confirmed: 262/262 embeddings on both preview and prod after rebuild.

---

## 🛡️ Script Hardening — Track 2

### Tiered Hostname Safety

New shared helper `backend/app/utils/database_safety.py` with tiered enforcement:

| Target | Hosted DB detected | Behavior |
|--------|-------------------|----------|
| `int` | Yes | **Hard abort** — misconfiguration, cannot be bypassed |
| `preview` / `stg` | Yes | **Warning** displayed, `--force --yes` continues to work |
| `prod` | Yes | **Interactive hostname confirmation** — must type full hostname, no flag bypass |
| Any (in CI) | Non-INT | **Blocked entirely** |

### DatabaseConfig Integration

Both `reset_schema.py` and `prep_db.py` now resolve URLs through `DatabaseConfig.get_database_url()` instead of their own resolvers. Both scripts clear `DB_CONFIRM_BYPASS` before resolution so ambient env vars can't bypass safety gates.

### SITE_MODE=prod Bypass Fixed

`database_config.py` no longer skips confirmation just because `SITE_MODE=prod`. Now requires explicit `DB_CONFIRM_BYPASS=1` (set only in Render start commands for managed runtimes: backend, celery-worker, celery-beat, flower). Scripts explicitly clear this flag.

### Explicit URL Requirement (Codex P1 Fix)

Non-INT modes now require the mode-specific env var (`PREVIEW_DATABASE_URL`, `PROD_DATABASE_URL`, etc.). Generic `DATABASE_URL` is cleared to prevent silent fallback to a stale/wrong database.

### Dead Service-URL Code Removed
- `SERVICE_ENV_URL_VARS`, `resolve_service_db_url()`, `seed_db_url` from `prep_db.py`
- `preview_service_database_url_raw`, `prod_service_database_url_raw` from `config.py`
- Service URL override from `simulate_checkr_webhook.py`

### Key Files
```
backend/app/utils/database_safety.py     # NEW — shared helper
backend/app/core/database_config.py      # DB_CONFIRM_BYPASS, fixed prod bypass
backend/app/core/config.py               # Removed service URL config fields
backend/scripts/reset_schema.py          # Refactored to use DatabaseConfig
backend/scripts/prep_db.py              # Refactored, service URL code removed
backend/scripts/simulate_checkr_webhook.py  # Service URL override removed
backend/scripts/seed_chat_fixture.py     # Lazy imports to prevent import-time DB init
.github/workflows/db-smoke.yml          # DB_CONFIRM_BYPASS for CI boot check
```

---

## 📋 Backup Verification Hardening — Track 3

The backup verification workflow reported 100% success for 82 days while masking real failures.

### Fixes Applied
- **Table name bug:** `services` → `instructor_services` (the table that actually exists)
- **Container upgrade:** `pg14` → `postgis/postgis:17-3.5` + runtime pgvector install (matches pg17 dumps)
- **Error classification:** `|| true` masking replaced with stderr capture + fatal/warning pattern categorization
- **Backup freshness:** Fails if newest backup is >2 days old (parsed from filename)
- **Backup size:** Fails if decrypted dump is <1 MB (catches truncation)
- **Row-count validation:** Critical tables must have >0 rows (was print-only)
- **Table existence:** Missing critical tables now fail (was warn-only)

### Key Files
```
.github/workflows/backup-verification.yml
```

---

## 🏛️ Architecture Decisions (v145)

- **Dedicated PgBouncer over shared Supavisor** — eliminates circuit-breaker DoS vector. fail2ban blocks only offending IP, not all connections. $4/month IPv4 add-on per project is the cost.
- **Post-connect SET over startup options** — PgBouncer doesn't support PostgreSQL `options` parameter. `SET statement_timeout` via SQLAlchemy connect event is functionally equivalent and compatible with all connection types.
- **Autocommit for SET statement_timeout** — Execute in autocommit context so pool rollback on check-in doesn't revert the timeout setting.
- **DB_CONFIRM_BYPASS as explicit opt-in** — Only managed runtimes set it (via Render env group). Scripts clear it before resolution. Replaces implicit SITE_MODE=prod trust.
- **Tiered hostname safety** — int+hosted=abort (misconfiguration), preview/stg+hosted=warn (fast path preserved), prod+hosted=interactive (no bypass). CI always blocked for non-INT.
- **Explicit URL requirement for non-INT** — Generic DATABASE_URL fallback disabled for preview/prod/stg. Mode-specific env var must be set. Prevents silent wrong-database targeting.
- **Service-role URLs are dead code** — `service_role` is a Supabase API concept, not a DB user. The connection never worked. Removed entirely.

---

## 📊 Platform Health (Post-v145)

| Metric | Value | Change from v144 |
|--------|-------|-------------------|
| **Backend Tests** | 13,375+ | +79 |
| **Frontend Tests** | 8,321+ | Maintained |
| **Backend Coverage** | 98%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | Maintained |
| **PRs Merged** | 3 | PgBouncer fix + Script hardening + Backup verification |
| **Independent Audits** | 10+ | Across all tracks |
| **Region Embeddings** | 262/262 | Was: 0/262 (silent failure fixed) |
| **DB Password Strength** | 48-char random | Was: 23-char word-based |
| **Connection Pooler** | Dedicated PgBouncer | Was: Shared Supavisor |
| **Backup Verification** | Real validation | Was: Silent green (53 masked errors) |
| **Script Safety** | Tiered hostname + CI guard | Was: --force --yes could destroy prod |
| **Monthly Infra Cost** | ~$68/month | Was: $60 (+$8 for 2x IPv4 add-ons) |

---

## 📋 Remaining Work

### From This Session (carried forward)

| Item | Priority | Notes |
|------|----------|-------|
| Dedup shared constants between prep_db.py and reset_schema.py | Low | SITE_MODE_BY_ENV, enforce_ci_guard duplicated — move to database_safety.py |
| Custom pg17 CI image for backup verification | Low | Would eliminate runtime pgvector apt-get install |
| Backup pipeline failure notifications | Medium | Add Slack webhook or email on backup/verification failure |
| Network Restrictions (IP allowlisting) | Medium | Free, additional protection layer — allowlist Render + GitHub Actions + personal IP |

### From Previous Sessions (unchanged)

| Item | Priority | Notes |
|------|----------|-------|
| QA bugs (3 booking flow scenarios) | **High** | Failed booking emails, wrong next-available time, online lesson join button |
| Dashboard Beast 2.0 | **High** | Cancellation flow with policy, booking detail redesign for online lessons |
| Founding instructor activation | **High** | ~102 recruited, invite codes, onboarding |
| Day Zero database prep | **High** | Wipe mock data, seed real instructors, clean backup |
| `student_launch_enabled` flag | **High** | Currently `false` — students can't sign up |
| S5 login cold start 6.7s | Medium | Render min_instances +$15/mo |
| Tier 1-3 large file refactoring | Low | payment_tasks, notification_service, nl_search_service, etc. |
| TypeScript 6.0 upgrade | Low | Blocked on @typescript-eslint peer dep |
| PRD completion | Low | Parts 2, 3, 5, 6, 7, 8, 9 |

---

## 🔑 Git History (main, post-v145)

```
HEAD     fix(ops): harden backup verification workflow
         fix(database): harden destructive scripts and remove dead service-URL code
         fix(database): execute SET statement_timeout in autocommit context
         fix(database): replace startup options with post-connect SET statement_timeout (PR #369)
         [v144 commits below]
```

---

## 🔐 Infrastructure State (Post-v145)

### Database Connections

| Environment | Transaction Pooler (6543) | Session/Direct (5432) | Type |
|-------------|--------------------------|----------------------|------|
| Preview | `db.jyxeuwdbimvnxclkxcmt.supabase.co` | `db.jyxeuwdbimvnxclkxcmt.supabase.co` | Dedicated PgBouncer + Direct |
| Prod | `db.qwbzjvgaxykxuiynwbxp.supabase.co` | `db.qwbzjvgaxykxuiynwbxp.supabase.co` | Dedicated PgBouncer + Direct |

### GitHub Secrets Updated
- `PREVIEW_DATABASE_URL` — new password + dedicated pooler hostname
- `PROD_DATABASE_URL` — new password + dedicated pooler hostname
- `SUPABASE_BACKUP_PASSWORD` — new prod postgres password
- `SUPABASE_DB_HOST` — `db.PROJECT_REF.supabase.co` (was pooler.supabase.com)
- `SUPABASE_DB_USER` — `postgres` (was `postgres.PROJECT_REF`)

### Render Env Group
- `DB_CONFIRM_BYPASS=1` added (for backend, celery-worker, celery-beat, flower)
- Both `DATABASE_URL` variants updated per environment

### Supabase Add-ons
- IPv4 add-on enabled on both preview and prod ($4/month each)

### Local .env Changes
- `preview_database_url` — new password + dedicated pooler hostname
- `prod_database_url` — new password + dedicated pooler hostname
- `preview_service_database_url` — **DELETED** (dead code)
- `prod_service_database_url` — **DELETED** (dead code)

---

**STATUS: Production database fully hardened. Passwords rotated to 48-char random. Both environments on dedicated PgBouncer (circuit-breaker DoS eliminated). Destructive scripts require interactive hostname confirmation for prod. Backup verification actually verifies. Region embeddings fixed (was silently failing for months). 13,375+ backend tests passing. Critical path to launch: fix 3 QA bugs → activate founding instructors → Day Zero prep → flip student_launch_enabled → launch.**
