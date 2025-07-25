#!/usr/bin/env python3
"""
Celery Beat with health check endpoint for Render.

Since Render Web Services require an open port, this wrapper runs
Celery Beat alongside a simple HTTP health check server.
"""

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    """Simple health check handler."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "celery-beat"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress log messages."""


def run_health_server():
    """Run the health check server."""
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health check server listening on port {port}")
    server.serve_forever()


def run_celery_beat():
    """Run Celery Beat."""
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.tasks.celery_app",
        "beat",
        "--loglevel=info",
    ]

    # Run Celery Beat
    subprocess.run(cmd)


if __name__ == "__main__":
    # Start health check server in a separate thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Run Celery Beat in the main thread
    run_celery_beat()
