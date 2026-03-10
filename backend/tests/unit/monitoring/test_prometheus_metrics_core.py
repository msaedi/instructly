from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.monitoring import prometheus_metrics as metrics_module


def _reset_metrics_cache() -> None:
    metrics_module.PrometheusMetrics._cache_payload = None
    metrics_module.PrometheusMetrics._cache_ts = None
    metrics_module.PrometheusMetrics._cache_ttl_seconds = 1.0


def test_metrics_ttl_uses_test_mode(monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "test")

    assert metrics_module._metrics_ttl_seconds() == 2.0


def test_get_metrics_reuses_cache_until_invalidated(monkeypatch) -> None:
    _reset_metrics_cache()
    generated = iter([b"payload-1", b"payload-2"])
    monotonic_values = iter([10.0, 10.5, 11.0, 11.2, 11.3])

    monkeypatch.setattr(metrics_module, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(metrics_module, "generate_latest", lambda _registry: next(generated))
    monkeypatch.setattr(
        metrics_module.PrometheusMetrics,
        "_update_db_pool_metrics",
        staticmethod(lambda: None),
    )

    metrics_module.PrometheusMetrics.prewarm()
    warm_payload = metrics_module.PrometheusMetrics.get_metrics()
    cached_payload = metrics_module.PrometheusMetrics.get_metrics()

    metrics_module.PrometheusMetrics.record_notification_attempt("booking.created")
    refreshed_payload = metrics_module.PrometheusMetrics.get_metrics()

    assert warm_payload == b"payload-1"
    assert cached_payload == b"payload-1"
    assert refreshed_payload == b"payload-2"


def test_update_db_pool_metrics_sets_all_gauges(monkeypatch) -> None:
    statuses = {
        "api-observed": {
            "size": 15,
            "overflow_in_use": 2,
            "checked_out": 5,
            "checked_in": 10,
            "utilization_pct": 33.3,
        }
    }
    monkeypatch.setattr("app.database.get_pool_status_for_role", lambda: statuses)
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(service_role="worker"),
        raising=False,
    )

    metrics_module.PrometheusMetrics._update_db_pool_metrics()

    labels = {"pool_name": "api-observed", "service_role": "worker"}
    size_samples = list(metrics_module.db_pool_size.collect())[0].samples
    usage_samples = list(metrics_module.db_pool_usage_percent.collect())[0].samples

    assert any(sample.labels == labels and sample.value == 15.0 for sample in size_samples)
    assert any(sample.labels == labels and sample.value == 33.3 for sample in usage_samples)


def test_update_db_pool_metrics_swallow_lookup_failures(monkeypatch) -> None:
    def _boom():
        raise RuntimeError("db metrics unavailable")

    monkeypatch.setattr("app.database.get_pool_status_for_role", _boom)
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(service_role="api"),
        raising=False,
    )

    with patch.object(metrics_module.logger, "debug") as debug_log:
        metrics_module.PrometheusMetrics._update_db_pool_metrics()

    debug_log.assert_called_once()


def test_domain_metric_helpers_invalidate_cache() -> None:
    metrics_module.PrometheusMetrics._cache_payload = b"cached"
    metrics_module.PrometheusMetrics._cache_ts = 5.0

    metrics_module.PrometheusMetrics.inc_credits_applied("referral")
    assert metrics_module.PrometheusMetrics._cache_payload is None
    assert metrics_module.PrometheusMetrics._cache_ts is None

    metrics_module.PrometheusMetrics._cache_payload = b"cached"
    metrics_module.PrometheusMetrics._cache_ts = 6.0
    metrics_module.PrometheusMetrics.inc_instant_payout_request("success")

    assert metrics_module.PrometheusMetrics._cache_payload is None
    assert metrics_module.PrometheusMetrics._cache_ts is None
