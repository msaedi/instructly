"""Prometheus metrics for bitmap availability retention."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

from app.monitoring.prometheus_metrics import REGISTRY

availability_days_purged_total = Counter(
    "availability_days_purged_total",
    "Total availability_day rows purged by retention",
    labelnames=("site_mode",),
    registry=REGISTRY,
)

availability_retention_run_seconds = Histogram(
    "availability_retention_run_seconds",
    "Duration of availability retention purge runs (seconds)",
    registry=REGISTRY,
)

__all__ = [
    "availability_days_purged_total",
    "availability_retention_run_seconds",
]
