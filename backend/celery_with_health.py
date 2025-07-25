#!/usr/bin/env python3
"""
Run Celery worker with a simple health check endpoint.

This allows Celery to run as a Render Web Service with health checks.
"""

import os
import socket
import subprocess
import sys
import threading
import time
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


def wait_for_port(port, timeout=10):
    """Wait for port to be available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(("127.0.0.1", port))
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)
    return False


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
    # Get port from environment
    port = int(os.environ.get("PORT", 10000))

    # Start health check server in a separate thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Wait for the health server to be ready
    print("Waiting for health server to start...")
    if wait_for_port(port, timeout=10):
        print(f"Health server is ready on port {port}")
    else:
        print(f"Warning: Health server may not be ready on port {port}")

    # Additional delay to ensure Render detects the port
    time.sleep(2)

    # Run Celery worker in main thread
    print("Starting Celery worker...")
    run_celery_worker()
