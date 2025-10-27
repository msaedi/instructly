from __future__ import annotations

from datetime import date, time, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.middleware.perf_counters import PerfCounterMiddleware
from app.models.availability import AvailabilitySlot


def _ensure_perf_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    existing = {middleware.cls for middleware in client.app.user_middleware}
    if PerfCounterMiddleware not in existing:
        client.app.add_middleware(PerfCounterMiddleware)


@pytest.mark.usefixtures("STRICT_ON")
def test_week_get_uses_single_query(
    client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_perf_mode(client, monkeypatch)

    week_start = date(2025, 10, 20)
    db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == test_instructor.id).delete()

    slots = []
    for day_offset in range(7):
        current_date = week_start + timedelta(days=day_offset)
        slots.append(
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=current_date,
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
        )
        slots.append(
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=current_date,
                start_time=time(14, 0),
                end_time=time(15, 0),
            )
        )

    db.add_all(slots)
    db.commit()

    response = client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers={**auth_headers_instructor, "x-debug-sql": "1"},
    )

    assert response.status_code == 200
    table_header = response.headers.get("x-db-table-availability_slots")
    assert table_header is not None and table_header.isdigit()
    sample_sql = response.headers.get("x-db-table-availability_slots-sql", "")
    assert int(table_header) <= 1, (
        "Expected single availability_slots query, got "
        f"{table_header}. Sample SQL: {sample_sql}"
    )
