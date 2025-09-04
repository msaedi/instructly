from prometheus_client import Counter, Histogram

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

__all__ = ["rl_decisions", "rl_retry_after"]

# Seed an initial series so histogram buckets appear prior to first observation in tests
try:
    rl_retry_after.labels(bucket="bootstrap", shadow="true").observe(0.0)
except Exception:
    pass
