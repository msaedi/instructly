# backend/scripts/debug_routes.py
"""
Debug script to find the correct route prefixes in your FastAPI app.
This will help fix the 404 errors in the tests.

Run this script to see all registered routes and their paths:
    cd backend
    python scripts/debug_routes.py
"""

import os
import sys

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app


def list_all_routes():
    """List all routes registered in the FastAPI app."""
    print("=== All Registered Routes ===\n")

    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            for method in route.methods:
                routes.append(
                    {"path": route.path, "method": method, "name": route.name if hasattr(route, "name") else "N/A"}
                )

    # Sort routes by path for easier reading
    routes.sort(key=lambda x: (x["path"], x["method"]))

    # Group by path prefix
    current_prefix = None
    for route in routes:
        path = route["path"]
        # Extract prefix (first part of path)
        prefix = "/" + path.split("/")[1] if len(path.split("/")) > 1 else "/"

        if prefix != current_prefix:
            current_prefix = prefix
            print(f"\n--- Routes under {prefix} ---")

        print(f"{route['method']:6} {route['path']:50} [{route['name']}]")

    # Show specific examples for our routes
    print("\n\n=== Route Prefixes You Need ===")

    booking_routes = [r for r in routes if "booking" in r["path"].lower()]
    availability_routes = [r for r in routes if "availability" in r["path"].lower()]

    if booking_routes:
        print(f"\nBooking routes prefix: {booking_routes[0]['path'].rsplit('/', 1)[0]}")
        print(f"Example: {booking_routes[0]['path']}")

    if availability_routes:
        print(f"\nAvailability routes prefix: {availability_routes[0]['path'].rsplit('/', 1)[0]}")
        print(f"Example: {availability_routes[0]['path']}")

    print("\n\n=== How to Fix the Tests ===")
    print("1. Look at the prefixes above")
    print("2. Update the test file paths to match")
    print("3. For example, if you see '/api/v1/bookings', update:")
    print('   FROM: client.post("/bookings", ...)')
    print('   TO:   client.post("/api/v1/bookings", ...)')
    print("\n4. IMPORTANT: Check if routes have trailing slashes!")
    print("   If the route shows '/bookings/' (with slash), you must include it")
    print('   FROM: client.post("/bookings", ...)')
    print('   TO:   client.post("/bookings/", ...)')

    # Check for trailing slash patterns
    print("\n\n=== Trailing Slash Analysis ===")
    post_routes = [r for r in routes if r["method"] == "POST"]
    with_slash = [r for r in post_routes if r["path"].endswith("/")]
    without_slash = [r for r in post_routes if not r["path"].endswith("/") and "/" in r["path"]]

    if with_slash:
        print("\nPOST routes WITH trailing slashes:")
        for route in with_slash[:5]:  # Show first 5
            print(f"  {route['path']}")

    if without_slash:
        print("\nPOST routes WITHOUT trailing slashes:")
        for route in without_slash[:5]:  # Show first 5
            print(f"  {route['path']}")


if __name__ == "__main__":
    list_all_routes()
