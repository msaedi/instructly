#!/usr/bin/env python3
"""
Quick test script for GeolocationService integration.

This script tests the GeolocationService with real API calls
to ensure it works correctly in the production environment.
"""

import asyncio
import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.services.cache_service import CacheService
from app.services.geolocation_service import GeolocationService


async def test_geolocation_service():
    """Test GeolocationService with real IPs."""
    print("🌍 Testing GeolocationService...")

    # Create database session
    db = SessionLocal()

    try:
        # Create cache service (optional)
        cache_service = CacheService(db)

        # Create geolocation service
        geo_service = GeolocationService(db, cache_service)

        # Test IPs (using public DNS servers)
        test_ips = [
            "8.8.8.8",  # Google DNS (California)
            "1.1.1.1",  # Cloudflare DNS
            "192.168.1.1",  # Private IP (should return default)
            "invalid-ip",  # Invalid IP (should return None)
        ]

        print("\n📍 Testing IP geolocation lookups:")

        for ip in test_ips:
            print(f"\nTesting IP: {ip}")

            try:
                result = await geo_service.get_location_from_ip(ip)

                if result:
                    print(f"  ✅ Location found:")
                    print(f"     Country: {result.get('country_name', 'Unknown')}")
                    print(f"     State: {result.get('state', 'Unknown')}")
                    print(f"     City: {result.get('city', 'Unknown')}")
                    if result.get("is_nyc"):
                        print(f"     Borough: {result.get('borough', 'Unknown')}")
                    print(f"     Is NYC: {result.get('is_nyc', False)}")
                else:
                    print(f"  ❌ No location data returned")

            except Exception as e:
                print(f"  ⚠️  Error: {str(e)}")

        # Test request IP extraction
        print("\n🔍 Testing request IP extraction:")

        class MockRequest:
            def __init__(self, headers, client_host=None):
                self.headers = headers
                if client_host:
                    self.client = type("Client", (), {"host": client_host})()
                else:
                    self.client = None

        test_requests = [
            (MockRequest({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}), "1.2.3.4"),
            (MockRequest({"X-Real-IP": "9.10.11.12"}), "9.10.11.12"),
            (MockRequest({"CF-Connecting-IP": "13.14.15.16"}), "13.14.15.16"),
            (MockRequest({}, "17.18.19.20"), "17.18.19.20"),
            (MockRequest({}), "127.0.0.1"),
        ]

        for i, (request, expected) in enumerate(test_requests):
            extracted_ip = geo_service.get_ip_from_request(request)
            status = "✅" if extracted_ip == expected else "❌"
            print(f"  {status} Test {i+1}: Expected {expected}, got {extracted_ip}")

        # Test NYC detection
        print("\n🗽 Testing NYC borough detection:")

        nyc_test_data = [
            {"city": "New York", "state": "New York"},  # Should be Manhattan
            {"city": "Brooklyn", "state": "NY"},  # Should be Brooklyn
            {"city": "Queens", "state": "New York"},  # Should be Queens
            {"city": "Los Angeles", "state": "California"},  # Should not be NYC
        ]

        for data in nyc_test_data:
            enhanced = geo_service._enhance_nyc_data(data.copy())
            city = data["city"]
            is_nyc = enhanced.get("is_nyc", False)
            borough = enhanced.get("borough", "N/A")
            print(f"  {city}: NYC={is_nyc}, Borough={borough}")

        await geo_service.close()
        print("\n✅ GeolocationService testing completed successfully!")

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_geolocation_service())
