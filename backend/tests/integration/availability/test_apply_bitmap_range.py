from __future__ import annotations

from datetime import date, timedelta
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_seed import next_monday, seed_week_bits

import app.api.dependencies.services as dependency_services
import app.main
from app.models import AvailabilityDay, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module
import app.services.week_operation_service as week_operation_service_module
from app.utils.bitset import windows_from_bits

pytestmark = pytest.mark.usefixtures("bitmap_env_relaxed")


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


def _future_source_monday() -> date:
    today = date.today()
    # Guardrails clamp copy-to-future, so ensure the source is at least one week ahead.
    return next_monday(today + timedelta(days=7))


def test_apply_bitmap_pattern_across_weeks(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()

    source_week = _future_source_monday()
    pattern = {
        0: [("09:00:00", "10:00:00")],
        2: [("14:00:00", "16:00:00")],
        4: [("08:00:00", "09:30:00")],
    }
    written = seed_week_bits(
        db,
        instructor_id=test_instructor.id,
        week_start=source_week,
        windows_by_weekday=pattern,
        clear_existing=True,
    )
    assert written == len(pattern)

    target_start = source_week + timedelta(days=7)
    weeks_to_apply = 4
    target_end = target_start + timedelta(days=7 * weeks_to_apply - 1)

    resp = bitmap_client.post(
        "/instructors/availability/apply-to-date-range",
        json={
            "from_week_start": source_week.isoformat(),
            "start_date": target_start.isoformat(),
            "end_date": target_end.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["weeks_applied"] == weeks_to_apply
    assert body.get("weeks_affected", 0) >= 1
    assert body.get("days_written", 0) > 0
    assert body.get("windows_created", 0) > 0

    for week_index in range(weeks_to_apply):
        target_monday = target_start + timedelta(days=7 * week_index)
        stored_week = repo.get_week(test_instructor.id, target_monday)
        for weekday in range(7):
            target_day = target_monday + timedelta(days=weekday)
            expected = pattern.get(weekday, [])
            bits = stored_week.get(target_day)
            if not bits:
                assert expected == []
            else:
                assert windows_from_bits(bits) == expected

        get_resp = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": target_monday.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        payload = get_resp.json()
        for weekday in range(7):
            target_day = target_monday + timedelta(days=weekday)
            expected = [
                {"start_time": start, "end_time": end}
                for start, end in pattern.get(weekday, [])
            ]
            assert payload[target_day.isoformat()] == expected


def test_apply_bitmap_pattern_no_source_bits(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()

    source_week = _future_source_monday()
    # Ensure the source week is explicitly empty.
    seed_week_bits(
        db,
        instructor_id=test_instructor.id,
        week_start=source_week,
        windows_by_weekday={},
        clear_existing=True,
    )

    target_start = source_week + timedelta(days=7)
    target_end = target_start + timedelta(days=13)

    resp = bitmap_client.post(
        "/instructors/availability/apply-to-date-range",
        json={
            "from_week_start": source_week.isoformat(),
            "start_date": target_start.isoformat(),
            "end_date": target_end.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("windows_created", 0) == 0
    assert body.get("days_written", 0) == 0

    for offset in range(0, (target_end - target_start).days + 1, 7):
        target_monday = target_start + timedelta(days=offset)
        stored_week = repo.get_week(test_instructor.id, target_monday)
        for bits in stored_week.values():
            assert windows_from_bits(bits) == []

        get_resp = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": target_monday.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        payload = get_resp.json()
        for day_payload in payload.values():
            assert day_payload == []
