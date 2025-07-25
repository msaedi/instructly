"""
Standalone Celery configuration for Flower.
This file has NO imports from the app package.
"""

import os
import ssl

from celery import Celery

# Get Redis URL from environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Handle SSL for Upstash Redis
broker_use_ssl = None
if redis_url.startswith("rediss://"):
    broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }

# Create minimal Celery app for Flower
celery_app = Celery(
    "instructly",
    broker=redis_url,
    backend=redis_url,
    broker_use_ssl=broker_use_ssl,
    redis_backend_use_ssl=broker_use_ssl,
)

# Configure Celery for Flower monitoring
celery_app.conf.update(
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_pool_restarts=True,
)


# Register a dummy task for testing
@celery_app.task
def health_check():
    return "OK"
