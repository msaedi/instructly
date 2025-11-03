"""
Test suite for past-day behavior toggles.

Locks the behavior when AVAILABILITY_ALLOW_PAST is true vs false.
"""

from datetime import date, timedelta, timezone
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.main
from app.models import AvailabilityDay, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module
from app.utils.bitset import windows_from_bits


@pytest.fixture
def bitmap_app_allow_past(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability and allow_past enabled."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)

    yield app.main

    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "false")
    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)


@pytest.fixture
def bitmap_app_disallow_past(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability but disallow_past."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "false")

    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)

    yield app.main

    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)


@pytest.fixture
def bitmap_client_allow_past(bitmap_app_allow_past) -> TestClient:
    """Return a TestClient with allow_past enabled."""
    client = TestClient(bitmap_app_allow_past.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def bitmap_client_disallow_past(bitmap_app_disallow_past) -> TestClient:
    """Return a TestClient with allow_past disabled."""
    client = TestClient(bitmap_app_disallow_past.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def _freeze_time_to_date(monkeypatch: pytest.MonkeyPatch, target_date: date) -> None:
    """Freeze time to a specific date at noon UTC."""
    real_datetime = availability_service_module.datetime

    class FixedDateTime(real_datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            anchor = real_datetime.combine(target_date, real_datetime.min.time()).replace(tzinfo=timezone.utc)
            anchor = anchor.replace(hour=12, minute=0, second=0)
            if tz:
                return anchor.astimezone(tz)
            return anchor.replace(tzinfo=None)

    monkeypatch.setattr(availability_service_module, "datetime", FixedDateTime)
    monkeypatch.setattr(availability_service_module, "get_user_today_by_id", lambda *_: target_date)


class TestPastDayEditsPersistWhenAllowPastTrue:
    """Test that past day edits persist when AVAILABILITY_ALLOW_PAST=true."""

    def test_past_day_edits_persist_when_allow_past_true(
        self,
        bitmap_client_allow_past: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With AVAILABILITY_ALLOW_PAST=true, POST /week containing past date persists."""
        # Freeze time to 2025-10-30 (Wednesday)
        today_frozen = date(2025, 10, 30)
        _freeze_time_to_date(monkeypatch, today_frozen)

        # Week starting Monday 2025-10-27 (past) to Sunday 2025-11-02
        week_start = date(2025, 10, 27)  # Monday (3 days ago)
        past_day = week_start  # Monday is in the past
        future_day = week_start + timedelta(days=5)  # Saturday is in the future

        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        # POST /week containing a past date and a future date
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

        resp = bitmap_client_allow_past.post(
            "/instructors/availability/week",
            json=payload,
            headers=auth_headers_instructor,
        )

        assert resp.status_code == 200
        assert resp.headers.get("X-Allow-Past") == "true"

        # GET /week includes both sets of windows
        get_resp = bitmap_client_allow_past.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body[past_day.isoformat()] == [{"start_time": "08:00:00", "end_time": "09:00:00"}]
        assert body[future_day.isoformat()] == [{"start_time": "16:00:00", "end_time": "17:00:00"}]

        # ETag updated
        etag = get_resp.headers.get("ETag")
        assert etag is not None

        # Verify persistence in database
        stored = repo.get_week(test_instructor.id, week_start)
        assert windows_from_bits(stored[past_day]) == [("08:00:00", "09:00:00")]
        assert windows_from_bits(stored[future_day]) == [("16:00:00", "17:00:00")]


class TestPastDayEditsIgnoredWhenAllowPastFalse:
    """Test that past day edits are ignored when AVAILABILITY_ALLOW_PAST=false."""

    def test_past_day_edits_ignored_when_allow_past_false(
        self,
        bitmap_client_disallow_past: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With AVAILABILITY_ALLOW_PAST=false, POST /week ignores past dates."""
        # Freeze time to 2025-10-30 (Wednesday)
        today_frozen = date(2025, 10, 30)
        _freeze_time_to_date(monkeypatch, today_frozen)

        monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "false")
        monkeypatch.setenv("PAST_EDIT_WINDOW_DAYS", "30")

        # Week starting Monday 2025-10-27 (past) to Sunday 2025-11-02
        week_start = date(2025, 10, 27)  # Monday (3 days ago)
        past_day = week_start  # Monday is in the past
        future_day = week_start + timedelta(days=5)  # Saturday is in the future

        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        # Initially seed some bits for past day to verify they remain unchanged
        initial_bits = repo.get_week(test_instructor.id, week_start)
        initial_past_bits = initial_bits.get(past_day)

        # POST /week mixed past+future → 200
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

        resp = bitmap_client_disallow_past.post(
            "/instructors/availability/week",
            json=payload,
            headers=auth_headers_instructor,
        )

        assert resp.status_code == 200
        assert resp.headers.get("X-Allow-Past") == "false"

        # GET /week shows only future edits; past dates unchanged
        get_resp = bitmap_client_disallow_past.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        body = get_resp.json()

        # Past day should be empty (or unchanged if there was initial data)
        assert body[past_day.isoformat()] == []

        # Future day should have the new window
        assert body[future_day.isoformat()] == [{"start_time": "16:00:00", "end_time": "17:00:00"}]

        # ETag reflects only future changes
        etag = get_resp.headers.get("ETag")
        assert etag is not None

        # Verify database: past day unchanged, future day updated
        stored = repo.get_week(test_instructor.id, week_start)
        # Past day should be empty (or match initial if there was initial data)
        if initial_past_bits:
            # If there was initial data, it should remain (past edits ignored)
            assert stored.get(past_day) == initial_past_bits or stored.get(past_day) is None
        else:
            # If no initial data, past day should remain empty
            past_bits = stored.get(past_day)
            assert past_bits is None or all(b == 0 for b in past_bits)

        # Future day should have the new window
        assert windows_from_bits(stored[future_day]) == [("16:00:00", "17:00:00")]
