# backend/app/monitoring/availability_perf.py
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
import time
from typing import Any, Callable, Dict, Iterator, Optional

WEEK_GET_ENDPOINT = "GET /api/v1/instructors/availability/week"
WEEK_SAVE_ENDPOINT = "POST /api/v1/instructors/availability/week"
COPY_WEEK_ENDPOINT = "POST /api/v1/instructors/availability/copy-week"

_logger = logging.getLogger("app.perf.availability")


def _is_perf_enabled() -> bool:
    """Check if AVAILABILITY_PERF_DEBUG is enabled."""
    return os.getenv("AVAILABILITY_PERF_DEBUG") in {"1", "true", "TRUE", "True"}


def _serialize_value(value: Any) -> Any:
    """Serialize values for structured logging."""
    if value is None:
        return None
    iso_formatter = getattr(value, "isoformat", None)
    if callable(iso_formatter):
        try:
            return iso_formatter()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return value


def _emit_payload(payload: Dict[str, Any]) -> None:
    """Emit the payload as a structured log line."""
    _logger.info("availability_perf %s", json.dumps(payload, default=str))


PerfSetter = Callable[..., None]
OptionalPerfSetter = Optional[PerfSetter]


@contextmanager
def availability_perf_span(span: str, **fields: Any) -> Iterator[OptionalPerfSetter]:
    """
    Measure the elapsed time for a code block when perf debugging is enabled.

    Returns a setter callable to append extra fields before the span exits.
    """
    if not _is_perf_enabled():
        yield None
        return

    extra: Dict[str, Any] = {}

    def set_extra(**kwargs: Any) -> None:
        extra.update(kwargs)

    start = time.perf_counter()
    try:
        yield set_extra
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        payload = {"span": span, "ms": round(duration_ms, 2)}
        for key, value in {**fields, **extra}.items():
            serialized = _serialize_value(value)
            if serialized is not None:
                payload[key] = serialized
        _emit_payload(payload)


def estimate_payload_size_bytes(payload: Any) -> Optional[int]:
    """
    Best-effort payload size estimation in bytes for structured inputs.

    Attempts to use Pydantic's model_dump_json if available, otherwise
    falls back to json serialization.
    """
    if payload is None:
        return 0

    try:
        if hasattr(payload, "model_dump_json"):
            data = payload.model_dump_json()
        elif hasattr(payload, "json"):
            data = payload.json()
        else:
            data = json.dumps(payload)
        return len(data.encode("utf-8"))
    except Exception:
        return None
