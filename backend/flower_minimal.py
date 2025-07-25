#!/usr/bin/env python3
"""
Minimal Flower app that connects directly to Redis without importing the main app.
"""

import os
import subprocess
import sys

# Set environment variables
port = os.getenv("PORT", "5555")
basic_auth = os.getenv("FLOWER_BASIC_AUTH", "admin:instructly2024")
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a minimal Celery configuration file
celery_config = """
import ssl
from celery import Celery

redis_url = "{redis_url}"

# Handle SSL for Upstash Redis
broker_use_ssl = None
if redis_url.startswith("rediss://"):
    broker_use_ssl = {{
        "ssl_cert_reqs": ssl.CERT_NONE,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }}

celery_app = Celery(
    "instructly",
    broker=redis_url,
    backend=redis_url,
    broker_use_ssl=broker_use_ssl,
    redis_backend_use_ssl=broker_use_ssl,
)

celery_app.conf.update(
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_pool_restarts=True,
)
""".format(
    redis_url=redis_url
)

# Write the config to a temporary file
with open("/tmp/flower_celery_config.py", "w") as f:
    f.write(celery_config)

# Run Flower using the temporary config
cmd = [
    sys.executable,
    "-m",
    "celery",
    "-A",
    "/tmp/flower_celery_config:celery_app",
    "--broker=" + redis_url,
    "flower",
    "--port=" + port,
    "--address=0.0.0.0",
    "--basic_auth=" + basic_auth,
]

print(f"Starting Flower on port {port}...")
print(f"Broker: {redis_url.split('@')[1] if '@' in redis_url else redis_url}")

# Run Flower
subprocess.run(cmd)
