import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv('STRICT_SCHEMAS', raising=False)

    from importlib import reload
    from types import SimpleNamespace

    import app.schemas.base as base
    import app.schemas.booking as booking_schemas
    import app.api.dependencies as api_dependencies
    import app.routes.bookings as bookings_routes
    import app.main as main

    reload(base)
    reload(booking_schemas)
    reload(api_dependencies)
    reload(bookings_routes)
    reload(main)

    dummy_user = SimpleNamespace(id='user_123', roles=[])
    main.fastapi_app.dependency_overrides[api_dependencies.get_current_active_user] = lambda: dummy_user

    class DummyBookingService:
        async def create_booking_with_payment_setup(self, *_, **__):  # pragma: no cover
            raise AssertionError('service should not execute during validation tests')

        async def check_availability(self, *_, **__):  # pragma: no cover
            raise AssertionError('service should not execute during validation tests')

        async def reschedule_booking(self, *_, **__):  # pragma: no cover
            raise AssertionError('service should not execute during validation tests')

    main.fastapi_app.dependency_overrides[api_dependencies.get_booking_service] = lambda: DummyBookingService()

    for route in main.fastapi_app.routes:
        if getattr(route, 'path', '').startswith('/bookings') and getattr(route, 'dependencies', None):
            for dep in route.dependencies:
                main.fastapi_app.dependency_overrides[dep.dependency] = lambda: None

    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_create_booking_rejects_datetime_strings(client: TestClient):
    payload = {
        'instructor_id': 'instr_123',
        'instructor_service_id': 'svc_123',
        'booking_date': '2025-08-01T00:00:00Z',
        'start_time': '09:00',
        'selected_duration': 60,
    }
    resp = client.post('/bookings/', json=payload)
    assert resp.status_code == 422


def test_check_availability_rejects_datetime_strings(client: TestClient):
    payload = {
        'instructor_id': 'instr_123',
        'instructor_service_id': 'svc_123',
        'booking_date': '2025-08-01 09:00:00',
        'start_time': '09:00',
        'end_time': '10:00',
    }
    resp = client.post('/bookings/check-availability', json=payload)
    assert resp.status_code == 422


def test_reschedule_rejects_datetime_strings(client: TestClient):
    payload = {
        'booking_date': '2025-08-01T00:00:00',
        'start_time': '09:00',
        'selected_duration': 60,
    }
    resp = client.post('/bookings/demo-booking/reschedule', json=payload)
    assert resp.status_code == 422
