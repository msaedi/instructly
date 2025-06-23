# backend/tests/test_route_exists.py
from fastapi.testclient import TestClient

from app.main import app


def test_routes_exist():
    client = TestClient(app)
    # List all routes
    for route in app.routes:
        if hasattr(route, "path"):
            print(f"Route: {route.methods} {route.path}")

    # Try to access the endpoint without auth to see what error we get
    response = client.get("/instructors/availability-windows/week/booked-slots?start_date=2025-06-23")
    print(f"Status without auth: {response.status_code}")
    print(f"Response: {response.json()}")


if __name__ == "__main__":
    test_routes_exist()
