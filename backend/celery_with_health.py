#!/usr/bin/env python3
"""
Run Celery worker with a simple health check endpoint.

This allows Celery to run as a Render Web Service with health checks.
"""

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    """Simple health check handler."""

    def do_GET(self):
        """Respond to health check requests."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Celery worker is running")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress request logging."""


def run_health_server():
    """Run the health check server."""
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health check server listening on port {port}")
    server.serve_forever()


def run_celery_worker():
    """Run the Celery worker."""
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
    ]

    # Run Celery worker
    subprocess.run(cmd)


if __name__ == "__main__":
    # Start health check server in a separate thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Give the health server a moment to start
    import time

    time.sleep(1)

    # Run Celery worker in main thread
    run_celery_worker()
