#!/usr/bin/env python3
"""
Flower monitoring app for Celery.

This runs Flower with basic authentication for production use.
"""

import os
import sys

# Set up basic auth from environment
basic_auth = os.getenv("FLOWER_BASIC_AUTH", "admin:instructly2024")
os.environ["FLOWER_BASIC_AUTH"] = basic_auth

# Set broker URL
broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
os.environ["FLOWER_BROKER"] = broker_url

# Set port
port = os.getenv("PORT", "5555")
os.environ["FLOWER_PORT"] = port

# Set address
os.environ["FLOWER_ADDRESS"] = "0.0.0.0"

# Set other options
os.environ["FLOWER_DB"] = "/tmp/flower.db"
os.environ["FLOWER_MAX_TASKS"] = "10000"
os.environ["FLOWER_PERSISTENT"] = "true"

# Import and run Flower's main
from flower.__main__ import main

if __name__ == "__main__":
    # Run Flower with command line args
    sys.argv = ["flower", "--port=" + port, "--address=0.0.0.0"]
    main()
