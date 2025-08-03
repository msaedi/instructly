# backend/tests/routes/test_public_route_registration.py
"""
Simple test to verify public routes are registered.
Run this first to ensure main.py is updated correctly.
"""

import pytest


def test_public_routes_registered(client):
    """Test that public routes are registered in the app."""
    # Try to access the public availability endpoint
    response = client.get("/api/public/instructors/1/availability?start_date=2025-07-10")

    # If we get 404 with generic "Not Found", routes aren't registered
    if response.status_code == 404 and response.json().get("detail") == "Not Found":
        pytest.fail(
            "\n\n"
            + "=" * 60
            + "\n"
            + "PUBLIC ROUTES NOT REGISTERED!\n"
            + "=" * 60
            + "\n"
            + "You need to update backend/app/main.py:\n\n"
            + "1. Add import at top:\n"
            + "   from .routes import public\n\n"
            + "2. Register router (with other routers):\n"
            + "   app.include_router(public.router)\n\n"
            + "=" * 60
            + "\n"
        )

    # If we get 404 with "Instructor not found", routes ARE registered
    if response.status_code == 404 and "Instructor not found" in response.json().get("detail", ""):
        # This is expected - instructor 1 doesn't exist
        pass

    # If we get 400 (bad date), routes are registered
    elif response.status_code == 400:
        # This is fine - means route is working
        pass

    # Any other response means routes are working
    print(f"✅ Public routes are registered! Response: {response.status_code}")


def test_next_available_route_registered(client):
    """Test that next-available route is registered."""
    response = client.get("/api/public/instructors/1/next-available")

    # Similar check - 404 with "Not Found" means not registered
    if response.status_code == 404 and response.json().get("detail") == "Not Found":
        pytest.fail("Next-available route not registered!")

    print(f"✅ Next-available route registered! Response: {response.status_code}")


def test_list_all_routes(client):
    """List all registered routes for debugging."""
    from app.main import fastapi_app as app

    print("\n📍 All registered routes:")
    for route in app.routes:
        if hasattr(route, "path"):
            print(f"  {route.methods} {route.path}")

    # Check if public routes are in the list
    public_routes = [r for r in app.routes if hasattr(r, "path") and "/api/public" in r.path]

    if not public_routes:
        print("\n❌ No public routes found!")
    else:
        print(f"\n✅ Found {len(public_routes)} public routes")
        for route in public_routes:
            print(f"  {route.methods} {route.path}")
