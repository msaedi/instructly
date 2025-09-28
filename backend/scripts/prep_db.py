#!/usr/bin/env python3
"""
prep_db.py — environment-aware database prep for Instainstru.

Supports SITE_MODE resolution via positional arg, env var, or legacy flags.
Modes: prod | preview | stg | int
"""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap
from typing import Optional, Tuple

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Load backend/.env so lowercase keys are available when running directly
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

# Import settings after dotenv so local overrides take effect
from app.core.config import settings

# ---------- tiny log helpers ----------


def warn(msg: str):
    print(f"[WARN] {msg}", file=sys.stderr)


def info(tag: str, msg: str):
    print(f"[{tag.upper()}] {msg}")


def fail(msg: str, code: int = 1):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- env resolution ----------

ALIASES = {
    "prod": {"prod", "production", "live"},
    "preview": {"preview", "pre"},
    "stg": {"stg", "stage", "staging", "local"},
    "int": {"int", "test", "ci"},
}


def _norm_mode(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip().lower()
    for canon, names in ALIASES.items():
        if s in names:
            return canon
    return None


def detect_site_mode(positional: Optional[str], explicit: Optional[str]) -> Tuple[str, bool]:
    """Return (mode, legacy_used). Priority: --env > positional > SITE_MODE > legacy > default(int)."""
    flag_mode = _norm_mode(explicit)
    if explicit:
        if not flag_mode:
            fail(f"Unknown env alias from --env: {explicit}")
        return flag_mode, False

    # positional
    m = _norm_mode(positional)
    if m:
        return m, False

    # env
    env_mode = _norm_mode(os.getenv("SITE_MODE"))
    if env_mode:
        return env_mode, False

    # legacy
    # default
    return "int", False


ENV_URL_VARS = {
    "int": ("DATABASE_URL_INT", "TEST_DATABASE_URL", "test_database_url"),
    "stg": ("DATABASE_URL_STG", "STG_DATABASE_URL", "LOCAL_DATABASE_URL", "local_database_url", "stg_database_url"),
    "preview": ("DATABASE_URL_PREVIEW", "PREVIEW_DATABASE_URL", "preview_database_url"),
    "prod": ("DATABASE_URL_PROD", "PROD_DATABASE_URL", "PRODUCTION_DATABASE_URL", "prod_database_url"),
}


def resolve_db_url(mode: str) -> str:
    """Resolve DB URL using env overrides first, then settings fields."""
    for key in ENV_URL_VARS.get(mode, ()):  # try lowercase/uppercase variants
        value = os.getenv(key)
        if value:
            return value
        value = os.getenv(key.upper())
        if value:
            return value

    if mode == "prod":
        return settings.prod_database_url_raw or ""
    if mode == "preview":
        return settings.preview_database_url_raw or ""
    if mode == "stg":
        return settings.stg_database_url or settings.prod_database_url_raw or ""
    # int/default
    return settings.test_database_url


# ---------- ops ----------


def redact(url: str) -> str:
    try:
        if "://" in url and "@" in url:
            scheme, rest = url.split("://", 1)
            creds, host = rest.split("@", 1)
            return f"{scheme}://***:***@{host}"
    except Exception:
        pass
    return url


def run_migrations(db_url: str, dry_run: bool, tool_cmd: Optional[str]):
    if dry_run:
        info("dry", f"(dry-run) Would run migrations on {redact(db_url)}")
        return
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    cmd = tool_cmd or "alembic upgrade head"
    info("sys", f"Running migrations: {cmd}")
    subprocess.check_call(shlex.split(cmd), cwd=str(BACKEND_DIR), env=env)


def _mode_env(mode: str) -> dict:
    # Only SITE_MODE is authoritative now
    site_mode = "local" if mode == "stg" else mode
    return {"SITE_MODE": site_mode}


def seed_system_data(db_url: str, dry_run: bool, mode: str):
    if dry_run:
        info("dry", f"(dry-run) Would seed SYSTEM data on {redact(db_url)}")
        return
    info("seed", "Seeding SYSTEM data…")
    # Roles/permissions and catalog + regions
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": db_url}
    subprocess.check_call([sys.executable, "scripts/seed_data.py", "--system-only"], cwd=str(BACKEND_DIR), env=env)


def seed_mock_users(db_url: str, dry_run: bool, mode: str):
    if dry_run:
        info("dry", f"(dry-run) Would seed MOCK users on {redact(db_url)}")
        return
    info("seed", "Seeding MOCK users/instructors/bookings…")
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": db_url}
    subprocess.check_call(
        [sys.executable, "scripts/seed_data.py", "--include-mock-users"], cwd=str(BACKEND_DIR), env=env
    )


def verify_env_marker(db_url: str, expected_mode: str) -> bool:
    """
    Optional sanity check. If a 'settings' table with key='env_name' exists, verify it.
    Return True if OK or unknown; False if mismatch.
    """
    try:
        import psycopg2  # type: ignore
    except Exception:
        warn("psycopg2 not available; skipping --verify-env check.")
        return True
    try:
        conn = psycopg2.connect(db_url)
        with conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key='env_name'")
            row = cur.fetchone()
            if not row:
                warn("settings.env_name not found; skipping strict verify.")
                return True
            value = (row[0] or "").strip().lower()
            if value not in ALIASES.get(expected_mode, {expected_mode}):
                warn(f"DB env_name='{value}' != expected '{expected_mode}'")
                return False
            return True
    except Exception as e:
        warn(f"--verify-env check skipped ({e})")
        return True


# ---------- post-seed operations ----------


def generate_embeddings(db_url: str, dry_run: bool, mode: str) -> None:
    if dry_run:
        info("dry", f"(dry-run) Would generate embeddings on {redact(db_url)}")
        return
    info("ops", "Generating service embeddings…")
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": db_url}
    subprocess.check_call([sys.executable, "scripts/generate_service_embeddings.py"], cwd=str(BACKEND_DIR), env=env)


def calculate_analytics(db_url: str, dry_run: bool, mode: str) -> None:
    if dry_run:
        info("dry", f"(dry-run) Would calculate service analytics on {redact(db_url)}")
        return
    info("ops", "Calculating service analytics…")
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": db_url}
    subprocess.check_call([sys.executable, "scripts/calculate_service_analytics.py"], cwd=str(BACKEND_DIR), env=env)


def _trigger_render_one_off_job(command: str) -> bool:
    try:
        import requests  # type: ignore
    except Exception:
        warn("requests not available; cannot trigger Render job for cache clear")
        return False

    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        warn("RENDER_API_KEY not set; skipping Render cache clear")
        return False

    service_id = os.getenv("RENDER_BACKEND_SERVICE_ID")
    service_name = os.getenv("RENDER_BACKEND_SERVICE_NAME")
    try:
        if not service_id:
            resp = requests.get(
                "https://api.render.com/v1/services?limit=100",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            services = resp.json()
            candidate_names = [
                n for n in [service_name, "instainstru-backend", "instructly-backend", "instainstru-celery"] if n
            ]
            for svc in services:
                name = (
                    (svc.get("service") or {}).get("name")
                    if isinstance(svc, dict) and "service" in svc
                    else svc.get("name")
                )
                sid = (
                    (svc.get("service") or {}).get("id")
                    if isinstance(svc, dict) and "service" in svc
                    else svc.get("id")
                )
                if name in candidate_names and sid:
                    service_id = sid
                    break
        if not service_id:
            warn("Could not resolve Render backend service id; skipping cache clear")
            return False

        job_resp = requests.post(
            f"https://api.render.com/v1/services/{service_id}/jobs",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"startCommand": command},
            timeout=15,
        )
        if job_resp.status_code not in (200, 201):
            warn(f"Failed to start Render job [{job_resp.status_code}]")
            return False
        return True
    except Exception as e:
        warn(f"Render job error: {e}")
        return False


def clear_cache(mode: str, dry_run: bool) -> None:
    if dry_run:
        info("dry", f"(dry-run) Would clear cache for mode={mode}")
        return
    if mode == "int":
        info("cache", "Skipping cache clear for INT")
        return
    if mode in ("stg", "preview"):
        info("cache", "Clearing cache locally via script…")
        try:
            subprocess.check_call([sys.executable, "scripts/clear_cache.py", "--scope", "all"], cwd=str(BACKEND_DIR))
        except FileNotFoundError:
            warn("clear_cache.py not found; skipping cache clear")
        return
    if mode == "prod":
        info("cache", "Triggering Render one-off job to clear cache…")
        ok = _trigger_render_one_off_job('bash -lc "python backend/scripts/clear_cache.py --scope all"')
        if not ok:
            warn("Render cache clear could not be started; cache will expire naturally")
        return


# ---------- main ----------


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Prepare database by environment.",
        epilog=textwrap.dedent(
            """
Examples:
  python scripts/prep_db.py                # default → int
  python scripts/prep_db.py stg
  python scripts/prep_db.py preview
  python scripts/prep_db.py prod

  SITE_MODE=preview python scripts/prep_db.py --migrate --seed-all
  SITE_MODE=prod    python scripts/prep_db.py --migrate --seed-all --force --yes

  # Seed with additional mock data windows (overrides config defaults)
  python backend/scripts/prep_db.py int --seed-all --set availability_weeks_future=6 --set availability_weeks_past=2
  python backend/scripts/prep_db.py stg --seed-all --set booking_days_future=10 --set booking_days_past=30
"""
        ),
    )
    parser.add_argument("env", nargs="?", help="env alias: int|stg|preview|prod")
    parser.add_argument("--env", dest="env_flag", help="explicit env alias (same choices as positional)")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--seed-all", action="store_true")
    parser.add_argument("--seed-system-only", action="store_true")
    parser.add_argument("--seed-mock-users", action="store_true")
    parser.add_argument("--dry-run", "--noop", dest="dry_run", action="store_true")
    parser.add_argument("--migrate-tool", type=str, default=None)
    parser.add_argument("--force", action="store_true", help="required for any writes in prod")
    parser.add_argument("--yes", action="store_true", help="non-interactive confirmation for prod")
    parser.add_argument("--verify-env", action="store_true", help="sanity-check DB env marker")
    args = parser.parse_args()

    mode, legacy = detect_site_mode(args.env, args.env_flag)
    if legacy:
        warn(
            "Legacy flags (USE_*_DATABASE) are deprecated. Use SITE_MODE or positional env. This mapping will be removed."
        )

    db_url = resolve_db_url(mode)
    if not db_url:
        missing = {
            "stg": "stg_database_url",
            "preview": "preview_database_url",
            "prod": "prod_database_url",
        }.get(mode, "test_database_url")
        fail(f"Missing database URL for mode '{mode}'. Set {missing} or export an override.")

    os.environ["DATABASE_URL"] = db_url
    site_mode_env = "local" if mode == "stg" else mode
    os.environ["SITE_MODE"] = site_mode_env
    if mode == "int":
        os.environ["TEST_DATABASE_URL"] = db_url
    elif mode == "stg":
        os.environ["STG_DATABASE_URL"] = db_url
        os.environ["LOCAL_DATABASE_URL"] = db_url
    elif mode == "preview":
        os.environ["PREVIEW_DATABASE_URL"] = db_url
    else:
        os.environ["PROD_DATABASE_URL"] = db_url

    info("db", f"Using URL for migrations & seed: {redact(db_url)}")

    seed_mode = (
        "system+mock"
        if args.seed_all
        else "system_only" if args.seed_system_only else "mock_only" if args.seed_mock_users else "none"
    )

    info(
        "mode",
        f"MODE={mode} db={redact(db_url)} migrate={'Y' if args.migrate else 'N'} "
        f"seed={seed_mode} dry_run={'Y' if args.dry_run else 'N'} verify_env={'Y' if args.verify_env else 'N'}",
    )

    # verify env marker (optional)
    if args.verify_env:
        ok = verify_env_marker(db_url, mode)
        if not ok and not args.force:
            info("guard", "Env marker mismatch; re-run with --force to override.")
            sys.exit(0)

    # prod safety
    if mode == "prod":
        if args.seed_mock_users or args.seed_all:
            warn("Prod mode: mock user seeding is not allowed. Forcing system-only.")
            args.seed_system_only = True
            args.seed_mock_users = False
            args.seed_all = False
        if not args.dry_run and (args.migrate or args.seed_system_only):
            if not (args.force and args.yes):
                fail("Prod writes require BOTH --force and --yes.")
        # optional interactive confirmation (only when writing)
        if not args.yes and not args.dry_run and (args.migrate or args.seed_system_only) and not os.getenv("CI"):
            resp = input("You are about to modify PRODUCTION. Type 'yes' to continue: ").strip().lower()
            if resp != "yes":
                info("prod", "Operation cancelled.")
                sys.exit(0)

    # do work
    try:
        if args.migrate:
            run_migrations(db_url, args.dry_run, args.migrate_tool)
        if args.seed_system_only:
            seed_system_data(db_url, args.dry_run, mode)
        if args.seed_mock_users:
            if mode == "prod":
                fail("Cannot seed mock users in prod!")
            seed_mock_users(db_url, args.dry_run, mode)
        if args.seed_all:
            # only non-prod paths fall here; seed_mock_users triggers system seeding internally
            seed_mock_users(db_url, args.dry_run, mode)

        # Post-seed ops (always run after any seeding or migration when not dry-run)
        if args.migrate or args.seed_all or args.seed_system_only or args.seed_mock_users:
            generate_embeddings(db_url, args.dry_run, mode)
            calculate_analytics(db_url, args.dry_run, mode)
            clear_cache(mode, args.dry_run)
        info(mode, "Complete!")
    except subprocess.CalledProcessError as e:
        fail(f"External command failed with exit code {e.returncode}")
    except KeyboardInterrupt:
        fail("Interrupted by user", code=130)


if __name__ == "__main__":
    main()
