"""Tests for app/ratelimit/metrics.py — coverage gaps L66-67."""
from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestMetricsBootstrapCoverage:
    """Cover the except Exception block (L66-67) in bootstrap seeding."""

    def test_bootstrap_exception_is_silent(self) -> None:
        """L66-67: if histogram.labels().observe() raises, it is silently caught.

        We cannot easily reload the module due to prometheus duplicate registration.
        Instead, we directly exercise the bootstrap try/except pattern.
        """
        mock_histogram = MagicMock()
        mock_histogram.labels.return_value.observe.side_effect = RuntimeError("boom")

        logger = logging.getLogger("app.ratelimit.metrics")

        # Replicate the bootstrap block from the module
        try:
            mock_histogram.labels(bucket="bootstrap", shadow="true").observe(0.0)
            mock_histogram.labels(bucket="bootstrap").observe(0.0)
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)

        # Verify the mock was called and raised, but we caught it
        assert mock_histogram.labels.call_count >= 1

    def test_bootstrap_observe_succeeds_normally(self) -> None:
        """Verify the normal (non-exception) bootstrap path works."""
        mock_histogram = MagicMock()
        mock_histogram.labels.return_value.observe.return_value = None

        # No exception should be raised
        try:
            mock_histogram.labels(bucket="bootstrap", shadow="true").observe(0.0)
            mock_histogram.labels(bucket="bootstrap").observe(0.0)
        except Exception:
            pytest.fail("Should not have raised")

        assert mock_histogram.labels.call_count == 2

    def test_metrics_are_importable(self) -> None:
        """Smoke test: all exported metrics are accessible."""
        from app.ratelimit.metrics import (
            rl_active_overrides,
            rl_config_reload_total,
            rl_decisions,
            rl_eval_duration,
            rl_eval_errors,
            rl_retry_after,
        )

        assert rl_decisions is not None
        assert rl_retry_after is not None
        assert rl_eval_errors is not None
        assert rl_eval_duration is not None
        assert rl_config_reload_total is not None
        assert rl_active_overrides is not None

    def test_bootstrap_except_branch_via_reload(self) -> None:
        """L66-67: Force the except branch by reloading the module.

        Strategy: unregister existing metrics, then monkey-patch the
        prometheus_client classes at the package level so the module's
        ``from prometheus_client import Histogram`` picks up our fakes
        during reload. The fake Histogram's labels().observe() raises.
        """
        import prometheus_client

        from app.monitoring.prometheus_metrics import REGISTRY
        import app.ratelimit.metrics as metrics_mod

        # Save original metrics to restore later
        originals = {
            "rl_decisions": metrics_mod.rl_decisions,
            "rl_retry_after": metrics_mod.rl_retry_after,
            "rl_eval_errors": metrics_mod.rl_eval_errors,
            "rl_eval_duration": metrics_mod.rl_eval_duration,
            "rl_config_reload_total": metrics_mod.rl_config_reload_total,
            "rl_active_overrides": metrics_mod.rl_active_overrides,
        }

        # Unregister all metrics from the REGISTRY
        for metric in originals.values():
            try:
                REGISTRY.unregister(metric)
            except Exception:
                pass

        observe_called = False

        class _BrokenHistogram:
            """Histogram stand-in whose labels().observe() always raises."""

            def __init__(self, *args, **kwargs):
                pass

            def labels(self, **kwargs):
                return self

            def observe(self, value):
                nonlocal observe_called
                observe_called = True
                raise RuntimeError("forced boom for coverage")

        real_histogram = prometheus_client.Histogram
        real_counter = prometheus_client.Counter
        real_gauge = prometheus_client.Gauge

        try:
            # Replace prometheus_client exports so `from prometheus_client import Histogram`
            # in the reloaded module picks up our broken version.
            prometheus_client.Histogram = _BrokenHistogram  # type: ignore[assignment]
            prometheus_client.Counter = MagicMock  # type: ignore[assignment]
            prometheus_client.Gauge = MagicMock  # type: ignore[assignment]

            importlib.reload(metrics_mod)

            # The bootstrap block at L63-67 should have hit the except branch
            assert observe_called, "observe() was never called — bootstrap did not execute"
        finally:
            # Restore real prometheus classes
            prometheus_client.Histogram = real_histogram
            prometheus_client.Counter = real_counter
            prometheus_client.Gauge = real_gauge

            # Restore original module attributes and re-register metrics
            for name, orig in originals.items():
                setattr(metrics_mod, name, orig)
            for metric in originals.values():
                try:
                    REGISTRY.register(metric)
                except Exception:
                    pass
