"""
Integration tests for bitmap past-edit guardrails.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditLog, AvailabilityDay, EventOutbox
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.services.availability_service as availability_service_module
import app.services.week_operation_service as week_operation_service_module
from app.utils.bitset import bits_from_windows, windows_from_bits

# Use shared bitmap_app and bitmap_client fixtures from conftest


@pytest.fixture
def anchor_today(monkeypatch: pytest.MonkeyPatch) -> date:
    anchor = date(2025, 6, 10)
    monkeypatch.setattr(settings, "past_edit_window_days", 7)
    monkeypatch.setattr(settings, "suppress_past_availability_events", True)
    monkeypatch.setattr(settings, "clamp_copy_to_future", False)
    monkeypatch.setattr(availability_service_module, "get_user_today_by_id", lambda *_: anchor)
    monkeypatch.setattr(week_operation_service_module, "get_user_today_by_id", lambda *_: anchor)
    return anchor


def _freeze_datetime_for_guardrails(monkeypatch: pytest.MonkeyPatch, target: date) -> None:
    real_datetime = availability_service_module.datetime

    class FrozenDateTime(real_datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            anchor = real_datetime.combine(target, datetime.min.time()).replace(
                hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
            )
            if tz:
                return anchor.astimezone(tz)
            return anchor.replace(tzinfo=None)

    monkeypatch.setattr(availability_service_module, "datetime", FrozenDateTime)
    monkeypatch.setattr(availability_service_module, "get_user_today_by_id", lambda *_: target)
    monkeypatch.setattr(week_operation_service_module, "get_user_today_by_id", lambda *_: target)

def test_bitmap_past_clamp_skips_outside_window(
    bitmap_client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor,
    anchor_today: date,
) -> None:
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()
    events_before = db.query(EventOutbox).count()

    week_start = anchor_today - timedelta(days=anchor_today.weekday() + 7)
    far_past = week_start
    recent_past = week_start + timedelta(days=6)

    request_body = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": far_past.isoformat(),
                "start_time": "08:00:00",
                "end_time": "09:00:00",
            },
            {
                "date": recent_past.isoformat(),
                "start_time": "10:00:00",
                "end_time": "11:00:00",
            },
        ],
    }

    resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json=request_body,
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["skipped_past_window"] == 1
    assert payload["days_written"] == 1

    get_resp = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert get_resp.status_code == 200
    week_map = get_resp.json()
    assert week_map.get(far_past.isoformat(), []) == []
    assert week_map[recent_past.isoformat()] == [
        {"start_time": "10:00:00", "end_time": "11:00:00"}
    ]

    # Ensure no availability events were enqueued for skipped past edits
    events_after = db.query(EventOutbox).count()
    assert events_after == events_before

    audit_entry = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "availability",
            AuditLog.entity_id == f"{test_instructor.id}:{week_start.isoformat()}",
        )
        .order_by(AuditLog.occurred_at.desc())
        .first()
    )
    assert audit_entry is not None
    after_payload = audit_entry.after or {}
    assert after_payload.get("historical_edit") is True
    assert far_past.isoformat() in after_payload.get("skipped_dates", [])
    assert recent_past.isoformat() in after_payload.get("edited_dates", [])


def test_apply_range_clamps_past_targets(
    bitmap_client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_instructor,
    anchor_today: date,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "clamp_copy_to_future", True)
    _freeze_datetime_for_guardrails(monkeypatch, anchor_today)
    repo = AvailabilityDayRepository(db)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()

    source_week = anchor_today - timedelta(days=anchor_today.weekday() + 14)
    source_windows = {
        source_week + timedelta(days=i): [("09:00:00", "10:00:00")]
        for i in range(7)
    }
    repo.upsert_week(
        test_instructor.id,
        [(day, bits_from_windows(windows)) for day, windows in source_windows.items()],
    )
    db.commit()

    start_date = anchor_today - timedelta(days=3)
    end_date = anchor_today + timedelta(days=6)

    resp = bitmap_client.post(
        "/api/v1/instructors/availability/apply-to-date-range",
        json={
            "from_week_start": source_week.isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["skipped_past_targets"] > 0
    assert payload["days_written"] > 0

    past_day = anchor_today - timedelta(days=3)
    past_week_start = past_day - timedelta(days=past_day.weekday())
    stored_past = repo.get_week(test_instructor.id, past_week_start)
    past_bits = stored_past.get(past_day)
    if past_bits is None:
        assert True  # Clamp left the row untouched (no bitmap persisted).
    else:
        assert windows_from_bits(past_bits) == []

    future_day = anchor_today + timedelta(days=2)
    future_week_start = future_day - timedelta(days=future_day.weekday())
    stored_future = repo.get_week(test_instructor.id, future_week_start)
    future_bits = stored_future.get(future_day)
    assert future_bits is not None
    assert windows_from_bits(future_bits) == [("09:00:00", "10:00:00")]


def test_week_headers_stable(
    bitmap_client: TestClient,
    test_instructor,
    auth_headers_instructor,
    anchor_today: date,
) -> None:
    week_start = anchor_today - timedelta(days=anchor_today.weekday())
    resp = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200
    assert resp.headers.get("ETag")
    assert resp.headers.get("Access-Control-Expose-Headers")
    assert resp.headers.get("X-Allow-Past") in {"true", "false"}
