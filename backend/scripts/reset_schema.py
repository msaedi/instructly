# backend/scripts/reset_schema.py
"""
Reset database schema - DROPS ALL TABLES!

Database safety: This script now uses safe database selection
Default: INT database
Use USE_STG_DATABASE=true or USE_PROD_DATABASE=true for other databases

Usage:
    python scripts/reset_schema.py       # Default: INT database
    python scripts/reset_schema.py int   # Explicit INT
    python scripts/reset_schema.py stg   # Staging database
    python scripts/reset_schema.py prod  # Production (requires confirmation)
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.utils.env_logging import log_error, log_info, log_warn

ALLOWED_ENVS = {"int", "stg", "preview", "prod"}


def mask_url(url: str) -> str:
    try:
        scheme, rest = url.split("://", 1)
    except ValueError:
        return url
    if "@" not in rest:
        return url
    creds, remainder = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{remainder}"


def parse_args(argv):
    env = None
    dry_run = False
    force = False
    assume_yes = False
    for arg in argv:
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--force":
            force = True
        elif arg == "--yes":
            assume_yes = True
        elif arg.startswith("--"):
            print(f"❌ Unknown option: {arg}")
            print("Usage: python scripts/reset_schema.py [int|stg|preview|prod] [--dry-run] [--force] [--yes]")
            sys.exit(1)
        elif env is None:
            env = arg.lower()
        else:
            print(f"❌ Unexpected extra argument: {arg}")
            sys.exit(1)
    if env is None:
        env = "int"
    elif env not in ALLOWED_ENVS:
        print(f"❌ Unknown target: {env}")
        print("Usage: python scripts/reset_schema.py [int|stg|preview|prod] [--dry-run] [--force] [--yes]")
        sys.exit(1)
    return env, dry_run, force, assume_yes


def resolve_db_url(env: str) -> str:
    if env == "int":
        return settings.database_url
    if env == "stg":
        return settings.stg_database_url_raw or ""
    if env == "preview":
        return settings.preview_database_url_raw or ""
    return settings.prod_database_url_raw or ""


from app.core.config import settings

env, dry_run, force, assume_yes = parse_args(sys.argv[1:])
db_url = resolve_db_url(env)
if not db_url:
    missing = {
        "stg": "stg_database_url",
        "preview": "preview_database_url",
        "prod": "prod_database_url",
    }.get(env, "database_url")
    log_error(env, f"Missing database URL for env '{env}'. Set {missing} in your environment or settings.")
    sys.exit(3)

print("\n" + "=" * 60)
print("⚠️  SCHEMA RESET - This will DROP ALL TABLES!")
print("=" * 60)
log_info(env, "Environment confirmed")
log_info(env, f"Target database: {mask_url(db_url)}")

if env != "int":
    if not force:
        log_error(env, f"Refusing to drop '{env}' without --force.")
        sys.exit(2)
    if not assume_yes:
        if not sys.stdin.isatty():
            log_error(env, "Non-interactive drops require --yes.")
            sys.exit(2)
        confirmation = input(f"Type '{env}' to confirm: ").strip().lower()
        if confirmation != env:
            log_warn(env, "Operation cancelled before drop.")
            sys.exit(2)

if dry_run:
    log_info(env, "Dry run complete; no changes made.")
    sys.exit(0)

engine = create_engine(db_url)
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    # Disable statement timeout for this session - DROP CASCADE can take a while
    log_info(env, "Disabling statement timeout for this session...")
    conn.execute(text("SET statement_timeout = 0"))

    # Terminate other connections to the database (except ourselves)
    # This helps avoid lock contention during DROP
    log_info(env, "Terminating other connections to avoid locks...")
    conn.execute(
        text("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND state != 'idle'
    """)
    )

    log_info(env, "Dropping schema (this may take a moment)...")
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))

    # Grant default permissions on the new schema
    conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

log_info(env, "Schema reset complete!")
