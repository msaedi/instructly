#!/usr/bin/env python3
"""
Flower monitoring app for Celery.

This runs Flower with basic authentication for production use.
"""

import os
import subprocess
import sys

# Get environment variables
port = os.getenv("PORT", "5555")
basic_auth = os.getenv("FLOWER_BASIC_AUTH", "admin:instructly2024")
broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Build command
cmd = [
    sys.executable,
    "-m",
    "flower",
    f"--port={port}",
    "--address=0.0.0.0",
    f"--broker={broker_url}",
    f"--basic_auth={basic_auth}",
    "--db=/tmp/flower.db",
    "--persistent=true",
    "--max_tasks=10000",
]

print(f"Starting Flower on port {port}...")
print(f"Command: {' '.join(cmd)}")

# Run Flower
subprocess.run(cmd)
