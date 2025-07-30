# backend/app/tasks/celery_init.py
"""
Initialize Celery with proper database configuration.

This module ensures Celery uses the correct database based on the
three-tier system (INT/STG/PROD).
"""

import os
import sys

# Determine which database to use
if "pytest" in sys.modules:
    # Force INT for tests
    os.environ.pop("USE_STG_DATABASE", None)
    os.environ.pop("USE_PROD_DATABASE", None)
    print("[Celery Init] Using INT database (pytest detected)")
elif os.getenv("USE_PROD_DATABASE") == "true":
    print("[Celery Init] Using PROD database")
elif os.getenv("USE_STG_DATABASE") == "true":
    print("[Celery Init] Using STG database")
else:
    # Handle legacy USE_TEST_DATABASE flag
    if os.getenv("USE_TEST_DATABASE") == "true":
        print("[Celery Init] Using INT database (legacy flag)")
    else:
        print("[Celery Init] Using INT database (default)")
