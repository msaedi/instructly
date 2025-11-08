"""Retention purge metrics with optional Prometheus integration."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter
from typing import Any, DefaultDict, Iterator, cast

try:  # pragma: no cover - optional dependency
    from prometheus_client import Counter, Histogram, generate_latest

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover - fallback when prometheus_client missing
    Counter = Histogram = generate_latest = cast(Any, None)
    _PROM_AVAILABLE = False

_TOTAL_METRIC_NAME = "retention_purge_total"
_ERROR_METRIC_NAME = "retention_purge_errors_total"
_CHUNK_METRIC_NAME = "retention_purge_chunk_seconds"

_totals: DefaultDict[str, int] = defaultdict(int)
_errors: DefaultDict[str, int] = defaultdict(int)
_chunk_sum: DefaultDict[str, float] = defaultdict(float)
_chunk_count: DefaultDict[str, int] = defaultdict(int)

if _PROM_AVAILABLE:
    _TOTAL_COUNTER = Counter(
        _TOTAL_METRIC_NAME,
        "Total soft-deleted rows purged during retention cleanup",
        ["table"],
    )
    _ERROR_COUNTER = Counter(
        _ERROR_METRIC_NAME,
        "Errors encountered while purging soft-deleted rows",
        ["table"],
    )
    _CHUNK_HISTOGRAM = Histogram(
        _CHUNK_METRIC_NAME,
        "Duration of retention purge chunks in seconds",
        ["table"],
    )
else:
    _TOTAL_COUNTER = _ERROR_COUNTER = _CHUNK_HISTOGRAM = cast(Any, None)


def inc_total(table: str, n: int) -> None:
    """Increment total purged rows for the given table."""
    if n <= 0:
        return
    if _PROM_AVAILABLE:
        _TOTAL_COUNTER.labels(table=table).inc(n)
    else:
        _totals[table] += n


def inc_error(table: str, n: int = 1) -> None:
    """Increment error counter for the given table."""
    if n <= 0:
        return
    if _PROM_AVAILABLE:
        _ERROR_COUNTER.labels(table=table).inc(n)
    else:
        _errors[table] += n


@contextmanager
def time_chunk(table: str) -> Iterator[None]:
    """Record the duration of a purge chunk for the given table."""
    if _PROM_AVAILABLE:
        timer = _CHUNK_HISTOGRAM.labels(table=table).time()
        with timer:
            yield
    else:
        start = perf_counter()
        try:
            yield
        finally:
            duration = perf_counter() - start
            _chunk_sum[table] += duration
            _chunk_count[table] += 1


def render_text() -> str:
    """
    Render metrics text for debugging purposes.

    Returns Prometheus exposition format when the client is available,
    otherwise emits a simple text dump of the in-memory counters.
    """
    if _PROM_AVAILABLE:
        try:
            output = generate_latest()
            return cast(bytes, output).decode("utf-8")
        except Exception:  # pragma: no cover - defensive fallback
            pass

    lines: list[str] = []
    for table, count in sorted(_totals.items()):
        lines.append(f'{_TOTAL_METRIC_NAME}{{table="{table}"}} {count}')
    for table, count in sorted(_errors.items()):
        lines.append(f'{_ERROR_METRIC_NAME}{{table="{table}"}} {count}')
    for table in sorted(_chunk_sum.keys()):
        total = _chunk_sum[table]
        cnt = _chunk_count[table]
        lines.append(f'{_CHUNK_METRIC_NAME}_sum{{table="{table}"}} {total}')
        lines.append(f'{_CHUNK_METRIC_NAME}_count{{table="{table}"}} {cnt}')

    if not lines:
        lines.append("# retention metrics not available")

    return "\n".join(lines) + "\n"
