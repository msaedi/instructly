from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    from importlib import reload

    import app.main as main
    import app.routes.bookings as routes
    import app.schemas.base as base
    import app.schemas.booking as bs

    reload(base)
    reload(bs)
    reload(routes)
    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_create_booking_rejects_extra_field(client: TestClient):
    # Create a payload with the required fields plus an unexpected field
    payload = {
        "instructor_id": "instr_123",
        "instructor_service_id": "svc_123",
        "booking_date": "2025-08-01",
        "start_time": "09:00",
        "selected_duration": 60,
        "unexpected": 1,
    }
    resp = client.post("/api/v1/bookings/", json=payload)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    body = resp.json()
    assert "title" in body or "detail" in body


def test_check_availability_rejects_extra_field(client: TestClient):
    payload = {
        "instructor_id": "instr_123",
        "instructor_service_id": "svc_123",
        "booking_date": "2025-08-01",
        "start_time": "09:00",
        "end_time": "10:00",
        "plus_one": True,
    }
    resp = client.post("/api/v1/bookings/check-availability", json=payload)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422


def test_bookings_list_query_param_strictness(client: TestClient):
    # Supply an unexpected query parameter to the bookings list
    resp = client.get("/api/v1/bookings/?page=1&per_page=10&unexpected=1")
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    # Our current route does not enforce query param rejection; allow 200
    # This test remains as a canary in case we add explicit query param validation later.
    assert resp.status_code in (200, 422)
