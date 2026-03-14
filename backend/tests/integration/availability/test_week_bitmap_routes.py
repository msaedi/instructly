from __future__ import annotations

import asyncio
from datetime import date, time, timedelta, timezone
from typing import Dict, List, Tuple

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.core.timezone_utils as timezone_utils_module
from app.models import AvailabilityDay, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.services.availability_service as availability_service_module
from app.services.booking_service import BookingService
from app.utils.bitmap_base64 import decode_bitmap_bytes, encode_bitmap_bytes
from app.utils.bitset import (
    bits_from_windows,
    new_empty_bits,
    new_empty_tags,
    set_range_tag,
    windows_from_bits,
)

# Use shared bitmap_app and bitmap_client fixtures from conftest


def _upsert_week(
    repo: AvailabilityDayRepository,
    instructor_id: str,
    week_start: date,
    windows_by_day: Dict[date, List[Tuple[str, str]]],
    *,
    tags_by_day: Dict[date, bytes] | None = None,
) -> None:
    """Helper to seed bitmap availability for tests."""
    items = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        wins = windows_by_day.get(day, [])
        bits = bits_from_windows(wins) if wins else bits_from_windows([])
        format_tags = (tags_by_day or {}).get(day, new_empty_tags())
        items.append((day, bits, format_tags))
    repo.upsert_week(instructor_id, items)


def _build_bitmap_days_payload(
    week_start: date,
    windows_by_day: Dict[date, List[Tuple[str, str]]],
) -> list[dict[str, str]]:
    days: list[dict[str, str]] = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        windows = windows_by_day.get(day, [])
        days.append(
            {
                "date": day.isoformat(),
                "bits": encode_bitmap_bytes(bits_from_windows(windows) if windows else new_empty_bits()),
                "format_tags": encode_bitmap_bytes(new_empty_tags()),
            }
        )
    return days


def _body_days_map(body: dict) -> dict[str, dict[str, str]]:
    return {entry["date"]: entry for entry in body["days"]}


def test_get_week_bitmap_returns_base64_days_and_etag(
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
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == resp.headers.get("ETag")
    days = _body_days_map(body)
    expected_keys = {(week_start + timedelta(days=offset)).isoformat() for offset in range(7)}
    assert set(days.keys()) == expected_keys
    assert resp.headers.get("ETag")
    assert resp.headers.get("Access-Control-Expose-Headers") == "ETag, Last-Modified, X-Allow-Past"
    assert resp.headers.get("X-Allow-Past") == "true"

    first_day = days[week_start.isoformat()]
    second_day = days[(week_start + timedelta(days=1)).isoformat()]
    assert windows_from_bits(decode_bitmap_bytes(first_day["bits"], 36)) == [("09:00:00", "10:00:00")]
    assert windows_from_bits(decode_bitmap_bytes(second_day["bits"], 36)) == [("14:00:00", "15:00:00")]
    assert decode_bitmap_bytes(first_day["format_tags"], 72) == new_empty_tags()
    assert decode_bitmap_bytes(second_day["format_tags"], 72) == new_empty_tags()


def test_save_week_bitmap_initial_then_if_match_conflict_and_override(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    # Use dynamic future date: next Monday from today
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7  # If today is Monday, use next Monday
    week_start = today + timedelta(days=days_until_monday)

    body = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "days": _build_bitmap_days_payload(
            week_start,
            {
                week_start: [("09:00:00", "10:00:00")],
                week_start + timedelta(days=2): [("15:00:00", "16:00:00")],
            },
        ),
    }

    resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json=body,
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    first_version = resp.headers.get("ETag")
    assert first_version
    payload = resp.json()
    expected_windows = 2
    assert payload["windows_created"] == expected_windows
    assert payload["days_written"] == 2
    assert payload.get("weeks_affected") == 1
    assert set(payload.get("edited_dates", [])) == {
        week_start.isoformat(),
        (week_start + timedelta(days=2)).isoformat(),
    }
    assert payload["skipped_past_window"] == 0

    intermediate_body = {
        **body,
        "days": _build_bitmap_days_payload(
            week_start,
            {week_start: [("10:00:00", "11:00:00")]},
        ),
    }

    override_update = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        params={"override": "true"},
        json=intermediate_body,
        headers=auth_headers_instructor,
    )
    assert override_update.status_code == 200
    current_version = override_update.headers.get("ETag")
    assert current_version and current_version != first_version

    conflicting_body = {
        **body,
        "days": _build_bitmap_days_payload(
            week_start,
            {week_start: [("11:00:00", "12:00:00")]},
        ),
    }

    conflict_resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
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
        "/api/v1/instructors/availability/week",
        params={"override": "true"},
        json=conflicting_body,
        headers={**auth_headers_instructor, "If-Match": first_version},
    )
    assert override_resp.status_code == 200
    override_version = override_resp.headers.get("ETag")
    assert override_version and override_version not in {current_version, first_version}

    stored = repo.get_week(test_instructor.id, week_start)
    assert windows_from_bits(stored[week_start]) == [("11:00:00", "12:00:00")]


