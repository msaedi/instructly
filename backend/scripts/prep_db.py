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
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or backend_dir)

        if result.returncode == 0:
            print(f"{GREEN}✓{NC} {description} completed")
            if result.stdout and len(result.stdout) < 1000:  # Show short output
                print(result.stdout)
            return True
        else:
            print(f"{RED}✗{NC} {description} failed")
            if result.stderr:
                print(result.stderr)
            return False

    except Exception as e:
        print(f"{RED}✗{NC} Error: {e}")
        return False


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

    # Step 3: Seed data
    if not run_command([sys.executable, "scripts/reset_and_seed_yaml.py"], "Seed database with YAML data"):
        return False

    # Step 4: Generate embeddings
    if not run_command([sys.executable, "scripts/generate_service_embeddings.py"], "Generate service embeddings"):
        return False

    # Step 5: Calculate analytics
    if not run_command([sys.executable, "scripts/calculate_service_analytics.py"], "Calculate service analytics"):
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
