#!/usr/bin/env python3
# backend/run_celery_worker.py
"""
Development Celery worker runner that uses staging database
For local development only - preserves development data
"""
import os
import subprocess
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# Force staging database for local development
os.environ["USE_STG_DATABASE"] = "true"

if __name__ == "__main__":
    print("🚀 Starting Celery worker with STAGING database...")
    print("📊 This preserves your local development data between test runs")
    print("🔄 Worker configuration: concurrency=2, max-tasks-per-child=100")
    print("")

    # Run Celery worker with the same settings as the user's command
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.tasks.celery_app",
        "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--max-tasks-per-child=100",
        "--pool=prefork",
    ]

    subprocess.run(cmd)
