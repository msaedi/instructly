#!/usr/bin/env python3
"""
Simple Celery worker with health check for Render.
Starts health server immediately on import.
"""

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Start health server immediately on module import
PORT = int(os.environ.get("PORT", 10000))


class HealthHandler(BaseHTTPRequestHandler):
    """Simple health check handler."""

    def do_GET(self):
        """Respond to health check requests."""
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"healthy")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress request logging."""


def start_health_server():
    """Start the health check server."""
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"[HEALTH] Server started on 0.0.0.0:{PORT}", file=sys.stderr, flush=True)
    server.serve_forever()


# Start health server immediately in background thread
print(f"[STARTUP] Starting health check server on port {PORT}...", file=sys.stderr, flush=True)
health_thread = threading.Thread(target=start_health_server, daemon=True)
health_thread.start()

# Import Celery after health server is started
import time

time.sleep(1)  # Give health server time to bind

# Now start Celery
from celery import current_app
from celery.bin import worker

if __name__ == "__main__":
    print("[STARTUP] Starting Celery worker...", file=sys.stderr, flush=True)
    # Use Celery's worker command
    worker = worker.worker(app=current_app)
    worker.run(
        loglevel="INFO",
        traceback=True,
        concurrency=2,
        max_tasks_per_child=100,
    )
