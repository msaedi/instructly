from __future__ import annotations

from datetime import date, timedelta, timezone
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


def test_get_week_bitmap_returns_windows_and_etag(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    week_start = date(2025, 11, 3)
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()

    windows = {
        week_start: [("09:00:00", "10:00:00")],
        week_start + timedelta(days=1): [("14:00:00", "15:00:00")],
    }
    _upsert_week(repo, test_instructor.id, week_start, windows)
    db.commit()

    resp = bitmap_client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 7
    assert resp.headers.get("ETag")
    assert resp.headers.get("Access-Control-Expose-Headers") == "ETag, Last-Modified, X-Allow-Past"
    assert resp.headers.get("X-Allow-Past") == "true"

    first_day = body[week_start.isoformat()]
    assert first_day == [
        {"start_time": "09:00:00", "end_time": "10:00:00"},
    ]
    second_day = body[(week_start + timedelta(days=1)).isoformat()]
    assert second_day == [
        {"start_time": "14:00:00", "end_time": "15:00:00"},
    ]


def test_save_week_bitmap_initial_then_if_match_conflict_and_override(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    week_start = date(2025, 11, 10)

    body = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": week_start.isoformat(),
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
            {
                "date": (week_start + timedelta(days=2)).isoformat(),
                "start_time": "15:00:00",
                "end_time": "16:00:00",
            },
        ],
    }

    resp = bitmap_client.post(
        "/instructors/availability/week",
        json=body,
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    first_version = resp.headers.get("ETag")
    assert first_version
    payload = resp.json()
    assert payload["windows_created"] == 7

    intermediate_body = {
        **body,
        "schedule": [
            {
                "date": week_start.isoformat(),
                "start_time": "10:00:00",
                "end_time": "11:00:00",
            }
        ],
    }

    override_update = bitmap_client.post(
        "/instructors/availability/week",
        params={"override": "true"},
        json=intermediate_body,
        headers=auth_headers_instructor,
    )
    assert override_update.status_code == 200
    current_version = override_update.headers.get("ETag")
    assert current_version and current_version != first_version

    conflicting_body = {
        **body,
        "schedule": [
            {
                "date": week_start.isoformat(),
                "start_time": "11:00:00",
                "end_time": "12:00:00",
            }
        ],
    }

    conflict_resp = bitmap_client.post(
        "/instructors/availability/week",
        json=conflicting_body,
        headers={**auth_headers_instructor, "If-Match": first_version},
    )
    assert conflict_resp.status_code == 409
    conflict_json = conflict_resp.json()
    assert isinstance(conflict_json, dict)
    assert conflict_json.get("error") == "version_conflict"
    assert conflict_json.get("current_version") == current_version
    assert conflict_resp.headers.get("ETag") == current_version
    assert conflict_resp.headers.get("X-Allow-Past") == "true"
    assert (
        conflict_resp.headers.get("Access-Control-Expose-Headers")
        == "ETag, Last-Modified, X-Allow-Past"
    )

    override_resp = bitmap_client.post(
        "/instructors/availability/week",
        params={"override": "true"},
        json=conflicting_body,
        headers={**auth_headers_instructor, "If-Match": first_version},
    )
    assert override_resp.status_code == 200
    override_version = override_resp.headers.get("ETag")
    assert override_version and override_version not in {current_version, first_version}

    stored = repo.get_week(test_instructor.id, week_start)
    assert windows_from_bits(stored[week_start]) == [("11:00:00", "12:00:00")]


def test_save_week_bitmap_persists_past_days_when_allowed(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    week_start = date(2025, 10, 27)

    real_datetime = availability_service_module.datetime

    class FixedDateTime(real_datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            anchor = real_datetime(2025, 10, 30, 12, 0, tzinfo=timezone.utc)
            if tz:
                return anchor.astimezone(tz)
            return anchor.replace(tzinfo=None)

    monkeypatch.setattr(availability_service_module, "datetime", FixedDateTime)

    past_day = week_start
    future_day = week_start + timedelta(days=5)

    payload = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": past_day.isoformat(),
                "start_time": "08:00:00",
                "end_time": "09:00:00",
            },
            {
                "date": future_day.isoformat(),
                "start_time": "16:00:00",
                "end_time": "17:00:00",
            },
        ],
    }

    resp = bitmap_client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Allow-Past") == "true"

    fetched = bitmap_client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert fetched.status_code == 200
    body = fetched.json()
    assert body[past_day.isoformat()] == [
        {"start_time": "08:00:00", "end_time": "09:00:00"},
    ]
    assert body[future_day.isoformat()] == [
        {"start_time": "16:00:00", "end_time": "17:00:00"},
    ]

    stored = repo.get_week(test_instructor.id, week_start)
    assert windows_from_bits(stored[past_day]) == [("08:00:00", "09:00:00")]
    assert windows_from_bits(stored[future_day]) == [("16:00:00", "17:00:00")]


def test_copy_week_bitmap_copies_all_days(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()

    source_week = date(2025, 11, 3)
    target_week = source_week + timedelta(days=7)

    windows = {
        source_week + timedelta(days=offset): [("09:00:00", "10:00:00")]
        for offset in range(7)
    }
    _upsert_week(repo, test_instructor.id, source_week, windows)
    db.commit()

    resp = bitmap_client.post(
        "/instructors/availability/copy-week",
        json={
            "from_week_start": source_week.isoformat(),
            "to_week_start": target_week.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["windows_copied"] == 7

    copied = repo.get_week(test_instructor.id, target_week)
    for offset in range(7):
        day = target_week + timedelta(days=offset)
        assert windows_from_bits(copied[day]) == [("09:00:00", "10:00:00")]
