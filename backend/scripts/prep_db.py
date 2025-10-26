#!/usr/bin/env python3
"""
prep_db.py — environment-aware database prep for Instainstru.

Supports SITE_MODE resolution via positional arg, env var, or legacy flags.
Modes: prod | preview | stg | int
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap
from typing import Optional, Tuple
import urllib.request

import click

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Load backend/.env so lowercase keys are available when running directly
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.render", override=False)
except Exception:
    pass

# Import settings after dotenv so local overrides take effect
from app.core.config import settings
from app.utils.env_logging import (
    log_info as color_log_info,
    log_warn as color_log_warn,
)

# ---------- tiny log helpers ----------


_ENV_TAGS = {"INT", "STG", "PREVIEW", "PROD"}


def warn(msg: str):
    click.echo(f"{click.style('[WARN]', fg='yellow')} {msg}", err=True)


def info(tag: str, msg: str):
    upper = tag.upper()
    if upper in _ENV_TAGS:
        color_log_info(upper.lower(), msg)
    else:
        click.echo(f"[{upper}] {msg}")


def fail(msg: str, code: int = 1):
    click.echo(f"{click.style('[ERROR]', fg='red')} {msg}", err=True)
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

SERVICE_ENV_URL_VARS = {
    "preview": ("PREVIEW_SERVICE_DATABASE_URL", "preview_service_database_url"),
    "prod": ("PROD_SERVICE_DATABASE_URL", "prod_service_database_url"),
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


def resolve_service_db_url(mode: str) -> str:
    for key in SERVICE_ENV_URL_VARS.get(mode, ()):  # try lowercase/uppercase variants
        value = os.getenv(key)
        if value:
            return value
        value = os.getenv(key.upper())
        if value:
            return value

    if mode == "prod":
        return settings.prod_service_database_url_raw or ""
    if mode == "preview":
        return settings.preview_service_database_url_raw or ""
    return ""


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


def seed_system_data(db_url: str, dry_run: bool, mode: str, seed_db_url: Optional[str] = None):
    if dry_run:
        info("dry", f"(dry-run) Would seed SYSTEM data on {redact(db_url)}")
        info(
            "dry",
            "(dry-run) Would upsert 10 badge definitions: "
            "welcome_aboard, foundation_builder, first_steps, dedicated_learner, momentum_starter, "
            "consistent_learner, top_student, explorer, favorite_partnership, year_one_learner",
        )
        return
    info("seed", "Seeding SYSTEM data…")
    # Roles/permissions and catalog + regions
    target = seed_db_url or db_url
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": target}
    subprocess.check_call([sys.executable, "scripts/seed_data.py", "--system-only"], cwd=str(BACKEND_DIR), env=env)


def seed_mock_users(db_url: str, dry_run: bool, mode: str, seed_db_url: Optional[str] = None):
    if dry_run:
        info("dry", f"(dry-run) Would seed MOCK users on {redact(db_url)}")
        return
    info("seed", "Seeding MOCK users/instructors/bookings…")
    target = seed_db_url or db_url
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": target}
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


def _render_api_request(url: str, api_key: str, method: str = "GET", data: Optional[dict] = None) -> Optional[dict]:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
        req.data = payload
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset)
            if body:
                return json.loads(body)
            return {}
    except Exception as exc:
        warn(f"Render API request failed ({exc})")
        return None


def _render_list_services(api_key: str) -> list[dict]:
    data = _render_api_request("https://api.render.com/v1/services?limit=100", api_key, method="GET")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "services" in data and isinstance(data["services"], list):
        return data["services"]
    return []


def _render_get_service_id_by_name(api_key: str, service_name: str) -> Optional[str]:
    services = _render_list_services(api_key)
    for svc in services:
        if not isinstance(svc, dict):
            continue
        nested = svc.get("service") if isinstance(svc.get("service"), dict) else None
        flat_name = svc.get("name")
        flat_id = svc.get("id")
        nested_name = nested.get("name") if nested else None
        nested_id = nested.get("id") if nested else None
        if service_name in {flat_name, nested_name}:
            return nested_id or flat_id
    return None


def _render_post_job(api_key: str, service_id: str, command: str) -> bool:
    url = f"https://api.render.com/v1/services/{service_id}/jobs"
    payload = {"startCommand": command}
    resp = _render_api_request(url, api_key, method="POST", data=payload)
    if resp is None:
        warn("Failed to start Render job (no response)")
        return False
    return True


def _render_redeploy_service(api_key: str, service_id: str) -> bool:
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    payload = {"clearCache": "do_not_clear"}
    resp = _render_api_request(url, api_key, method="POST", data=payload)
    if resp is None:
        warn("Failed to trigger Render deploy")
        return False
    return True


def clear_cache(mode: str, dry_run: bool) -> None:
    if mode == "int":
        info("CACHE", "Skipping cache clear for INT")
        return
    if mode == "stg":
        if dry_run:
            info("DRY", "(dry-run) Would run local cache clear script for STG")
            return
        info("CACHE", "Clearing cache locally via script…")
        try:
            result = subprocess.run(
                [sys.executable, "scripts/clear_cache.py", "--scope", "all", "--echo-sentinel"],
                cwd=str(BACKEND_DIR),
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout or ""
            if "CACHE_CLEAR_OK" in output:
                color_log_info("stg", "Local cache cleared successfully")
            else:
                color_log_warn("stg", "Local cache script completed without sentinel acknowledgment")
        except FileNotFoundError:
            color_log_warn("stg", "clear_cache.py not found; skipping cache clear")
        except subprocess.CalledProcessError as exc:
            color_log_warn("stg", f"Local cache clear failed: {exc.stderr or exc.stdout or exc}")
        return

    if mode not in {"preview", "prod"}:
        warn(f"Unknown cache clear mode '{mode}'")
        return

    backend_service = "instainstru-api-preview" if mode == "preview" else "instainstru-api"
    redis_service = "redis-preview" if mode == "preview" else "redis"
    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        color_log_warn(mode, "RENDER_API_KEY not set; skipping Render cache clear")
        return

    if dry_run:
        info("DRY", f"(dry-run) Would trigger Render job on {backend_service}")
        info("DRY", f"(dry-run) Would redeploy Render service {redis_service}")
        return

    backend_id = _render_get_service_id_by_name(api_key, backend_service)
    if backend_id:
        ok = _render_post_job(api_key, backend_id, 'bash -lc "python backend/scripts/clear_cache.py --scope all"')
        if not ok:
            color_log_warn(mode, f"Failed to start cache-clear job for {backend_service}")
    else:
        color_log_warn(mode, f"Could not find Render service '{backend_service}'")

    redis_id = _render_get_service_id_by_name(api_key, redis_service)
    if redis_id:
        ok = _render_redeploy_service(api_key, redis_id)
        if not ok:
            color_log_warn(mode, f"Failed to redeploy Render service '{redis_service}'")
    else:
        color_log_warn(mode, f"Could not find Render service '{redis_service}'")


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
    parser.add_argument(
        "--seed-all-prod",
        action="store_true",
        help="Allow mock/demo data seeding in prod (requires --force and --yes)",
    )
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
    service_db_url = resolve_service_db_url(mode)
    seed_db_url = service_db_url or db_url
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

    info("db", f"Using URL for migrations: {redact(db_url)}")
    if seed_db_url != db_url:
        info("db", f"Using seed connection override: {redact(seed_db_url)}")

    # verify env marker (optional)
    if args.verify_env:
        ok = verify_env_marker(db_url, mode)
        if not ok and not args.force:
            info("guard", "Env marker mismatch; re-run with --force to override.")
            sys.exit(0)

    # prod safety
    if mode == "prod":
        if args.seed_all_prod:
            if not (args.force and args.yes):
                fail("Prod mock seeding requires --force and --yes.")
            args.seed_all = True
            args.seed_mock_users = True
            args.seed_system_only = True
        elif args.seed_mock_users or args.seed_all:
            warn("Prod mode: mock user seeding is not allowed. Forcing system-only.")
            args.seed_system_only = True
            args.seed_mock_users = False
            args.seed_all = False
        if not args.dry_run and (args.migrate or args.seed_system_only or args.seed_all_prod):
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

        perform_system_seed = args.seed_system_only or args.seed_all or args.seed_mock_users
        perform_mock_seed = args.seed_mock_users or args.seed_all

        if perform_system_seed:
            seed_system_data(db_url, args.dry_run, mode, seed_db_url=seed_db_url)
        if perform_mock_seed:
            seed_mock_users(db_url, args.dry_run, mode, seed_db_url=seed_db_url)

        if (
            not args.dry_run
            and mode == "prod"
            and args.seed_all_prod
            and perform_mock_seed
        ):
            from importlib import import_module

            db_module = import_module("app.database")
            seed_module = import_module("scripts.seed_data")

            with db_module.SessionLocal() as session:
                created, existing = seed_module.seed_beta_access_for_instructors(session)
            info(
                mode,
                f"Ensured beta access for instructors (created={created}, existing={existing})",
            )

        # Post-seed ops (always run after any seeding or migration when not dry-run)
        if args.migrate or perform_system_seed or perform_mock_seed:
            generate_embeddings(db_url, args.dry_run, mode)
            calculate_analytics(db_url, args.dry_run, mode)
            clear_cache(mode, args.dry_run)
        info(mode, "Complete!")
    except subprocess.CalledProcessError as e:
        if mode in {"prod", "preview"} and not service_db_url:
            warn("Command failed; consider setting a service-role DSN (e.g., PROD_SERVICE_DATABASE_URL) for seeding.")
        fail(f"External command failed with exit code {e.returncode}")
    except KeyboardInterrupt:
        fail("Interrupted by user", code=130)


if __name__ == "__main__":
    main()
