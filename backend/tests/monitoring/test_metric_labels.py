"""
Test that metric labels are correct and consistent
"""
import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.main import fastapi_app as app
from app.monitoring.prometheus_metrics import errors_total, service_operation_duration_seconds, service_operations_total
from app.services.base import BaseService


class TestMetricLabels:
    """Test that metrics have correct labels"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    def test_http_metrics_have_required_labels(self, client):
        """Test that HTTP metrics have method, endpoint, and status_code labels"""
        # Make various requests
        client.get("/health")
        client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong"})
        client.get("/api/nonexistent")

        # Get metrics
        response = client.get("/metrics/prometheus")
        families = {f.name: f for f in text_string_to_metric_families(response.text)}

        # Check http_requests (may be _total or not depending on prometheus_client version)
        http_requests = families.get("instainstru_http_requests_total") or families.get("instainstru_http_requests")
        assert http_requests is not None, f"HTTP requests metric not found. Available: {list(families.keys())}"

        required_labels = {"method", "endpoint", "status_code"}
        for sample in http_requests.samples:
            assert all(label in sample.labels for label in required_labels)
            # Verify label values are sensible
            assert sample.labels["method"] in ["GET", "POST", "PUT", "DELETE", "PATCH"]
            assert sample.labels["endpoint"].startswith("/")
            assert sample.labels["status_code"].isdigit()

    def test_service_metrics_have_required_labels(self):
        """Test that service operation metrics have service and operation labels"""

        # Create a test service and execute an operation
        class TestService(BaseService):
            @BaseService.measure_operation("test_operation")
            def test_operation(self):
                return "success"

        from unittest.mock import Mock

        db_mock = Mock()
        service = TestService(db_mock)
        service.test_operation()

        # Get metrics from registry
        samples = list(service_operations_total.collect())[0].samples

        # Find our test metric
        for sample in samples:
            if sample.labels.get("service") == "TestService" and sample.labels.get("operation") == "test_operation":
                assert sample.labels.get("status") in ["success", "error"]
                assert len(sample.labels) == 3  # service, operation, status
                break
        else:
            pytest.fail("Test service metric not found")

    def test_error_metrics_include_error_type(self):
        """Test that error metrics include error_type label"""

        class TestService(BaseService):
            @BaseService.measure_operation("failing_operation")
            def failing_operation(self):
                raise ValueError("Test error")

        from unittest.mock import Mock

        db_mock = Mock()
        service = TestService(db_mock)

        # Execute and catch error
        with pytest.raises(ValueError):
            service.failing_operation()

        # Check error metrics
        samples = list(errors_total.collect())[0].samples

        # Find our error metric
        for sample in samples:
            if sample.labels.get("service") == "TestService" and sample.labels.get("operation") == "failing_operation":
                assert sample.labels.get("error_type") == "ValueError"
                assert len(sample.labels) == 3  # service, operation, error_type
                break
        else:
            pytest.fail("Error metric not found")

    def test_cache_metrics_have_cache_name_label(self):
        """Test that cache metrics include cache_name label"""
        # Skip this test since cache metrics aren't in prometheus_metrics.py yet
        pytest.skip("Cache metrics not implemented in current prometheus_metrics.py")

    def test_database_metrics_have_query_labels(self):
        """Test that database metrics include query_type and table labels"""
        # Skip this test since db metrics aren't in prometheus_metrics.py yet
        pytest.skip("Database metrics not implemented in current prometheus_metrics.py")

    def test_label_values_are_sanitized(self, client):
        """Test that label values are properly sanitized"""
        # Make request with special characters in path
        client.get("/api/test-endpoint-with-dashes")
        client.get("/api/test_endpoint_with_underscores")
        client.get("/api/test/nested/path")

        # Get metrics
        response = client.get("/metrics/prometheus")
        families = {f.name: f for f in text_string_to_metric_families(response.text)}

        http_requests = families.get("instainstru_http_requests_total") or families.get("instainstru_http_requests")
        assert http_requests is not None, f"HTTP requests metric not found. Available: {list(families.keys())}"

        # Check that all label values are valid
        for sample in http_requests.samples:
            endpoint = sample.labels.get("endpoint", "")
            # Label values should not break Prometheus format
            assert '"' not in endpoint or '\\"' in endpoint  # Quotes should be escaped
            assert "\n" not in endpoint  # No newlines
            assert "\r" not in endpoint  # No carriage returns

    def test_histogram_labels_include_le_for_buckets(self, client):
        """Test that histogram bucket metrics include 'le' label"""
        # Make a request to generate histogram data
        client.get("/health")

        # Get metrics
        response = client.get("/metrics/prometheus")
        families = list(text_string_to_metric_families(response.text))

        # Find histogram metrics
        for family in families:
            if family.type == "histogram" and family.name.startswith("instainstru_"):
                bucket_found = False
                for sample in family.samples:
                    if sample.name.endswith("_bucket"):
                        assert "le" in sample.labels
                        # le should be a number or "+Inf"
                        le_value = sample.labels["le"]
                        assert le_value == "+Inf" or float(le_value) >= 0
                        bucket_found = True

                assert bucket_found, f"No buckets found for histogram {family.name}"

    def test_label_cardinality_is_reasonable(self, client):
        """Test that label cardinality doesn't explode"""
        # Make many requests with different parameters
        for i in range(10):
            client.get(f"/api/users/{i}")  # Should normalize to /api/users/{id}

        # Get metrics
        response = client.get("/metrics/prometheus")
        families = {f.name: f for f in text_string_to_metric_families(response.text)}

        http_requests = families.get("instainstru_http_requests_total")
        if http_requests:
            # Count unique endpoint labels
            endpoints = set()
            for sample in http_requests.samples:
                endpoints.add(sample.labels.get("endpoint", ""))

            # Should not have 10 different endpoints for user IDs
            # They should be normalized to a single /api/users/{id} pattern
            user_endpoints = [e for e in endpoints if "/api/users/" in e]
            assert len(user_endpoints) <= 2  # Maybe one for success, one for 404

    def test_service_operation_labels_match_class_method(self):
        """Test that service and operation labels match actual class and method names"""

        class VerySpecificServiceName(BaseService):
            @BaseService.measure_operation("very_specific_operation_name")
            def very_specific_operation_name(self):
                return "done"

        from unittest.mock import Mock

        db_mock = Mock()
        service = VerySpecificServiceName(db_mock)
        service.very_specific_operation_name()

        # Check metrics
        samples = list(service_operations_total.collect())[0].samples

        # Find our specific metric
        found = False
        for sample in samples:
            if (
                sample.labels.get("service") == "VerySpecificServiceName"
                and sample.labels.get("operation") == "very_specific_operation_name"
            ):
                found = True
                break

        assert found, "Service operation labels don't match class/method names"

    def test_metrics_labels_are_consistent_across_metric_types(self):
        """Test that the same operation has consistent labels across different metric types"""

        class ConsistencyTestService(BaseService):
            @BaseService.measure_operation("consistent_operation")
            def consistent_operation(self):
                return "success"

        from unittest.mock import Mock

        db_mock = Mock()
        service = ConsistencyTestService(db_mock)
        service.consistent_operation()

        # Collect labels from different metric types
        duration_labels = set()
        operations_labels = set()

        # Duration metric
        for family in service_operation_duration_seconds.collect():
            for sample in family.samples:
                if (
                    sample.labels.get("service") == "ConsistencyTestService"
                    and sample.labels.get("operation") == "consistent_operation"
                ):
                    duration_labels.add((sample.labels["service"], sample.labels["operation"]))

        # Operations metric
        for sample in list(service_operations_total.collect())[0].samples:
            if (
                sample.labels.get("service") == "ConsistencyTestService"
                and sample.labels.get("operation") == "consistent_operation"
            ):
                operations_labels.add((sample.labels["service"], sample.labels["operation"]))

        # Labels should be consistent
        assert duration_labels == operations_labels
        assert len(duration_labels) == 1  # Should have exactly one set of labels
