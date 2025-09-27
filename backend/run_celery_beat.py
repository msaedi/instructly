#!/usr/bin/env python3
# backend/run_celery_beat.py
"""
Development Celery beat runner that uses staging database
For local development only - preserves development data
"""
import os
from pathlib import Path
import subprocess
import sys

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# Default SITE_MODE for local development
os.environ.setdefault("SITE_MODE", "local")

if __name__ == "__main__":
    print("🚀 Starting Celery beat (SITE_MODE=" + os.getenv("SITE_MODE", "local") + ")…")
    print("📊 This preserves your local development data between test runs")
    print("⏰ Beat will schedule periodic tasks")
    print("")

    # Run Celery beat with the same settings as the user's command
    cmd = [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=info"]

    subprocess.run(cmd)
