# backend/app/services/search/metrics.py
"""
Prometheus metrics for NL search.

Provides observability for:
- Search latency by stage
- Result quality metrics
- Cache performance
- Degradation events
"""
from __future__ import annotations

from typing import Dict, List

from prometheus_client import Counter, Gauge, Histogram

from app.monitoring.prometheus_metrics import REGISTRY, PrometheusMetrics

# Latency metrics
SEARCH_LATENCY = Histogram(
    "instainstru_nl_search_latency_ms",
    "Search latency in milliseconds",
    ["stage", "cache_hit", "parsing_mode"],
    registry=REGISTRY,
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000],
)

OPENAI_LATENCY = Histogram(
    "instainstru_nl_search_openai_latency_ms",
    "OpenAI API latency in milliseconds",
    ["endpoint"],
    registry=REGISTRY,
    buckets=[25, 50, 100, 200, 500, 1000, 2000],
)

# Quality metrics
SEARCH_RESULT_COUNT = Histogram(
    "instainstru_nl_search_result_count",
    "Number of search results returned",
    registry=REGISTRY,
    buckets=[0, 1, 5, 10, 20, 50, 100],
)

SEARCH_ZERO_RESULTS = Counter(
    "instainstru_nl_search_zero_results_total",
    "Count of searches returning zero results",
    ["has_constraints"],
    registry=REGISTRY,
)

TYPO_CORRECTIONS = Counter(
    "instainstru_nl_search_typo_corrections_total",
    "Count of typo corrections made",
    ["confidence"],
    registry=REGISTRY,
)

QUERY_COMPLEXITY = Histogram(
    "instainstru_nl_search_query_complexity",
    "Number of constraints in query",
    ["parsing_mode"],
    registry=REGISTRY,
    buckets=[0, 1, 2, 3, 4, 5, 6],
)

# Infrastructure metrics
CACHE_HIT = Counter(
    "instainstru_nl_search_cache_hit_total",
    "Cache hit count by type",
    ["cache_type"],
    registry=REGISTRY,
)

CACHE_MISS = Counter(
    "instainstru_nl_search_cache_miss_total",
    "Cache miss count by type",
    ["cache_type"],
    registry=REGISTRY,
)

CIRCUIT_BREAKER_STATE = Gauge(
    "instainstru_nl_search_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["component"],
    registry=REGISTRY,
)

DEGRADATION_EVENTS = Counter(
    "instainstru_nl_search_degradation_total",
    "Count of degradation events",
    ["level", "component"],
    registry=REGISTRY,
)

# Search volume
SEARCH_REQUESTS = Counter(
    "instainstru_nl_search_requests_total",
    "Total search requests",
    ["status"],
    registry=REGISTRY,
)


def record_search_metrics(
    total_latency_ms: int,
    stage_latencies: Dict[str, int],
    cache_hit: bool,
    parsing_mode: str,
    result_count: int,
    degraded: bool,
    degradation_reasons: List[str],
) -> None:
    """Record all metrics for a search request."""

    # Record latencies
    cache_hit_label = "true" if cache_hit else "false"

    SEARCH_LATENCY.labels(
        stage="total", cache_hit=cache_hit_label, parsing_mode=parsing_mode
    ).observe(total_latency_ms)

    for stage, latency in stage_latencies.items():
        SEARCH_LATENCY.labels(
            stage=stage, cache_hit=cache_hit_label, parsing_mode=parsing_mode
        ).observe(latency)

    # Record result count
    SEARCH_RESULT_COUNT.observe(result_count)

    # Record zero results
    if result_count == 0:
        has_constraints = "true" if stage_latencies else "false"
        SEARCH_ZERO_RESULTS.labels(has_constraints=has_constraints).inc()

    # Record cache hit/miss
    if cache_hit:
        CACHE_HIT.labels(cache_type="response").inc()
    else:
        CACHE_MISS.labels(cache_type="response").inc()

    # Record degradation
    if degraded:
        for reason in degradation_reasons:
            component = reason.replace("_error", "").replace("_unavailable", "")
            DEGRADATION_EVENTS.labels(level="1", component=component).inc()

    # Record request
    status = "success" if result_count > 0 else "zero_results"
    SEARCH_REQUESTS.labels(status=status).inc()

    # Invalidate prometheus cache
    PrometheusMetrics._invalidate_cache()


def record_cache_event(cache_type: str, hit: bool) -> None:
    """Record a cache hit or miss."""
    if hit:
        CACHE_HIT.labels(cache_type=cache_type).inc()
    else:
        CACHE_MISS.labels(cache_type=cache_type).inc()
    PrometheusMetrics._invalidate_cache()


def record_openai_latency(endpoint: str, latency_ms: int) -> None:
    """Record OpenAI API call latency."""
    OPENAI_LATENCY.labels(endpoint=endpoint).observe(latency_ms)
    PrometheusMetrics._invalidate_cache()


def update_circuit_breaker_state(component: str, state: str) -> None:
    """Update circuit breaker state gauge."""
    state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
    CIRCUIT_BREAKER_STATE.labels(component=component).set(state_value)
    PrometheusMetrics._invalidate_cache()


def record_query_complexity(parsing_mode: str, constraint_count: int) -> None:
    """Record query complexity for analysis."""
    QUERY_COMPLEXITY.labels(parsing_mode=parsing_mode).observe(constraint_count)
    PrometheusMetrics._invalidate_cache()


def record_typo_correction(confidence: str) -> None:
    """Record a typo correction event."""
    TYPO_CORRECTIONS.labels(confidence=confidence).inc()
    PrometheusMetrics._invalidate_cache()


__all__ = [
    # Metrics
    "SEARCH_LATENCY",
    "OPENAI_LATENCY",
    "SEARCH_RESULT_COUNT",
    "SEARCH_ZERO_RESULTS",
    "TYPO_CORRECTIONS",
    "QUERY_COMPLEXITY",
    "CACHE_HIT",
    "CACHE_MISS",
    "CIRCUIT_BREAKER_STATE",
    "DEGRADATION_EVENTS",
    "SEARCH_REQUESTS",
    # Helper functions
    "record_search_metrics",
    "record_cache_event",
    "record_openai_latency",
    "update_circuit_breaker_state",
    "record_query_complexity",
    "record_typo_correction",
]
