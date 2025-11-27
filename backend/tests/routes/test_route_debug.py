# backend/tests/routes/test_route_debug.py
"""
Debug test to check if public routes are properly registered
"""

import pytest


def test_list_all_registered_routes():
    """List all routes to debug registration issues."""
    from app.main import fastapi_app as app

    print("\n" + "=" * 60)
    print("ALL REGISTERED ROUTES:")
    print("=" * 60)

    routes_found = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            path = route.path
            methods = route.methods
            routes_found.append((methods, path))
            print(f"{methods} {path}")

    print("=" * 60)

    # Check for public routes
    public_routes = [r for r in routes_found if "/public" in r[1]]

    if public_routes:
        print(f"\n✅ Found {len(public_routes)} public routes:")
        for methods, path in public_routes:
            print(f"  {methods} {path}")
    else:
        print("\n❌ No public routes found!")

    # Also check imports
    print("\n" + "=" * 60)
    print("CHECKING IMPORTS:")
    print("=" * 60)

    try:
        from app.routes import public

        print("✅ app.routes.public imports successfully")
        print(f"   Router prefix: {public.router.prefix}")
        print(f"   Router tags: {public.router.tags}")
    except ImportError as e:
        print(f"❌ Failed to import public routes: {e}")

    assert len(public_routes) > 0, "No public routes found in app!"


def test_public_route_specific_check(client):
    """Test accessing the specific public route."""
    # List all routes first for debugging
    from app.main import fastapi_app as app

    print("\nChecking for availability route specifically:")
    for route in app.routes:
        if hasattr(route, "path"):
            if "availability" in route.path and "public" in route.path:
                print(f"Found: {route.methods} {route.path}")

    # Try different URL patterns
    test_urls = [
        "/api/v1/public/instructors/01J5TESTINSTR0000000000001/availability?start_date=2025-07-15",
        "/public/instructors/01J5TESTINSTR0000000000001/availability?start_date=2025-07-15",
        "/instructors/01J5TESTINSTR0000000000001/availability?start_date=2025-07-15",
    ]

    for url in test_urls:
        response = client.get(url)
        print(f"\nTesting {url}")
        print(f"Status: {response.status_code}")
        if response.status_code != 404 or "Instructor not found" in response.json().get("detail", ""):
            print(f"✅ Route found at: {url}")
            return
        else:
            print(f"Response: {response.json()}")

    pytest.fail("Could not find public route at any expected path!")


def test_direct_import_check():
    """Test if we can import and inspect the public router directly."""
    try:
        from app.routes.public import router

        print("\n✅ Public router imported successfully")
        print(f"Prefix: {router.prefix}")
        print(f"Tags: {router.tags}")

        # List routes on the router
        print("\nRoutes defined on public router:")
        for route in router.routes:
            print(f"  {route.methods} {route.path}")

    except Exception as e:
        pytest.fail(f"Failed to import public router: {e}")
