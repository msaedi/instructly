from __future__ import annotations

from datetime import date, time

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from tests.utils.availability_builders import build_week_payload

from app.middleware.perf_counters import PerfCounterMiddleware
from app.models.availability import AvailabilitySlot
from app.repositories.bulk_operation_repository import BulkOperationRepository


def _ensure_perf_mode(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    middleware_classes = {middleware.cls for middleware in client.app.user_middleware}
    if PerfCounterMiddleware not in middleware_classes:
        client.app.add_middleware(PerfCounterMiddleware)


def _count_slots(db: Session, instructor_id: str) -> int:
    return db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == instructor_id).count()


@pytest.mark.usefixtures("STRICT_ON")
def test_week_save_rolls_back_on_fault(
    client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _ensure_perf_mode(monkeypatch, client)

    week_start = date(2025, 10, 20)
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

    response = client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )

    assert response.status_code >= 500
    after_count = _count_slots(db, test_instructor.id)
    assert before_count == after_count


@pytest.mark.parametrize("slot_count", [10, 30, 50])
def test_week_save_happy_path_query_counts_param(
    client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor: dict,
    monkeypatch: pytest.MonkeyPatch,
    slot_count: int,
):
    _ensure_perf_mode(monkeypatch, client)

    db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == test_instructor.id).delete()
    db.commit()

    week_start = date(2025, 10, 20)
    payload = build_week_payload(week_start, slot_count=slot_count)

    response = client.post(
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
