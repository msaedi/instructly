#!/usr/bin/env python
"""
Simplified database preparation script.

Usage:
    python scripts/prep_db.py           # Default: prep INT database
    python scripts/prep_db.py int       # Prep INT database
    python scripts/prep_db.py stg       # Prep STG database
    python scripts/prep_db.py prod      # Prep PROD database (requires confirmation)

This script:
1. Creates the database if it doesn't exist (for INT/STG only)
2. Runs migrations (alembic downgrade base + upgrade head)
3. Seeds with YAML data
4. Generates service embeddings
5. Calculates service analytics
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

# Add backend to path to import settings
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings

# Color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
NC = "\033[0m"
BOLD = "\033[1m"


def parse_database_url(url):
    """Parse a database URL to extract connection parameters."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
    }


# Database configurations from settings - using raw fields for direct access
DB_CONFIG = {
    "int": {
        "url": settings.int_database_url_raw,
        "color": GREEN,
        "label": "INT",
        "description": "Integration Test Database",
    },
    "stg": {
        "url": settings.stg_database_url_raw if settings.stg_database_url_raw else settings.prod_database_url_raw,
        "color": YELLOW,
        "label": "STG",
        "description": "Staging/Local Development Database",
    },
    "prod": {
        "url": settings.prod_database_url_raw,
        "color": RED,
        "label": "PROD",
        "description": "Production Database",
    },
}

# Get backend directory
backend_dir = Path(__file__).parent.parent


def print_header(db_type):
    """Print colored header for database type."""
    config = DB_CONFIG[db_type]
    print(f"\n{'='*60}")
    print(f"{config['color']}{BOLD}[{config['label']}]{NC} {config['description']}")
    print(f"{'='*60}\n")


def create_local_database(db_url):
    """Create a local database if it doesn't exist."""
    db_params = parse_database_url(db_url)
    db_name = db_params["database"]

    try:
        # Connect to PostgreSQL default database
        # Try 'postgres' first, then fallback to 'template1' if it doesn't exist
        for default_db in ["postgres", "template1"]:
            try:
                conn = psycopg2.connect(
                    host=db_params["host"],
                    port=db_params["port"],
                    user=db_params["user"],
                    password=db_params["password"],
                    database=default_db,
                )
                break
            except psycopg2.OperationalError as e:
                if "database" in str(e) and "does not exist" in str(e) and default_db == "postgres":
                    continue  # Try template1
                else:
                    raise
        conn.autocommit = True
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()

        if not exists:
            # Create database
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"{GREEN}✓{NC} Created database: {db_name}")
        else:
            print(f"ℹ️  Database '{db_name}' already exists")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"{RED}✗{NC} Failed to create database: {e}")
        return False


def run_command(cmd, description, cwd=None):
    """Run a command and show progress."""
    print(f"\n▶ {description}...")

    try:
        # Use subprocess.call for real-time output
        returncode = subprocess.call(cmd, cwd=cwd or backend_dir)

        if returncode == 0:
            print(f"{GREEN}✓{NC} {description} completed")
            return True
        else:
            print(f"{RED}✗{NC} {description} failed")
            return False

    except Exception as e:
        print(f"{RED}✗{NC} Error: {e}")
        return False


