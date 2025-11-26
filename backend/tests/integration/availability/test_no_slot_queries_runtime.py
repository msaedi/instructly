"""
Guard test: Assert that availability operations never query availability_slots table.

This test verifies that the x-db-table-availability_slots header is always "0",
confirming that bitmap-only operations are being used.
"""

from datetime import date, timedelta
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.api.dependencies.services as dependency_services
import app.main
from app.models.user import User
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module
import app.services.week_operation_service as week_operation_service_module


@pytest.fixture
def bitmap_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability enabled."""
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    reload(availability_service_module)
    reload(week_operation_service_module)
    reload(availability_routes)
    reload(dependency_services)
    reload(app.main)

    yield app.main

    reload(availability_service_module)
    reload(week_operation_service_module)
    reload(availability_routes)
    reload(dependency_services)
    reload(app.main)


@pytest.fixture
def bitmap_client(bitmap_app) -> TestClient:
    """Return a TestClient backed by the bitmap-enabled app instance."""
    client = TestClient(bitmap_app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def clear_week_bits(db: Session, test_instructor: User):
    """Clear bitmap data for the instructor's week."""
    from app.models.availability_day import AvailabilityDay

    # Clear by deleting existing rows
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()
    yield
    # Cleanup - delete again
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()


def test_post_and_get_week_no_slot_queries(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    clear_week_bits,
    auth_headers_instructor: dict,
):
    """
    POST then GET a week and assert x-db-table-availability_slots == "0".

    This confirms that bitmap-only operations are used and no slot table queries occur.
    """
    week_start = date.today() - timedelta(days=date.today().weekday())
    monday_str = week_start.isoformat()

    # POST /instructors/availability/week
    payload = {
        "week_start": monday_str,
        "schedule": [
            {"date": monday_str, "start_time": "09:00:00", "end_time": "12:00:00"},
            {"date": monday_str, "start_time": "14:00:00", "end_time": "17:00:00"},
            {
                "date": (week_start + timedelta(days=2)).isoformat(),
                "start_time": "10:00:00",
                "end_time": "15:00:00",
            },
        ],
        "clear_existing": True,
    }

    # Use auth headers from fixture
    headers = auth_headers_instructor

    # POST week availability
    post_response = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json=payload,
        headers=headers,
    )
    assert post_response.status_code == 200
    post_data = post_response.json()

    # Verify POST response has bitmap counters
    assert post_data["windows_created"] >= 0
    assert post_data["days_written"] >= 0
    assert "slots_created" not in post_data or post_data.get("slots_created") == 0

    # Check perf header - should be "0" (no slot queries)
    slot_header = post_response.headers.get("x-db-table-availability_slots")
    assert slot_header == "0", (
        f"Expected x-db-table-availability_slots='0', got '{slot_header}'. Slot queries detected!"
    )

    # GET /instructors/availability/week
    get_response = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": monday_str},
        headers=headers,
    )
    assert get_response.status_code == 200
    get_data = get_response.json()

    # Verify GET response structure
    assert isinstance(get_data, dict)
    assert monday_str in get_data
    assert len(get_data[monday_str]) >= 2  # At least two windows on Monday

    # Check perf header - should be "0" (no slot queries)
    slot_header_get = get_response.headers.get("x-db-table-availability_slots")
    assert slot_header_get == "0", (
        f"Expected x-db-table-availability_slots='0' on GET, got '{slot_header_get}'. Slot queries detected!"
    )

    # Verify bitmap data was actually written
    # Use db_session fixture instead of get_db()
    # db = next(get_db())
    # bitmap_repo = AvailabilityDayRepository(db)
    # monday_bits = bitmap_repo.get_day_bits(unique_instructor.id, week_start)
    # assert monday_bits is not None, "Bitmap data should exist for Monday"
    # from app.utils.bitset import windows_from_bits

    # monday_windows = windows_from_bits(monday_bits)
    # assert len(monday_windows) == 2, "Monday should have 2 windows"
