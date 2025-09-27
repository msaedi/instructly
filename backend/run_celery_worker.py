#!/usr/bin/env python3
# backend/run_celery_worker.py
"""
Development Celery worker runner that uses staging database
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
    print("🚀 Starting Celery worker (SITE_MODE=" + os.getenv("SITE_MODE", "local") + ")…")
    print("📊 This preserves your local development data between test runs")
    print(
        "🔄 Worker configuration: concurrency=2, max-tasks-per-child=100, queues=analytics,celery,privacy,maintenance,email,notifications,payments"
    )
    print("")

    # Run Celery worker with the same settings as the user's command
    # Allow both CELERY_QUEUE and CELERY_QUEUES; prefer CELERY_QUEUES if provided
    queues = (
        os.getenv("CELERY_QUEUES")
        or os.getenv("CELERY_QUEUE")
        or "analytics,celery,privacy,maintenance,email,notifications,payments"
    )
    print(f"📦 Consuming queues: {queues}")

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
        "-Q",
        queues,
    ]

    subprocess.run(cmd)