def _trigger_render_one_off_job(command: str) -> bool:
    """Trigger a Render one-off job on the backend service to run a command.

    Requires env var RENDER_API_KEY and either RENDER_BACKEND_SERVICE_ID or a
    service name via RENDER_BACKEND_SERVICE_NAME (defaults to 'instainstru-backend').
    """
    import requests

    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        # Try loading backend/.env.render
        env_render_path = Path(backend_dir) / ".env.render"
        if env_render_path.exists():
            try:
                for line in env_render_path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
                api_key = os.getenv("RENDER_API_KEY")
            except Exception:
                pass
    if not api_key:
        print("  ⚠ RENDER_API_KEY not set; cannot trigger Render job")
        return False

    service_id = os.getenv("RENDER_BACKEND_SERVICE_ID")
    # Primary preferred name via env; otherwise we'll try common candidates
    service_name = os.getenv("RENDER_BACKEND_SERVICE_NAME")

    try:
        if not service_id:
            # Lookup service ID by name
            resp = requests.get(
                "https://api.render.com/v1/services?limit=100",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            services = resp.json()
            # Accept either a configured name or common candidates
            candidate_names = [
                name
                for name in [
                    service_name,
                    "instainstru-backend",
                    "instructly",
                    "instructly-backend",
                    "instainstru-celery",
                ]
                if name
            ]
            for svc in services:
                # Render returns a flat object list; handle potential nested structure defensively
                candidate_name = (
                    (svc.get("service") or {}).get("name")
                    if isinstance(svc, dict) and "service" in svc
                    else svc.get("name")
                )
                candidate_id = (
                    (svc.get("service") or {}).get("id")
                    if isinstance(svc, dict) and "service" in svc
                    else svc.get("id")
                )
                if candidate_name in candidate_names and candidate_id:
                    service_id = candidate_id
                    break

        if not service_id:
            looked_for = service_name or "(common candidates)"
            print(f"  ⚠ Could not find Render service ID for '{looked_for}'")
            return False

        # Start the one-off job
        job_resp = requests.post(
            f"https://api.render.com/v1/services/{service_id}/jobs",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"startCommand": command},
            timeout=15,
        )
        if job_resp.status_code not in (200, 201):
            print(f"  ⚠ Failed to start Render job [{job_resp.status_code}]")
            try:
                print(f"    Response: {job_resp.text[:300]}")
            except Exception:
                pass
            return False

        job_id = job_resp.json().get("id") or job_resp.json().get("job", {}).get("id")
        if job_id:
            print(f"  ✓ Started Render job {job_id} to clear cache")
        else:
            print("  ✓ Started Render cache clear job")
        return True
    except Exception as e:
        print(f"  ⚠ Exception starting Render job: {e}")
        return False


def clear_cache(db_type):
    """Clear cache after database operations."""
    if db_type == "int":
        print(f"\n▶ Skipping cache clear for INT database (testing use only)")
        return True

    print(f"\n▶ Clearing cache for {db_type.upper()} database...")

    try:
        if db_type == "prod":
            # Trigger a one-off job on Render to clear cache in production
            # Use the container's Python via a shell, not the local sys.executable path
            command = 'bash -lc "python backend/scripts/clear_cache.py --scope all"'
            ok = _trigger_render_one_off_job(command)
            if not ok:
                print("  ⚠ Could not trigger Render job; cache may remain warm until TTL")
        elif db_type == "stg":
            # For staging, run against local Docker Redis directly
            print("  Clearing cache locally via script...")
            result = subprocess.call([sys.executable, "scripts/clear_cache.py", "--scope", "all"], cwd=backend_dir)
            if result != 0:
                print(f"  ⚠ Cache clear script exited with code {result}")
        else:
            # INT: no Redis per env description; skip
            print("  Skipping cache clear (INT has no Redis)")

        print(f"{GREEN}✓{NC} Cache clearing initiated/completed")
        return True

    except Exception as e:
        print(f"{RED}✗{NC} Cache clearing failed: {e}")
        print(f"  💡 Database operations completed successfully - cache will expire naturally")
        return True  # Don't fail the entire process for cache issues


