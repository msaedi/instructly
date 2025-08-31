# backend/app/tasks/celery_init.py
"""
Initialize Celery with proper database configuration.

This module ensures Celery uses the correct database based on the
three-tier system (INT/STG/PROD).
"""

import os
import sys

# Determine which database to use via SITE_MODE only
site_mode = os.getenv("SITE_MODE", "int").lower()
if "pytest" in sys.modules:
    site_mode = "int"

if not os.getenv("SUPPRESS_DB_MESSAGES"):
    print(f"[Celery Init] SITE_MODE={site_mode}")
