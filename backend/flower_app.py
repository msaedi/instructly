#!/usr/bin/env python3
"""
Flower monitoring app for Celery.

This runs Flower with basic authentication for production use.
"""

import os

from flower import app
from flower.utils import options

# Configure Flower options
flower_options = options()

# Basic authentication
flower_options.basic_auth = [os.getenv("FLOWER_BASIC_AUTH", "admin:instructly2024")]

# Port (Render will set PORT env var)
flower_options.port = int(os.getenv("PORT", 5555))

# Address to bind
flower_options.address = "0.0.0.0"

# Broker URL (use same as Celery)
flower_options.broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Enable persistent storage
flower_options.db = "/tmp/flower.db"

# URL prefix if behind proxy
flower_options.url_prefix = os.getenv("FLOWER_URL_PREFIX", "")

# Max tasks to keep in memory
flower_options.max_tasks = 10000

# Enable task runtime info
flower_options.tasks_runtime = True

if __name__ == "__main__":
    # Start Flower
    app.start(flower_options)
