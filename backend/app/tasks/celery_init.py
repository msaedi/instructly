# backend/app/tasks/celery_init.py
"""
Initialize Celery with proper database configuration.

This module ensures Celery uses the correct database based on the
three-tier system (INT/STG/PROD).
"""

import os
import sys


def _derive_site_mode() -> str:
    """Derive SITE_MODE for worker/beat processes when not explicitly set."""
    explicit = os.getenv("SITE_MODE", "").strip().lower()
    if explicit:
        return explicit

    # Prefer preview when preview DB URL is present
    if os.getenv("PREVIEW_DATABASE_URL") or os.getenv("preview_database_url"):
        return "preview"

    # Use prod when only prod DB URL is present
    if os.getenv("PROD_DATABASE_URL") or os.getenv("prod_database_url"):
        return "prod"

    # Use local/stg if STG URL present
    if os.getenv("STG_DATABASE_URL") or os.getenv("stg_database_url"):
        return "local"

    # Default safest
    # If running on a deployment platform (e.g., Render), prefer preview semantics
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_SERVICE_NAME"):
        return "preview"
    return "int"


# Determine which database to use via SITE_MODE only
site_mode = _derive_site_mode()
if "pytest" in sys.modules:
    site_mode = "int"

# Export for child imports (e.g., DatabaseConfig)
os.environ["SITE_MODE"] = site_mode

if not os.getenv("SUPPRESS_DB_MESSAGES"):
    print(f"[Celery Init] SITE_MODE={site_mode}")
