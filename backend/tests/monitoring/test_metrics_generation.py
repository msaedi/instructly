"""
Test that @measure_operation decorator creates metrics correctly
"""
import time
from unittest.mock import Mock, patch

import pytest
from prometheus_client import REGISTRY

from app.monitoring.prometheus_metrics import errors_total, service_operation_duration_seconds, service_operations_total
from app.services.base import BaseService


class TestMetricsGeneration:
    """Test metrics generation from @measure_operation decorator"""

    @pytest.fixture(autouse=True)
    def clear_metrics(self):
        """Clear metrics before each test"""
        # Store current metrics
        list(REGISTRY._collector_to_names.keys())

        yield

        # Don't actually unregister in tests as it affects global state
        # In real monitoring, metrics persist across requests

    def test_measure_operation_creates_success_metric(self):
        """Test that successful operations create success metrics"""

        class TestService(BaseService):
            @BaseService.measure_operation("successful_operation")
            def successful_operation(self):
                return "success"

        # Create service instance
        db_mock = Mock()
        service = TestService(db_mock)

        # Execute operation
        result = service.successful_operation()

        # Verify result
        assert result == "success"

        # Verify metrics were created
        # Check that the metric exists and has the correct labels
        samples = list(service_operations_total.collect())[0].samples

        # Find our specific metric
        found = False
        for sample in samples:
            if (
                sample.labels.get("service") == "TestService"
                and sample.labels.get("operation") == "successful_operation"
                and sample.labels.get("status") == "success"
            ):
                found = True
                assert sample.value >= 1  # At least one success
                break

        assert found, "Success metric not found"

    def test_measure_operation_creates_error_metric(self):
        """Test that failed operations create error metrics"""

        class TestService(BaseService):
            @BaseService.measure_operation("failing_operation")
            def failing_operation(self):
                raise ValueError("Test error")

        # Create service instance
        db_mock = Mock()
        service = TestService(db_mock)

        # Execute operation and expect error
        with pytest.raises(ValueError):
            service.failing_operation()

        # Verify error metrics were created
        samples = list(errors_total.collect())[0].samples

        # Find our specific metric
        found = False
        for sample in samples:
            if (
                sample.labels.get("service") == "TestService"
                and sample.labels.get("operation") == "failing_operation"
                and sample.labels.get("error_type") == "ValueError"
            ):
                found = True
                assert sample.value >= 1  # At least one error
                break

        assert found, "Error metric not found"

    def test_measure_operation_tracks_duration(self):
        """Test that operation duration is tracked"""

        class TestService(BaseService):
            @BaseService.measure_operation("slow_operation")
            def slow_operation(self):
                time.sleep(0.1)  # 100ms delay
                return "done"

        # Create service instance
        db_mock = Mock()
        service = TestService(db_mock)

        # Execute operation
        start_time = time.time()
        result = service.slow_operation()
        duration = time.time() - start_time

        assert result == "done"
        assert duration >= 0.1  # Should take at least 100ms

        # Verify duration metric exists
        # Note: Histograms have multiple series (_bucket, _count, _sum)
        samples = []
        for collector in service_operation_duration_seconds.collect():
            samples.extend(collector.samples)

        # Check _sum metric (total time)
        sum_found = False
        for sample in samples:
            if (
                sample.name == "instainstru_service_operation_duration_seconds_sum"
                and sample.labels.get("service") == "TestService"
                and sample.labels.get("operation") == "slow_operation"
            ):
                sum_found = True
                assert sample.value >= 0.1  # Total time should be at least 100ms
                break

        assert sum_found, "Duration sum metric not found"

        # Check _count metric (number of observations)
        count_found = False
        for sample in samples:
            if (
                sample.name == "instainstru_service_operation_duration_seconds_count"
                and sample.labels.get("service") == "TestService"
                and sample.labels.get("operation") == "slow_operation"
            ):
                count_found = True
                assert sample.value >= 1  # At least one observation
                break

        assert count_found, "Duration count metric not found"

    def test_measure_operation_with_async_method(self):
        """Test that async operations are measured correctly"""

        class TestService(BaseService):
            @BaseService.measure_operation("async_operation")
            async def async_operation(self):
                # Simulate async work
                await asyncio.sleep(0.05)
                return "async done"

        # Create service instance
        db_mock = Mock()
        service = TestService(db_mock)

        # Execute async operation
        import asyncio

        result = asyncio.run(service.async_operation())

        assert result == "async done"

        # Verify metrics were created
        samples = list(service_operations_total.collect())[0].samples

        found = False
        for sample in samples:
            if (
                sample.labels.get("service") == "TestService"
                and sample.labels.get("operation") == "async_operation"
                and sample.labels.get("status") == "success"
            ):
                found = True
                assert sample.value >= 1
                break

        assert found, "Async operation metric not found"

    def test_multiple_services_have_separate_metrics(self):
        """Test that different services have separate metric labels"""

        class ServiceA(BaseService):
            @BaseService.measure_operation("operation")
            def operation(self):
                return "A"

        class ServiceB(BaseService):
            @BaseService.measure_operation("operation")
            def operation(self):
                return "B"

        # Create service instances
        db_mock = Mock()
        service_a = ServiceA(db_mock)
        service_b = ServiceB(db_mock)

        # Execute operations
        result_a = service_a.operation()
        result_b = service_b.operation()

        assert result_a == "A"
        assert result_b == "B"

        # Verify both services have metrics
        samples = list(service_operations_total.collect())[0].samples

        service_a_found = False
        service_b_found = False

        for sample in samples:
            if sample.labels.get("service") == "ServiceA" and sample.labels.get("operation") == "operation":
                service_a_found = True
            elif sample.labels.get("service") == "ServiceB" and sample.labels.get("operation") == "operation":
                service_b_found = True

        assert service_a_found, "ServiceA metric not found"
        assert service_b_found, "ServiceB metric not found"

    def test_decorator_preserves_function_metadata(self):
        """Test that @measure_operation preserves function name and docstring"""

        class TestService(BaseService):
            @BaseService.measure_operation("documented_operation")
            def documented_operation(self, x: int, y: int) -> int:
                """This operation adds two numbers"""
                return x + y

        # Check metadata is preserved
        assert TestService.documented_operation.__name__ == "documented_operation"
        assert TestService.documented_operation.__doc__ == "This operation adds two numbers"

        # Check operation still works
        db_mock = Mock()
        service = TestService(db_mock)
        result = service.documented_operation(2, 3)
        assert result == 5

    def test_decorator_preserves_logging_functionality(self):
        """Test that decorator doesn't break logging and handles slow operations"""

        class TestService(BaseService):
            @BaseService.measure_operation("slow_logged_operation")
            def slow_logged_operation(self):
                # Simulate slow operation to trigger warning
                import time

                time.sleep(1.1)  # Over 1 second threshold
                return "logged"

        # Create service instance with real logger to test logging
        db_mock = Mock()
        service = TestService(db_mock)

        # Mock the logger to verify calls
        with patch.object(service, "logger") as mock_logger:
            # Execute operation
            result = service.slow_logged_operation()

            assert result == "logged"

            # Verify slow operation warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "slow_logged_operation took" in call_args
            assert "1." in call_args  # Should contain duration around 1.1s
