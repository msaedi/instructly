#!/usr/bin/env python3
"""
Quick test script for DeviceTrackingService integration.

This script tests the DeviceTrackingService with real user agent strings
to ensure it works correctly for common devices and browsers.
"""

import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.services.device_tracking_service import DeviceTrackingService


def test_device_tracking_service():
    """Test DeviceTrackingService with real user agent strings."""
    print("📱 Testing DeviceTrackingService...")

    # Create database session
    db = SessionLocal()

    try:
        # Create device tracking service
        device_service = DeviceTrackingService(db)

        # Real user agent strings from different devices
        test_user_agents = [
            {
                "name": "Chrome Desktop (Windows)",
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "expected_type": "desktop",
            },
            {
                "name": "Safari iPhone",
                "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
                "expected_type": "mobile",
            },
            {
                "name": "Safari iPad",
                "ua": "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
                "expected_type": "tablet",
            },
            {
                "name": "Chrome Android",
                "ua": "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
                "expected_type": "mobile",
            },
            {
                "name": "Firefox Desktop",
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
                "expected_type": "desktop",
            },
            {
                "name": "Edge Desktop",
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
                "expected_type": "desktop",
            },
            {"name": "Googlebot", "ua": "Googlebot/2.1 (+http://www.google.com/bot.html)", "expected_type": "desktop"},
        ]

        print("\n🔍 Testing user agent parsing:")

        all_contexts = []

        for test_case in test_user_agents:
            print(f"\n{test_case['name']}:")

            parsed = device_service.parse_user_agent(test_case["ua"])

            print(f"  Browser: {parsed['browser_name']} {parsed['browser_version']}")
            print(f"  OS: {parsed['os_family']} {parsed['os_version']}")
            print(f"  Device: {parsed['device_family']}")
            print(f"  Type: {parsed['device_type']} (expected: {test_case['expected_type']})")
            print(f"  Mobile: {parsed['is_mobile']}, Tablet: {parsed['is_tablet']}, Bot: {parsed['is_bot']}")

            # Verify expected device type
            status = "✅" if parsed["device_type"] == test_case["expected_type"] else "❌"
            print(f"  {status} Device type detection")

            all_contexts.append(parsed)

        # Test analytics formatting
        print(f"\n📊 Testing analytics formatting:")

        sample_context = all_contexts[0]  # Use Chrome desktop
        formatted = device_service.format_for_analytics(sample_context)

        print(f"  Device Type: {formatted['device_type']}")
        print(f"  Browser Info: {formatted['browser_info']['browser']['name']}")
        print(f"  OS Family: {formatted['browser_info']['os']['family']}")
        print(f"  Is Mobile: {formatted['browser_info']['device']['is_mobile']}")

        # Test analytics summary
        print(f"\n📈 Testing analytics summary:")

        summary = device_service.get_analytics_summary(all_contexts)

        print(f"  Total Sessions: {summary['total_sessions']}")
        print(f"  Device Types:")
        for device_type, stats in summary["device_types"].items():
            print(f"    {device_type}: {stats['count']} ({stats['percentage']}%)")

        print(f"  Top Browsers:")
        for browser, stats in list(summary["top_browsers"].items())[:3]:
            print(f"    {browser}: {stats['count']} ({stats['percentage']}%)")

        # Test Client Hints extraction
        print(f"\n💡 Testing Client Hints extraction:")

        class MockRequest:
            def __init__(self, headers):
                self.headers = headers

        # Mock modern browser with client hints
        mock_request = MockRequest(
            {
                "User-Agent": test_user_agents[0]["ua"],
                "Device-Memory": "8",
                "Viewport-Width": "1920",
                "ECT": "4g",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-CH-UA-Mobile": "?0",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        full_context = device_service.get_device_context_from_request(mock_request)

        print(f"  Device Type: {full_context['device_type']}")
        print(f"  Connection: {full_context.get('connection_type', 'unknown')}")
        print(f"  Language: {full_context.get('accept_language', 'unknown')}")
        if "client_hints" in full_context:
            hints = full_context["client_hints"]
            print(f"  Memory: {hints.get('device_memory', 'unknown')} GB")
            print(f"  Viewport: {hints.get('viewport_width', 'unknown')}px")

        # Test connection type detection
        print(f"\n🌐 Testing connection type detection:")

        connection_tests = [
            ({"ECT": "4g"}, "4g"),
            ({"Downlink": "0.5"}, "2g"),
            ({"User-Agent": "Mobile 3G Browser"}, "3g"),
            ({}, None),
        ]

        for headers, expected in connection_tests:
            mock_req = MockRequest(headers)
            conn_type = device_service.get_connection_type(mock_req)
            status = "✅" if conn_type == expected else "❌"
            print(f"  {status} {headers} → {conn_type}")

        print("\n✅ DeviceTrackingService testing completed successfully!")

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_device_tracking_service()
