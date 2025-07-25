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

# Build command - Flower 2.0 requires 'celery' command with 'flower' as sub-command
# Use the minimal celery_flower module to avoid loading full app config
cmd = [
    sys.executable,
    "-m",
    "celery",
    "-A",
    "app.tasks.celery_flower",
    "--broker=" + broker_url,
    "flower",
    "--port=" + port,
    "--address=0.0.0.0",
    "--basic_auth=" + basic_auth,
]

print(f"Starting Flower on port {port}...")
print(f"Broker: {broker_url.split('@')[1] if '@' in broker_url else broker_url}")

# Run Flower
subprocess.run(cmd)
