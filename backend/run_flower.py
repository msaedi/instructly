#!/usr/bin/env python3
"""
Start Flower with environment configuration.
"""

import os
import subprocess
import sys

# Only force staging database for local development (not in production)
if not os.getenv("INSTAINSTRU_PRODUCTION_MODE"):
    os.environ["USE_STG_DATABASE"] = "true"

# Get environment variables
port = os.getenv("PORT", "5555")
basic_auth = os.getenv("FLOWER_BASIC_AUTH", "admin:password")

# Build command
cmd = [
    sys.executable,
    "-m",
    "celery",
    "-A",
    "flower_celery_standalone:celery_app",
    "flower",
    f"--port={port}",
    "--address=0.0.0.0",
    f"--basic_auth={basic_auth}",
    "--max_tasks=10000",  # Store up to 10k tasks in memory
    "--persistent=True",  # Enable persistent mode
    "--db=/tmp/flower.db",  # Use local SQLite for persistence
]

print(f"Starting Flower on port {port}...")
subprocess.run(cmd)
