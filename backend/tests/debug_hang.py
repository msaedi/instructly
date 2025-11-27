import time

from fastapi.testclient import TestClient

from app.main import fastapi_app as app


def test_booking_endpoint_directly():
    """Exercise bookings upcoming without Schemathesis to see if it hangs."""
    print("Creating TestClient...")
    start = time.time()
    with TestClient(app) as client:
        print("TestClient created, making request...")
        resp = client.get("/api/v1/bookings/upcoming")
        elapsed = time.time() - start
        print(f"Response received in {elapsed:.2f}s: {resp.status_code}")
        print(f"Body: {resp.text[:200]}")


def test_instructor_endpoint_directly():
    """Control: instructor endpoint that works under Schemathesis."""
    print("Creating TestClient...")
    start = time.time()
    with TestClient(app) as client:
        print("TestClient created, making request...")
        resp = client.get("/api/v1/instructors")
        elapsed = time.time() - start
        print(f"Response received in {elapsed:.2f}s: {resp.status_code}")
        print(f"Body: {resp.text[:200]}")
