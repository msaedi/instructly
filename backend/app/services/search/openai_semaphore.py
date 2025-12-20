"""
Shared semaphore for expensive OpenAI calls in the NL search pipeline.

Limits concurrent OpenAI requests per worker to protect rate limits.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings


def _coerce_concurrency(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


OPENAI_CALL_CONCURRENCY = _coerce_concurrency(getattr(settings, "openai_call_concurrency", 3))
OPENAI_CALL_SEMAPHORE = asyncio.Semaphore(OPENAI_CALL_CONCURRENCY)
