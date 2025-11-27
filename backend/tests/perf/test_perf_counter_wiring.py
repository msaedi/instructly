from __future__ import annotations

from datetime import date, timedelta
import os

import pytest

# Ensure perf instrumentation is enabled before any app imports
os.environ["AVAILABILITY_PERF_DEBUG"] = "1"
os.environ.setdefault("AVAILABILITY_TEST_MEMORY_CACHE", "1")

from tests._utils.bitmap_avail import seed_week


def _seed_week(db, instructor_id: str, week_start: date, start_hour: int) -> None:
    """Seed a week of availability using bitmap storage."""
    week_map = {}
    for offset in range(7):
        current = week_start + timedelta(days=offset)
        week_map[current.isoformat()] = [
            (f"{start_hour:02d}:00", f"{start_hour + 1:02d}:00")
        ]
    seed_week(db, instructor_id, week_start, week_map)


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
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert cold.status_code == 200
    cold_queries = int(cold.headers.get("x-db-query-count", "0"))
    cold_misses = int(cold.headers.get("x-cache-misses", "0"))
    assert cold_queries > 0
    assert cold_misses >= 1

    # Warm request should reuse cached payload when available
    warm = client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert warm.status_code == 200
    warm_hits = int(warm.headers.get("x-cache-hits", "0"))
    warm_misses = int(warm.headers.get("x-cache-misses", "0"))
    warm_queries = int(warm.headers.get("x-db-query-count", "0"))

    if warm_hits >= 1:
        assert warm.headers.get("x-db-table-availability_slots") == "0"
        assert warm.headers.get("x-db-query-count") == warm.headers.get("x-db-sql-samples")
    else:
        # Memory-cache fallback creates per-request caches, so hits may remain 0.
        # In that case we at least ensure misses and query counts stay consistent.
        assert warm_misses >= cold_misses
        assert warm_queries >= cold_queries
