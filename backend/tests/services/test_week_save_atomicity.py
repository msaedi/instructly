from __future__ import annotations

from datetime import time, timedelta
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from tests.utils.availability_builders import build_week_payload, future_week_start

import app.main
from app.middleware.perf_counters import PerfCounterMiddleware
from app.models.availability import AvailabilitySlot
from app.repositories.bulk_operation_repository import BulkOperationRepository


@pytest.fixture
def perf_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    reload(app.main)
    app_instance = app.main.fastapi_app
    if PerfCounterMiddleware not in {mw.cls for mw in app_instance.user_middleware}:
        app_instance.add_middleware(PerfCounterMiddleware)
    client = TestClient(app_instance, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def _count_slots(db: Session, instructor_id: str) -> int:
    return db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == instructor_id).count()


@pytest.mark.usefixtures("STRICT_ON")
def test_week_save_rolls_back_on_fault(
    perf_client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    week_start = future_week_start(weeks_ahead=3)
    existing_slot = AvailabilitySlot(
        instructor_id=test_instructor.id,
        specific_date=week_start,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db.add(existing_slot)
    db.commit()

    payload = build_week_payload(week_start, slot_count=30, clear_existing=True)
    before_count = _count_slots(db, test_instructor.id)

    original_bulk_create = BulkOperationRepository.bulk_create_slots

    def _boom(self, slots_data):  # type: ignore[override]
        original_bulk_create(self, slots_data)
        raise RuntimeError("Simulated bulk insert failure")

    monkeypatch.setattr(BulkOperationRepository, "bulk_create_slots", _boom)

    response = perf_client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )

    assert response.status_code >= 500
    after_count = _count_slots(db, test_instructor.id)
    assert before_count == after_count


@pytest.mark.parametrize("slot_count", [10, 30, 50])
def test_week_save_happy_path_query_counts_param(
    perf_client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor: dict,
    slot_count: int,
):
    db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == test_instructor.id).delete()
    db.commit()

    week_start = future_week_start(weeks_ahead=3)
    payload = build_week_payload(week_start, slot_count=slot_count)

    response = perf_client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200

    db_query_header = response.headers.get("x-db-query-count")
    assert db_query_header is not None and db_query_header.isdigit()

    cache_hit_header = response.headers.get("x-cache-hits")
    cache_miss_header = response.headers.get("x-cache-misses")
    assert cache_hit_header is not None and cache_hit_header.isdigit()
    assert cache_miss_header is not None and cache_miss_header.isdigit()


@pytest.mark.usefixtures("STRICT_ON")
def test_week_save_rejects_overlap_via_api(
    perf_client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    week_start = future_week_start(weeks_ahead=3)
    db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == test_instructor.id).delete()
    db.commit()

    payload = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": week_start.isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
            },
            {
                "date": week_start.isoformat(),
                "start_time": "10:30",
                "end_time": "11:30",
            },
        ],
    }

    response = perf_client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )

    assert response.status_code == 409
    body = response.json()
    assert body.get("code") == "AVAILABILITY_OVERLAP"
    assert _count_slots(db, test_instructor.id) == 0


@pytest.mark.usefixtures("STRICT_ON")
def test_week_save_overnight_round_trip_via_api(
    perf_client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    week_start = future_week_start(weeks_ahead=4)
    db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == test_instructor.id).delete()
    db.commit()

    payload = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": week_start.isoformat(),
                "start_time": "23:30",
                "end_time": "01:00",
            }
        ],
    }

    response = perf_client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )
    assert response.status_code == 200

    get_response = perf_client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert get_response.status_code == 200
    week_map = get_response.json()

    monday_slots = week_map[week_start.isoformat()]
    assert len(monday_slots) == 1
    assert monday_slots[0]["start_time"] == "23:30:00"
    assert monday_slots[0]["end_time"] == "00:00:00"

    tuesday_key = (week_start + timedelta(days=1)).isoformat()
    assert tuesday_key in week_map
    tuesday_slots = week_map[tuesday_key]
    assert len(tuesday_slots) == 1
    assert tuesday_slots[0]["start_time"] == "00:00:00"
    assert tuesday_slots[0]["end_time"] == "01:00:00"
