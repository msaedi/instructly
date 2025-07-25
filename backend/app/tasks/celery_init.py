# backend/app/tasks/celery_init.py
"""
Initialize Celery with proper database configuration.

This module handles the USE_TEST_DATABASE environment variable
BEFORE any database connections are created.
"""

import os

# Check if we should use test database BEFORE importing anything else
if os.getenv("USE_TEST_DATABASE") == "true":
    # Override DATABASE_URL with test database
    test_db_url = os.getenv("test_database_url", "postgresql://postgres:postgres@localhost:5432/instainstru_test")
    os.environ["DATABASE_URL"] = test_db_url
    print(f"[Celery Init] Using TEST database: {test_db_url.split('@')[1]}")
else:
    print(f"[Celery Init] Using PRODUCTION database")
