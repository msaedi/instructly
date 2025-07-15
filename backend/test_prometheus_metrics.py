#!/usr/bin/env python3
"""
Test script to verify Prometheus metrics endpoint is working correctly.

Run this after starting the FastAPI server to see sample metrics output.
"""

import time

import requests


def test_prometheus_metrics():
    """Test the Prometheus metrics endpoint."""
    base_url = "http://localhost:8000"

    print("Testing Prometheus Metrics Integration\n")
    print("=" * 50)

    # Make some API calls to generate metrics
    print("1. Making test requests to generate metrics...")

    # Health check
    try:
        response = requests.get(f"{base_url}/health")
        print(f"   - Health check: {response.status_code}")
    except Exception as e:
        print(f"   - Health check failed: {e}")

    # Root endpoint
    try:
        response = requests.get(f"{base_url}/")
        print(f"   - Root endpoint: {response.status_code}")
    except Exception as e:
        print(f"   - Root endpoint failed: {e}")

    # Performance metrics (to trigger service operations)
    try:
        response = requests.get(f"{base_url}/metrics/performance")
        print(f"   - Performance metrics: {response.status_code}")
    except Exception as e:
        print(f"   - Performance metrics failed: {e}")

    # Wait a moment for metrics to be recorded
    time.sleep(0.5)

    # Now fetch Prometheus metrics
    print("\n2. Fetching Prometheus metrics...")
    try:
        response = requests.get(f"{base_url}/metrics/prometheus")
        print(f"   - Status: {response.status_code}")
        print(f"   - Content-Type: {response.headers.get('Content-Type')}")

        if response.status_code == 200:
            print("\n3. Prometheus Metrics Output:")
            print("-" * 50)
            metrics_text = response.text

            # Show first 1500 characters of metrics
            if len(metrics_text) > 1500:
                print(metrics_text[:1500])
                print(f"\n... (truncated, total {len(metrics_text)} characters)")
            else:
                print(metrics_text)

            # Check for expected metrics
            print("\n4. Checking for expected metrics:")
            expected_metrics = [
                "instainstru_http_request_duration_seconds",
                "instainstru_http_requests_total",
                "instainstru_http_requests_in_progress",
                "instainstru_service_operation_duration_seconds",
                "instainstru_service_operations_total",
            ]

            for metric in expected_metrics:
                if metric in metrics_text:
                    print(f"   ✓ Found: {metric}")
                else:
                    print(f"   ✗ Missing: {metric}")

        else:
            print(f"   - Error: {response.text}")

    except Exception as e:
        print(f"   - Failed to fetch metrics: {e}")

    print("\n" + "=" * 50)
    print("Test complete!")
    print("\nNote: To see service operation metrics, make some API calls that")
    print("trigger @measure_operation decorated methods (e.g., booking operations).")


if __name__ == "__main__":
    test_prometheus_metrics()
