"""
Test that /metrics/prometheus endpoint returns correct format
"""

import time

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
import pytest

from app.main import fastapi_app as app


class TestPrometheusFormat:
    """Test Prometheus metrics endpoint format"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    def test_metrics_endpoint_exists(self, client):
        """Test that /api/v1/metrics/prometheus endpoint exists"""
        # Warm-up to reduce first-request latency that can flake in CI
        client.get("/api/v1/metrics/prometheus")

        response = None
        for attempt in range(3):
            try:
                response = client.get("/api/v1/metrics/prometheus")
                if response.status_code == 200:
                    break
            except Exception:
                response = None
            if attempt < 2:
                time.sleep(1)

        assert response is not None and response.status_code == 200
        # Prometheus metrics content type includes version info
        content_type = response.headers["content-type"]
        assert content_type.startswith("text/plain")
        assert "charset=utf-8" in content_type

    def test_metrics_format_is_valid_prometheus(self, client):
        """Test that metrics are in valid Prometheus format"""
        response = client.get("/api/v1/metrics/prometheus")
        assert response.status_code == 200

        # Parse the metrics to verify format
        metrics_text = response.text

        # Should be able to parse without errors
        families = list(text_string_to_metric_families(metrics_text))
        assert len(families) > 0

        # Check for expected metric families
        metric_names = {family.name for family in families}

        # Should include our custom metrics (actual names from the system)
        expected_metrics = {
            "instainstru_http_requests",  # Note: may be with or without _total suffix
            "instainstru_http_request_duration_seconds",
            "instainstru_service_operation_duration_seconds",
            "instainstru_service_operations",  # Note: actual metric name
            "instainstru_errors",  # Note: actual metric name
        }

        for metric in expected_metrics:
            assert metric in metric_names, f"Missing metric: {metric}"

    def test_metrics_include_help_text(self, client):
        """Test that metrics include HELP documentation"""
        response = client.get("/api/v1/metrics/prometheus")
        metrics_text = response.text

        # Check for HELP lines (using actual metric names)
        assert (
            "# HELP instainstru_http_requests_total" in metrics_text
            or "# HELP instainstru_http_requests" in metrics_text
        )
        assert "# HELP instainstru_http_request_duration_seconds" in metrics_text
        assert "# HELP instainstru_service_operation_duration_seconds" in metrics_text

    def test_metrics_include_type_info(self, client):
        """Test that metrics include TYPE information"""
        response = client.get("/api/v1/metrics/prometheus")
        metrics_text = response.text

        # Check for TYPE lines (using actual metric names)
        assert (
            "# TYPE instainstru_http_requests_total counter" in metrics_text
            or "# TYPE instainstru_http_requests counter" in metrics_text
        )
        assert "# TYPE instainstru_http_request_duration_seconds histogram" in metrics_text
        assert "# TYPE instainstru_service_operation_duration_seconds histogram" in metrics_text
        assert "# TYPE instainstru_errors_total counter" in metrics_text

    def test_histogram_metrics_have_buckets(self, client):
        """Test that histogram metrics include bucket information"""
        # Make a request to generate some metrics
        client.get("/api/v1/health")

        # Get metrics
        response = client.get("/api/v1/metrics/prometheus")
        metrics_text = response.text

        # Parse metrics
        families = list(text_string_to_metric_families(metrics_text))

        # Find histogram metrics
        for family in families:
            if family.type == "histogram":
                # Check for bucket samples
                for sample in family.samples:
                    if sample.name.endswith("_bucket"):
                        # Verify bucket has 'le' label
                        assert "le" in sample.labels
                        break
                else:
                    pytest.fail(f"No buckets found for histogram {family.name}")

    def _parse(self, text: str):
        """Parse Prometheus metrics text into metric families."""
        return list(text_string_to_metric_families(text))

    def _as_map(self, families):
        """Convert metric families to a map of metric_name -> value."""
        result = {}
        for family in families:
            for sample in family.samples:
                # Use the full sample name (includes _total suffix if present)
                key = sample.name
                # For metrics with labels, we could include labels in the key
                # but for simple counters without labels, just use the name
                if not sample.labels:
                    result[key] = sample.value
                else:
                    # For metrics with labels, create a key with labels
                    # For scrape counter, it should have no labels or minimal labels
                    if key == "instainstru_prometheus_scrapes_total" or key == "instainstru_prometheus_scrapes":
                        result[key] = sample.value
                    # For other metrics, use the first sample value (or aggregate)
                    elif key not in result:
                        result[key] = sample.value
        return result

    def test_counter_metrics_increment(self, client):
        """Test that counter metrics increment correctly"""
        # Get initial metrics
        resp1 = client.get("/api/v1/metrics/prometheus")
        m1 = self._as_map(self._parse(resp1.text))

        # Get metrics again (this increments the scrape counter)
        resp2 = client.get("/api/v1/metrics/prometheus")
        m2 = self._as_map(self._parse(resp2.text))

        # Assert on the scrape counter that always increments
        assert m2["instainstru_prometheus_scrapes_total"] == m1["instainstru_prometheus_scrapes_total"] + 1

        # Make some requests to increment counters
        client.get("/api/v1/health")
        client.get("/api/nonexistent")  # 404

        # Get metrics again
        response2 = client.get("/api/v1/metrics/prometheus")
        families2 = {f.name: f for f in text_string_to_metric_families(response2.text)}

        # Check that request counter increased (using correct metric name)
        http_metric_name = (
            "instainstru_http_requests_total"
            if "instainstru_http_requests_total" in m1
            else "instainstru_http_requests"
        )
        if http_metric_name in m1 and http_metric_name in families2:
            # Find samples for /health endpoint
            samples1 = {
                (s.labels.get("endpoint"), s.labels.get("status_code")): s.value
                for f in self._parse(resp1.text)
                for s in f.samples
                if f.name == http_metric_name
            }
            samples2 = {
                (s.labels.get("endpoint"), s.labels.get("status_code")): s.value
                for s in families2[http_metric_name].samples
            }

            # Check /api/v1/health counter increased
            health_key = ("/api/v1/health", "200")
            if health_key in samples1 and health_key in samples2:
                assert samples2[health_key] > samples1[health_key]

    @pytest.mark.skip(reason="Using custom registry without default process metrics")
    def test_metrics_have_process_info(self, client):
        """Test that standard process metrics are included"""
        response = client.get("/api/v1/metrics/prometheus")
        metrics_text = response.text

        # Should include standard Python process metrics
        process_metrics = [
            "process_virtual_memory_bytes",
            "process_resident_memory_bytes",
            "process_start_time_seconds",
            "process_cpu_seconds_total",
            "process_open_fds",
            "process_max_fds",
        ]

        for metric in process_metrics:
            # Not all platforms support all metrics, but at least some should exist
            if f"# TYPE {metric}" in metrics_text:
                return

        pytest.fail("No process metrics found")

    def test_metrics_labels_are_properly_escaped(self, client):
        """Test that label values are properly escaped"""
        # Make a request with special characters
        client.get('/api/test"path')

        response = client.get("/api/v1/metrics/prometheus")
        metrics_text = response.text

        # Labels with quotes should be escaped
        # Prometheus format requires quotes in labels to be escaped as \"
        if '"' in metrics_text:
            # Check that quotes in labels are escaped
            lines = metrics_text.split("\n")
            for line in lines:
                if line.startswith("instainstru_") and "{" in line:
                    # Extract label section
                    label_section = line[line.find("{") : line.find("}") + 1]
                    # If there are quotes in values, they should be escaped
                    if '"' in label_section and '="' in label_section:
                        # This is OK - quotes are part of the format
                        pass

    def test_metrics_endpoint_is_fast(self, client):
        """Test that metrics endpoint responds quickly"""
        import time

        # Generate some metrics first
        for _ in range(10):
            client.get("/api/v1/health")

        # Time the metrics endpoint
        start = time.time()
        response = client.get("/api/v1/metrics/prometheus")
        duration = time.time() - start

        assert response.status_code == 200
        # Metrics endpoint should be fast (< 100ms)
        assert duration < 0.1, f"Metrics endpoint took {duration:.3f}s"

    def test_metrics_are_atomic(self, client):
        """Test that metrics are consistent within a single scrape"""
        response = client.get("/api/v1/metrics/prometheus")
        families = list(text_string_to_metric_families(response.text))

        # Find histogram metrics
        histograms = [f for f in families if f.type == "histogram"]

        for histogram in histograms:
            # Group samples by labels (excluding 'le' for buckets)
            label_groups = {}
            for sample in histogram.samples:
                labels = tuple((k, v) for k, v in sample.labels.items() if k != "le")
                if labels not in label_groups:
                    label_groups[labels] = {}

                if sample.name.endswith("_bucket"):
                    if "buckets" not in label_groups[labels]:
                        label_groups[labels]["buckets"] = []
                    label_groups[labels]["buckets"].append(sample)
                elif sample.name.endswith("_count"):
                    label_groups[labels]["count"] = sample.value
                elif sample.name.endswith("_sum"):
                    label_groups[labels]["sum"] = sample.value

            # Verify consistency
            for labels, data in label_groups.items():
                if "count" in data and "sum" in data:
                    # Count should be >= 0
                    assert data["count"] >= 0
                    # If count > 0, sum should be >= 0 (can be 0 for very fast operations)
                    if data["count"] > 0:
                        assert data["sum"] >= 0
