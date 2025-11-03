from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from tests.utils.availability_builders import future_week_start

from app.models.availability import AvailabilitySlot


@pytest.fixture(autouse=True)
def enable_test_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    monkeypatch.setenv("AVAILABILITY_TEST_MEMORY_CACHE", "1")


def _seed_week(db, instructor_id: str, week_start: date, start_hour: int) -> None:
    week_end = week_start + timedelta(days=6)
    db.query(AvailabilitySlot).filter(
        AvailabilitySlot.instructor_id == instructor_id,
        AvailabilitySlot.specific_date.between(week_start, week_end),
    ).delete(synchronize_session=False)

    for day in range(7):
        current = week_start + timedelta(days=day)
        db.add(
            AvailabilitySlot(
                instructor_id=instructor_id,
                specific_date=current,
                start_time=time(start_hour, 0),
                end_time=time(start_hour + 1, 0),
            )
        )
    db.commit()


def _build_payload(week_start: date, start_hour: int) -> dict[str, object]:
    schedule = []
    for day in range(7):
        current = week_start + timedelta(days=day)
        schedule.append(
            {
                "date": current.isoformat(),
                "start_time": f"{start_hour:02d}:00",
                "end_time": f"{start_hour + 1:02d}:00",
            }
        )
    return {"week_start": week_start.isoformat(), "clear_existing": True, "schedule": schedule}


@pytest.mark.usefixtures("STRICT_ON")
def test_availability_cache_hit_rate(
    client,
    db,
    test_instructor,
    auth_headers_instructor,
) -> None:
    week_start = future_week_start(weeks_ahead=1)
    _seed_week(db, test_instructor.id, week_start, start_hour=8)

    headers = {**auth_headers_instructor, "x-debug-sql": "1"}
    resp1 = client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert resp1.status_code == 200
    assert int(resp1.headers.get("x-cache-misses", "0")) >= 1

    resp2 = client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert int(resp2.headers.get("x-cache-hits", "0")) >= 1
    assert resp2.headers.get("x-cache-key")
    assert resp2.json() == resp1.json()

    save_payload = _build_payload(week_start, start_hour=10)
    save_resp = client.post(
        "/instructors/availability/week",
        json=save_payload,
        headers=auth_headers_instructor,
    )
    assert save_resp.status_code == 200

    resp3 = client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=headers,
    )
    assert resp3.status_code == 200
    assert int(resp3.headers.get("x-cache-misses", "0")) >= 1
    monday_entries = resp3.json()[week_start.isoformat()]
    assert any(entry["start_time"].startswith("10:00") for entry in monday_entries)


@pytest.mark.usefixtures("STRICT_ON")
def test_availability_cache_invalidation_on_copy(
    client,
    db,
    test_instructor,
    auth_headers_instructor,
) -> None:
    src_week = future_week_start(weeks_ahead=1)
    dst_week = future_week_start(weeks_ahead=2)
    _seed_week(db, test_instructor.id, src_week, start_hour=9)
    _seed_week(db, test_instructor.id, dst_week, start_hour=6)

    headers = {**auth_headers_instructor, "x-debug-sql": "1"}
    warm_resp = client.get(
        "/instructors/availability/week",
        params={"start_date": dst_week.isoformat()},
        headers=headers,
    )
    assert warm_resp.status_code == 200

    copy_resp = client.post(
        "/instructors/availability/copy-week",
        json={
            "from_week_start": src_week.isoformat(),
            "to_week_start": dst_week.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert copy_resp.status_code == 200

    resp = client.get(
        "/instructors/availability/week",
        params={"start_date": dst_week.isoformat()},
        headers=headers,
    )
    assert resp.status_code == 200
    assert int(resp.headers.get("x-cache-misses", "0")) >= 1
    for entry in resp.json()[dst_week.isoformat()]:
        assert entry["start_time"].startswith("09:00")
