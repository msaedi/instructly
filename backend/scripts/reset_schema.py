# backend/scripts/reset_schema.py
"""
Reset database schema - DROPS ALL TABLES!

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

from app.core.database_config import DatabaseConfig
from app.utils.database_safety import check_hosted_database
from app.utils.env_logging import log_error, log_info, log_warn

ALLOWED_ENVS = {"int", "stg", "preview", "prod"}
SITE_MODE_BY_ENV = {
    "int": "int",
    "stg": "local",
    "preview": "preview",
    "prod": "prod",
}
ENV_URL_VARS = {
    "int": ("DATABASE_URL_INT", "TEST_DATABASE_URL", "test_database_url"),
    "stg": ("DATABASE_URL_STG", "STG_DATABASE_URL", "LOCAL_DATABASE_URL", "local_database_url", "stg_database_url"),
    "preview": ("DATABASE_URL_PREVIEW", "PREVIEW_DATABASE_URL", "preview_database_url"),
    "prod": ("DATABASE_URL_PROD", "PROD_DATABASE_URL", "PRODUCTION_DATABASE_URL", "prod_database_url"),
}
CANONICAL_DB_ENV_BY_MODE = {
    "int": "TEST_DATABASE_URL",
    "stg": "STG_DATABASE_URL",
    "preview": "PREVIEW_DATABASE_URL",
    "prod": "PROD_DATABASE_URL",
}
REQUIRED_DB_ENV_BY_MODE = {
    "stg": (("STG_DATABASE_URL", "LOCAL_DATABASE_URL"), "STG_DATABASE_URL or LOCAL_DATABASE_URL"),
    "preview": (("PREVIEW_DATABASE_URL",), "PREVIEW_DATABASE_URL"),
    "prod": (("PROD_DATABASE_URL",), "PROD_DATABASE_URL"),
}
USAGE = (
    "Usage: python scripts/reset_schema.py "
    "[int|stg|preview|prod] [--dry-run] [--force] [--yes]"
)


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
        if arg in {"--help", "-h"}:
            print(USAGE)
            sys.exit(0)
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--force":
            force = True
        elif arg == "--yes":
            assume_yes = True
        elif arg.startswith("--"):
            print(f"❌ Unknown option: {arg}")
            print(USAGE)
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
        print(USAGE)
        sys.exit(1)
    return env, dry_run, force, assume_yes


def is_ci_environment() -> bool:
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def _promote_database_url_aliases(env: str) -> None:
    canonical_var = CANONICAL_DB_ENV_BY_MODE[env]
    if env in {"preview", "prod"} and canonical_var in os.environ:
        return
    for key in ENV_URL_VARS.get(env, ()):
        value = os.getenv(key)
        if value:
            os.environ[canonical_var] = value
            return
        value = os.getenv(key.upper())
        if value:
            os.environ[canonical_var] = value
            return


def _require_explicit_database_url(env: str) -> None:
    if env == "int":
        return

    required_vars, display_name = REQUIRED_DB_ENV_BY_MODE[env]
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("database_url", None)

    if any((os.getenv(var) or "").strip() for var in required_vars):
        return

    sys.exit(
        f"ERROR: {display_name} is not set. Cannot target '{env}' without an explicit database URL. "
        "Generic DATABASE_URL fallback is not allowed for non-INT modes."
    )


def enforce_ci_guard(env: str, dry_run: bool) -> None:
    if is_ci_environment() and env != "int" and not dry_run:
        sys.exit("ERROR: Non-INT environment not allowed in CI. Aborting.")


def resolve_db_url(env: str, *, allow_prod_bypass: bool = False) -> str:
    os.environ.pop("DB_CONFIRM_BYPASS", None)
    if allow_prod_bypass and env == "prod":
        os.environ["DB_CONFIRM_BYPASS"] = "1"
    _promote_database_url_aliases(env)
    _require_explicit_database_url(env)
    os.environ["SITE_MODE"] = SITE_MODE_BY_ENV[env]
    try:
        return DatabaseConfig().get_database_url()
    finally:
        if allow_prod_bypass and env == "prod":
            os.environ.pop("DB_CONFIRM_BYPASS", None)


def main() -> None:
    env, dry_run, force, assume_yes = parse_args(sys.argv[1:])
    enforce_ci_guard(env, dry_run)
    ci_dry_run = is_ci_environment() and dry_run
    db_url = resolve_db_url(env, allow_prod_bypass=ci_dry_run)
    if not db_url:
        missing = {
            "stg": "stg_database_url",
            "preview": "preview_database_url",
            "prod": "prod_database_url",
        }.get(env, "database_url")
        log_error(env, f"Missing database URL for env '{env}'. Set {missing} in your environment or settings.")
        sys.exit(3)

    if not (ci_dry_run and env == "prod"):
        check_hosted_database(env, db_url)

    print("\n" + "=" * 60)
    print("⚠️  SCHEMA RESET - This will DROP ALL TABLES!")
    print("=" * 60)
    log_info(env, "Environment confirmed")
    log_info(env, f"Target database: {mask_url(db_url)}")

    if dry_run:
        log_info(env, "Dry run complete; no changes made.")
        sys.exit(0)

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


if __name__ == "__main__":
    main()
