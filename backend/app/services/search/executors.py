# backend/app/services/search/executors.py
"""
Dedicated thread pool executors for search operations.

Isolates blocking OpenAI calls from the default asyncio thread pool,
preventing search load from degrading non-search endpoints.

Under high load, sync OpenAI calls in asyncio.to_thread() saturate
the default executor (40 threads), causing ALL endpoints to queue
behind search requests. This dedicated pool ensures:

1. Search blocking work has bounded concurrency
2. Other endpoints (categories, profiles) remain responsive
3. System degrades gracefully under load
"""
from concurrent.futures import ThreadPoolExecutor
import logging
import os

logger = logging.getLogger(__name__)

# Keep small to prevent worker-local overload and protect other endpoints.
# With 2 workers and 2 threads each = max 4 concurrent blocking OpenAI calls.
# This creates natural backpressure - additional requests will queue here
# rather than saturating the entire async runtime.
OPENAI_BLOCKING_MAX_WORKERS = int(os.getenv("OPENAI_BLOCKING_MAX_WORKERS", "2"))

OPENAI_EXECUTOR = ThreadPoolExecutor(
    max_workers=OPENAI_BLOCKING_MAX_WORKERS,
    thread_name_prefix="openai-blocking",
)

logger.info(
    f"[EXECUTORS] Created dedicated OpenAI executor with {OPENAI_BLOCKING_MAX_WORKERS} workers"
)
