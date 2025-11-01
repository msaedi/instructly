from __future__ import annotations

from datetime import date, timedelta
from importlib import reload
from typing import Dict, List, Tuple

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.api.dependencies.services as dependency_services
import app.main
from app.models import AvailabilityDay, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module
import app.services.week_operation_service as week_operation_service_module
from app.utils.bitset import bits_from_windows, windows_from_bits


@pytest.fixture
def bitmap_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability enabled."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    reload(availability_service_module)
    reload(week_operation_service_module)
    reload(availability_routes)
    reload(dependency_services)
    reload(app.main)

    yield app.main

    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
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


def _upsert_week(
    repo: AvailabilityDayRepository,
    instructor_id: str,
    week_start: date,
    windows_by_day: Dict[date, List[Tuple[str, str]]],
) -> None:
    """Helper to seed bitmap availability for tests."""
    items = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        wins = windows_by_day.get(day, [])
        items.append((day, bits_from_windows(wins) if wins else bits_from_windows([])))
    repo.upsert_week(instructor_id, items)


def _windows_from_bits_map(bits_map: Dict[date, bytes]) -> Dict[int, List[Tuple[str, str]]]:
    """Return offset -> windows list for easier comparisons."""
    result: Dict[int, List[Tuple[str, str]]] = {}
    if not bits_map:
        return result
    anchor = min(bits_map.keys())
    for offset in range(7):
        day = anchor + timedelta(days=offset)
        result[offset] = windows_from_bits(bits_map.get(day, bits_from_windows([])))
    return result


def test_apply_bitmap_pattern_across_weeks(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    week_start = date(2025, 11, 3)

    source_windows = {
        week_start: [("09:00:00", "10:00:00")],
        week_start + timedelta(days=2): [("14:00:00", "16:00:00")],
        week_start + timedelta(days=4): [("08:00:00", "09:30:00")],
    }
    _upsert_week(repo, test_instructor.id, week_start, source_windows)
    db.commit()

    target_start = week_start + timedelta(days=7)
    target_end = target_start + timedelta(days=28 - 1)  # four full weeks

    resp = bitmap_client.post(
        "/instructors/availability/apply-to-date-range",
        json={
            "from_week_start": week_start.isoformat(),
            "start_date": target_start.isoformat(),
            "end_date": target_end.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["weeks_applied"] == 4
    assert body["weeks_affected"] == 4
    assert body["days_written"] == 12  # 3 patterned days × 4 weeks
    assert "bitmap" in body["message"].lower()

    source_bits = repo.get_week(test_instructor.id, week_start)
    source_windows_by_offset = _windows_from_bits_map(source_bits)

    for week_index in range(4):
        target_week_start = target_start + timedelta(days=7 * week_index)
        stored = repo.get_week(test_instructor.id, target_week_start)
        for offset in range(7):
            day = target_week_start + timedelta(days=offset)
            expected_windows = source_windows_by_offset.get(offset, [])
            assert windows_from_bits(stored[day]) == expected_windows

        get_resp = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": target_week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        week_payload = get_resp.json()
        for offset in range(7):
            day = target_week_start + timedelta(days=offset)
            expected_windows = [
                {"start_time": start, "end_time": end}
                for start, end in source_windows_by_offset.get(offset, [])
            ]
            assert week_payload[day.isoformat()] == expected_windows


def test_apply_bitmap_pattern_no_source_bits(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    week_start = date(2025, 12, 1)
    db.commit()

    target_start = week_start + timedelta(days=7)
    target_end = target_start + timedelta(days=6)

    resp = bitmap_client.post(
        "/instructors/availability/apply-to-date-range",
        json={
            "from_week_start": week_start.isoformat(),
            "start_date": target_start.isoformat(),
            "end_date": target_end.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["windows_created"] == 0
    assert body["weeks_affected"] == 0
    assert body["days_written"] == 0
    assert "no availability bits" in body["message"].lower()

    stored = repo.get_week(test_instructor.id, target_start)
    for bits in stored.values():
        assert windows_from_bits(bits) == []
