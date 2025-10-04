"""Prometheus counters and gauges for background-check flows."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

from ..monitoring.prometheus_metrics import REGISTRY

# Background-check invite outcomes (success and notable failure scenarios).
BGC_INVITES_TOTAL = Counter(
    "bgc_invites_total",
    "Background-check invites by outcome",
    ["outcome"],
    registry=REGISTRY,
)


# Checkr webhook processing states segmented by normalized result.
CHECKR_WEBHOOK_TOTAL = Counter(
    "checkr_webhook_total",
    "Checkr webhook events processed",
    ["result", "outcome"],
    registry=REGISTRY,
)


# Background-job failure counter grouped by job type.
BACKGROUND_JOB_FAILURES_TOTAL = Counter(
    "background_job_failures_total",
    "Background jobs that failed",
    ["type"],
    registry=REGISTRY,
)


# Adverse-action scheduling and execution metrics.
BGC_FINAL_ADVERSE_SCHEDULED_TOTAL = Counter(
    "bgc_final_adverse_scheduled_total",
    "Final adverse action jobs scheduled",
    registry=REGISTRY,
)
BGC_FINAL_ADVERSE_EXECUTED_TOTAL = Counter(
    "bgc_final_adverse_executed_total",
    "Final adverse action job outcomes",
    ["outcome"],
    registry=REGISTRY,
)


# Tracks number of instructors pending background check review beyond seven days.
BGC_PENDING_7D = Gauge(
    "bgc_pending_over_7d",
    "Number of instructors pending more than 7 days",
    registry=REGISTRY,
)


__all__ = [
    "BGC_INVITES_TOTAL",
    "CHECKR_WEBHOOK_TOTAL",
    "BACKGROUND_JOB_FAILURES_TOTAL",
    "BGC_FINAL_ADVERSE_SCHEDULED_TOTAL",
    "BGC_FINAL_ADVERSE_EXECUTED_TOTAL",
    "BGC_PENDING_7D",
]
