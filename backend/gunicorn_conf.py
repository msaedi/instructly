"""Gunicorn configuration with worker-abort diagnostics.

When a worker exceeds --timeout, gunicorn kills it. This hook logs
what the worker was processing so we can identify slow endpoints.

Usage (Render start command):
  gunicorn app.main:app -c gunicorn_conf.py --bind 0.0.0.0:$PORT ...
"""

import logging
import os
import traceback

logger = logging.getLogger("gunicorn.error")

# ── Timeouts ─────────────────────────────────────────────────────────
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))


# ── Worker abort hook ────────────────────────────────────────────────
def worker_abort(worker):  # type: ignore[no-untyped-def]
    """Log stack traces of all threads when a worker is killed for timeout."""
    import sys
    import threading

    logger.critical(
        "Worker %s timed out (pid=%s). Dumping thread stacks:",
        worker,
        worker.pid,
    )
    for thread_id, frame in sys._current_frames().items():
        thread_name = "unknown"
        for t in threading.enumerate():
            if t.ident == thread_id:
                thread_name = t.name
                break
        stack = "".join(traceback.format_stack(frame))
        logger.critical(
            "Thread %s (id=%s):\n%s",
            thread_name,
            thread_id,
            stack,
        )
