#!/usr/bin/env python3
"""
Start Flower with environment configuration.
"""

import os
import subprocess
import sys

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
]

print(f"Starting Flower on port {port}...")
subprocess.run(cmd)
