from __future__ import annotations

import builtins
import importlib
from unittest.mock import Mock, patch

import pytest

from app.services import base as base_module
from app.services.base import BaseService


class TestBaseServiceAdditionalCoverage:
    def test_prometheus_import_error_path(self, monkeypatch) -> None:
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.endswith("monitoring.prometheus_metrics"):
                raise ImportError("missing")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        spec = importlib.util.spec_from_file_location(
            "app.services._base_prometheus_test", base_module.__file__
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.PROMETHEUS_AVAILABLE is False
        assert module.prometheus_metrics is None

        monkeypatch.setattr(builtins, "__import__", original_import)

    @pytest.mark.asyncio
    async def test_measure_operation_async_no_args(self) -> None:
        @BaseService.measure_operation("standalone_async")
        async def run() -> str:
            return "ok"

        assert await run() == "ok"

    @pytest.mark.asyncio
    async def test_measure_operation_async_logs_slow(self) -> None:
        class TestService(BaseService):
            @BaseService.measure_operation("async_op")
            async def async_op(self) -> str:
                return "done"

        service = TestService(Mock())

        with patch("app.services.base.time.time", side_effect=[0.0, 2.0]):
            with patch.object(service.logger, "warning") as mock_warning:
                assert await service.async_op() == "done"

        mock_warning.assert_called_once()

    def test_measure_operation_context_records_failure(self) -> None:
        service = BaseService(Mock())

        with pytest.raises(RuntimeError):
            with service.measure_operation_context("explode"):
                raise RuntimeError("boom")

        metrics = service.get_metrics()
        assert metrics["explode"]["failure_count"] == 1

    def test_measure_operation_context_prometheus_error(self, monkeypatch) -> None:
        service = BaseService(Mock())

        class FakePrometheus:
            def record_service_operation(self, **_kwargs) -> None:
                raise RuntimeError("metrics down")

        monkeypatch.setattr(base_module, "PROMETHEUS_AVAILABLE", True)
        monkeypatch.setattr(base_module, "prometheus_metrics", FakePrometheus())

        with patch.object(base_module.logger, "debug") as mock_debug:
            with service.measure_operation_context("with_metrics"):
                pass

        mock_debug.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_measure_operation_context_warning_and_metrics_error(self, monkeypatch) -> None:
        service = BaseService(Mock())

        class FakePrometheus:
            def record_service_operation(self, **_kwargs) -> None:
                raise RuntimeError("metrics down")

        monkeypatch.setattr(base_module, "PROMETHEUS_AVAILABLE", True)
        monkeypatch.setattr(base_module, "prometheus_metrics", FakePrometheus())

        with patch("app.services.base.time.time", side_effect=[0.0, 2.0]):
            with patch.object(base_module.logger, "debug") as mock_debug:
                with patch.object(service.logger, "warning") as mock_warning:
                    async with service.async_measure_operation_context("async_ctx"):
                        pass

        mock_warning.assert_called_once()
        mock_debug.assert_called_once()

    def test_get_metrics_skips_zero_count(self) -> None:
        service = base_module.BaseService(Mock())
        base_module.BaseService._class_metrics.clear()
        base_module.BaseService._class_metrics[service.__class__.__name__] = {
            "zero": {
                "count": 0,
                "total_time": 0.0,
                "success_count": 0,
                "failure_count": 0,
                "min_time": float("inf"),
                "max_time": 0.0,
            }
        }

        assert service.get_metrics() == {}

    def test_reset_metrics_clears_class_entry(self) -> None:
        service = base_module.BaseService(Mock())
        base_module.BaseService._class_metrics[service.__class__.__name__] = {
            "op": {
                "count": 1,
                "total_time": 0.1,
                "success_count": 1,
                "failure_count": 0,
                "min_time": 0.1,
                "max_time": 0.1,
            }
        }

        service.reset_metrics()

        assert service.get_metrics() == {}
