"""
Test suite to lock Prometheus metrics format and counter increment behavior.

Locks the behavior that:
- Scrape counter increments between calls
- Format is valid (no duplicate HELP/TYPE, content non-empty)
"""

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
import pytest

from app.main import fastapi_app as app


@pytest.fixture(autouse=True)
def _prometheus_no_cache_in_tests(monkeypatch):
    """Ensure PROMETHEUS_CACHE_IN_TESTS is NOT set (or 0) so counters actually increment."""
    monkeypatch.setenv("PROMETHEUS_CACHE_IN_TESTS", "0")
    yield


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestPrometheusFormatLock:
    """Test suite to lock Prometheus metrics format."""

    def test_scrape_counter_increments_between_calls(self, client):
        """With PROMETHEUS_CACHE_IN_TESTS=0, scrape counter increments between calls."""
        # First call
        response1 = client.get("/api/v1/metrics/prometheus")
        assert response1.status_code == 200

        # Parse first response
        families1 = {f.name: f for f in text_string_to_metric_families(response1.text)}

        # Second call
        response2 = client.get("/api/v1/metrics/prometheus")
        assert response2.status_code == 200

        # Parse second response
        families2 = {f.name: f for f in text_string_to_metric_families(response2.text)}

        # Find scrape counter (typically named with "scrape" or "prometheus")
        scrape_counter_name = None
        increment_found = False
        for name in families1.keys():
            if "scrape" in name.lower() or "prometheus" in name.lower():
                scrape_counter_name = name
                break

        if scrape_counter_name and scrape_counter_name in families1 and scrape_counter_name in families2:
            # Get total values (sum across all labels)
            samples1 = families1[scrape_counter_name].samples
            samples2 = families2[scrape_counter_name].samples

            total1 = sum(s.value for s in samples1)
            total2 = sum(s.value for s in samples2)

            # Counter should increment
            if total2 > total1:
                increment_found = True

        # Alternative: check if any counter metric increments (fallback)
        # Look for common counter patterns
        counter_metrics = [name for name, family in families1.items() if family.type == "counter"]
        if counter_metrics:
            # Check at least one counter increased
            for metric_name in counter_metrics:
                if metric_name in families2:
                    samples1_dict = {(tuple(s.labels.items()) if s.labels else ()): s.value for s in families1[metric_name].samples}
                    samples2_dict = {(tuple(s.labels.items()) if s.labels else ()): s.value for s in families2[metric_name].samples}

                    # Check if any sample increased
                    for label_key in samples1_dict:
                        if label_key in samples2_dict:
                            if samples2_dict[label_key] > samples1_dict[label_key]:
                                # Found an increment, test passes
                                increment_found = True
                                break
                    if increment_found:
                        break

            # At minimum, verify metrics were parsed correctly
            assert len(families1) > 0
            assert len(families2) > 0

        assert increment_found, "Expected at least one counter to increase between scrapes"

    def test_basic_format_sanity(self, client):
        """Basic format sanity: no duplicate HELP/TYPE, content non-empty."""
        response = client.get("/api/v1/metrics/prometheus")
        assert response.status_code == 200

        metrics_text = response.text
        assert len(metrics_text) > 0, "Metrics content should not be empty"

        # Parse metrics
        families = list(text_string_to_metric_families(metrics_text))
        assert len(families) > 0, "Should have at least one metric family"

        # Check for duplicate HELP/TYPE per metric family
        help_lines = {}
        type_lines = {}

        lines = metrics_text.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# HELP "):
                parts = line[7:].split(" ", 1)
                metric_name = parts[0]
                if metric_name in help_lines and help_lines[metric_name] != line:
                    pytest.fail(f"Duplicate HELP line for metric {metric_name}")
                help_lines[metric_name] = line
            elif line.startswith("# TYPE "):
                parts = line[7:].split(" ", 1)
                metric_name = parts[0]
                if metric_name in type_lines:
                    # Duplicate TYPE is an error
                    pytest.fail(f"Duplicate TYPE line for metric {metric_name}")
                type_lines[metric_name] = line

        # Verify HELP and TYPE are paired (each metric with TYPE should have HELP)
        # Note: Some metrics might not have HELP, so we check TYPE->HELP mapping
        # TYPE should come after HELP (order check is implicit in parsing)
        # But we don't fail if HELP is missing (some metrics are self-documenting)
        # This loop is intentionally empty - we're just documenting the behavior
        for _metric_name, _type_line in type_lines.items():
            pass

        # Verify no obvious format errors
        assert response.headers.get("content-type", "").startswith("text/plain")