def prep_database(db_type):
    """Prepare a specific database."""
    config = DB_CONFIG[db_type]

    # Set environment variables
    if db_type == "int":
        os.environ.pop("USE_STG_DATABASE", None)
        os.environ.pop("USE_PROD_DATABASE", None)
    elif db_type == "stg":
        os.environ["USE_STG_DATABASE"] = "true"
        os.environ.pop("USE_PROD_DATABASE", None)
    elif db_type == "prod":
        os.environ["USE_PROD_DATABASE"] = "true"
        os.environ.pop("USE_STG_DATABASE", None)

        # Require confirmation for production
        db_params = parse_database_url(config["url"])
        print(f"\n{RED}{BOLD}⚠️  WARNING: This will modify PRODUCTION data!{NC}")
        print(f"{RED}Database: {db_params['host']}{NC}")
        print(f"{RED}Only proceed if you absolutely know what you're doing.{NC}")
        confirmation = input(f"\nType 'yes' to confirm: ")
        if confirmation.lower() != "yes":
            print("Operation cancelled.")
            return False

    print_header(db_type)

    # Step 1: Create database (only for local databases)
    db_params = parse_database_url(config["url"])
    is_local = db_params["host"] in ["localhost", "127.0.0.1"]

    if is_local and db_type in ["int", "stg"]:
        if not create_local_database(config["url"]):
            return False

    # Step 2: Run migrations
    if not run_command(["alembic", "downgrade", "base"], "Reset database schema"):
        return False

    if not run_command(["alembic", "upgrade", "head"], "Apply database migrations"):
        return False

    # Load region boundaries if table exists and is empty
    try:
        db_params = parse_database_url(config["url"])
        conn = psycopg2.connect(
            host=db_params["host"],
            port=db_params["port"],
            user=db_params["user"],
            password=db_params["password"],
            database=db_params["database"],
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema='public' AND table_name='region_boundaries'
                )
                """
            )
            exists = cur.fetchone()[0]
            count = 0
            if exists:
                cur.execute("SELECT COUNT(1) FROM region_boundaries")
                count = cur.fetchone()[0]
        conn.close()
        if exists and count == 0:
            # For INT database, region boundaries are optional (tests work without them)
            if db_type == "int":
                result = run_command([sys.executable, "scripts/load_region_boundaries.py"], "Load region boundaries")
                if not result:
                    print(
                        f"{YELLOW}⚠{NC} Region boundaries failed to load for INT database - continuing anyway (tests don't require them)"
                    )
            else:
                # For STG and PROD, region boundaries are required
                if not run_command([sys.executable, "scripts/load_region_boundaries.py"], "Load region boundaries"):
                    return False
    except Exception as e:
        print(f"{YELLOW}⚠{NC} Skipping auto-load of region boundaries ({e})")

    # Step 3: Seed roles and permissions (required for ULID migration)
    if not run_command([sys.executable, "scripts/seed_roles_permissions.py"], "Seed roles and permissions"):
        return False

    # Step 4: Seed data
    if not run_command([sys.executable, "scripts/reset_and_seed_yaml.py"], "Seed database with YAML data"):
        return False

    # Step 5: Generate embeddings
    if not run_command([sys.executable, "scripts/generate_service_embeddings.py"], "Generate service embeddings"):
        return False

    # Step 6: Calculate analytics
    if not run_command([sys.executable, "scripts/calculate_service_analytics.py"], "Calculate service analytics"):
        return False

    # Step 7: Clear cache to ensure fresh data
    if not clear_cache(db_type):
        return False

    print(f"\n{GREEN}{BOLD}✅ Database preparation complete!{NC}")
    print_header(db_type)

    return True


def main():
    """Main entry point."""
    # Parse arguments
    if len(sys.argv) > 1:
        db_type = sys.argv[1].lower()
    else:
        db_type = "int"  # Default to INT

    # Validate database type
    if db_type not in DB_CONFIG:
        print(f"{RED}Error: Invalid database type '{db_type}'{NC}")
        print(f"Valid options: {', '.join(DB_CONFIG.keys())}")
        print("\nUsage:")
        print("  python scripts/prep_db.py       # Default: INT database")
        print("  python scripts/prep_db.py int   # INT database")
        print("  python scripts/prep_db.py stg   # STG database")
        print("  python scripts/prep_db.py prod  # PROD database (requires confirmation)")
        sys.exit(1)

    # Prepare the database
    if not prep_database(db_type):
        sys.exit(1)


if __name__ == "__main__":
    main()
