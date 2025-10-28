from __future__ import annotations

from datetime import date, time, timedelta
import os

import pytest

# Ensure perf instrumentation is enabled before any app imports
os.environ["AVAILABILITY_PERF_DEBUG"] = "1"
os.environ.setdefault("AVAILABILITY_TEST_MEMORY_CACHE", "1")

from app.models.availability import AvailabilitySlot


def _seed_week(db, instructor_id: str, week_start: date, start_hour: int) -> None:
    week_end = week_start + timedelta(days=6)
    db.query(AvailabilitySlot).filter(
        AvailabilitySlot.instructor_id == instructor_id,
        AvailabilitySlot.specific_date.between(week_start, week_end),
    ).delete(synchronize_session=False)

    for offset in range(7):
        current = week_start + timedelta(days=offset)
        db.add(
            AvailabilitySlot(
                instructor_id=instructor_id,
                specific_date=current,
                start_time=time(start_hour, 0),
                end_time=time(start_hour + 1, 0),
            )
        )
    db.commit()


@pytest.mark.usefixtures("STRICT_ON")
def test_perf_counters_follow_cache_flow(
    client,
    db,
    test_instructor,
    auth_headers_instructor,
) -> None:
    week_start = date(2025, 8, 4)
    _seed_week(db, test_instructor.id, week_start, start_hour=9)

    headers = {**auth_headers_instructor, "x-debug-sql": "1"}

    # Cold request should query the DB and register a cache miss
    cold = client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert cold.status_code == 200
    assert int(cold.headers.get("x-db-query-count", "0")) > 0
    assert int(cold.headers.get("x-cache-misses", "0")) >= 1

    # Warm request should serve from cache without touching availability_slots
    warm = client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert warm.status_code == 200
    assert int(warm.headers.get("x-cache-hits", "0")) >= 1
    assert warm.headers.get("x-db-table-availability_slots") == "0"
    assert warm.headers.get("x-db-query-count") == warm.headers.get("x-db-sql-samples")