@pytest.mark.asyncio
async def test_midnight_window_round_trip(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    monday = today + timedelta(days=days_until_monday)
    payload = {
        "week_start": monday.isoformat(),
        "clear_existing": True,
        "days": _build_bitmap_days_payload(
            monday,
            {monday: [("23:30:00", "24:00:00")]},
        ),
    }

    create_resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )
    assert create_resp.status_code == 200, create_resp.text

    get_resp = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": monday.isoformat()},
        headers=auth_headers_instructor,
    )
    assert get_resp.status_code == 200
    body = _body_days_map(get_resp.json())
    assert windows_from_bits(decode_bitmap_bytes(body[monday.isoformat()]["bits"], 36)) == [
        ("23:30:00", "24:00:00"),
    ]

    booking_service = BookingService(db)
    windows = await asyncio.to_thread(booking_service._get_instructor_availability_windows,
        test_instructor.id,
        monday,
        time(0, 0),
        time(0, 0),
    )
    assert windows and windows[0]["end_time"] == time(0, 0)
    assert "_start_minutes" in windows[0] and "_end_minutes" in windows[0]
    assert windows[0]["_start_minutes"] == 23 * 60 + 30
    assert windows[0]["_end_minutes"] == 24 * 60

    opportunities = booking_service._calculate_booking_opportunities(
        windows,
        existing_bookings=[],
        target_duration_minutes=30,
        earliest_time=time(0, 0),
        latest_time=time(0, 0),
        instructor_id=test_instructor.id,
        target_date=monday,
    )
    assert opportunities, f"Opportunities returned: {opportunities}"
    assert any(op["end_time"] == "00:00:00" for op in opportunities)


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
    monkeypatch.setattr(timezone_utils_module, "datetime", FixedDateTime)

    past_day = week_start
    future_day = week_start + timedelta(days=5)

    payload = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "days": _build_bitmap_days_payload(
            week_start,
            {
                past_day: [("08:00:00", "09:00:00")],
                future_day: [("16:00:00", "17:00:00")],
            },
        ),
    }

    resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Allow-Past") == "true"

    fetched = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert fetched.status_code == 200
    body = _body_days_map(fetched.json())
    assert windows_from_bits(decode_bitmap_bytes(body[past_day.isoformat()]["bits"], 36)) == [
        ("08:00:00", "09:00:00"),
    ]
    assert windows_from_bits(decode_bitmap_bytes(body[future_day.isoformat()]["bits"], 36)) == [
        ("16:00:00", "17:00:00"),
    ]

    stored = repo.get_week(test_instructor.id, week_start)
    assert windows_from_bits(stored[past_day]) == [("08:00:00", "09:00:00")]
    assert windows_from_bits(stored[future_day]) == [("16:00:00", "17:00:00")]


def test_week_bitmap_round_trip_preserves_format_tags_and_updates_etag(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    week_start = today + timedelta(days=days_until_monday)
    day = week_start

    initial_days = _build_bitmap_days_payload(week_start, {day: [("09:00:00", "10:00:00")]})
    initial_days[0]["format_tags"] = encode_bitmap_bytes(set_range_tag(new_empty_tags(), 108, 12, 1))

    first_resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json={
            "week_start": week_start.isoformat(),
            "clear_existing": True,
            "days": initial_days,
        },
        headers=auth_headers_instructor,
    )
    assert first_resp.status_code == 200
    assert first_resp.json()["days_written"] == 1
    first_etag = first_resp.headers.get("ETag")

    get_resp = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert get_resp.status_code == 200
    body = _body_days_map(get_resp.json())
    assert decode_bitmap_bytes(body[day.isoformat()]["format_tags"], 72) == decode_bitmap_bytes(
        initial_days[0]["format_tags"],
        72,
    )

    updated_days = _build_bitmap_days_payload(week_start, {day: [("09:00:00", "10:00:00")]})
    updated_days[0]["format_tags"] = encode_bitmap_bytes(set_range_tag(new_empty_tags(), 108, 12, 2))
    second_resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json={
            "week_start": week_start.isoformat(),
            "clear_existing": True,
            "days": updated_days,
        },
        headers={**auth_headers_instructor, "If-Match": first_etag},
    )
    assert second_resp.status_code == 200
    second_etag = second_resp.headers.get("ETag")
    assert second_etag and second_etag != first_etag

    stored = repo.get_week_bitmaps(test_instructor.id, week_start)
    assert stored[day][1] == decode_bitmap_bytes(updated_days[0]["format_tags"], 72)


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
    tags_by_day = {
        source_week + timedelta(days=0): set_range_tag(new_empty_tags(), 108, 12, 1),
        source_week + timedelta(days=1): set_range_tag(new_empty_tags(), 108, 12, 2),
    }
    _upsert_week(repo, test_instructor.id, source_week, windows, tags_by_day=tags_by_day)
    db.commit()

    resp = bitmap_client.post(
        "/api/v1/instructors/availability/copy-week",
        json={
            "from_week_start": source_week.isoformat(),
            "to_week_start": target_week.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["windows_copied"] == 7

    copied = repo.get_week_bitmaps(test_instructor.id, target_week)
    for offset in range(7):
        day = target_week + timedelta(days=offset)
        copied_bits, copied_tags = copied[day]
        assert windows_from_bits(copied_bits) == [("09:00:00", "10:00:00")]
        assert copied_tags == tags_by_day.get(day - timedelta(days=7), new_empty_tags())
