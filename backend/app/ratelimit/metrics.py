from prometheus_client import Counter, Gauge, Histogram

from app.monitoring.prometheus_metrics import REGISTRY

rl_decisions = Counter(
    "instainstru_rl_decisions_total",
    "rate-limit decisions",
    ["bucket", "action", "shadow"],
    registry=REGISTRY,
)
rl_retry_after = Histogram(
    "instainstru_rl_retry_after_seconds",
    "retry-after values",
    ["bucket", "shadow"],
    registry=REGISTRY,
    buckets=(0.0, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# PR-8: additional observability
rl_eval_errors = Counter(
    "instainstru_rl_eval_errors_total",
    "errors during rate-limit evaluation (e.g., Redis failures)",
    ["bucket"],
    registry=REGISTRY,
)

rl_eval_duration = Histogram(
    "instainstru_rl_eval_duration_seconds",
    "duration of rate-limit evaluation",
    ["bucket"],
    registry=REGISTRY,
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1),
)

rl_config_reload_total = Counter(
    "instainstru_rl_config_reload_total",
    "count of rate-limit configuration reloads",
    [],
    registry=REGISTRY,
)

rl_active_overrides = Gauge(
    "instainstru_rl_active_overrides",
    "number of active rate-limit policy overrides",
    [],
    registry=REGISTRY,
)

__all__ = [
    "rl_decisions",
    "rl_retry_after",
    "rl_eval_errors",
    "rl_eval_duration",
    "rl_config_reload_total",
    "rl_active_overrides",
]

# Seed an initial series so histogram buckets appear prior to first observation in tests
try:
    rl_retry_after.labels(bucket="bootstrap", shadow="true").observe(0.0)
    rl_eval_duration.labels(bucket="bootstrap").observe(0.0)
except Exception:
    pass
