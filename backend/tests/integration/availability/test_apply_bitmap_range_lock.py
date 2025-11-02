"""
Test suite for apply-to-date-range endpoint (bitmap copy).

Locks the behavior of copying availability patterns across multiple weeks.
"""

from datetime import date, timedelta
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.main
from app.models import AvailabilityDay, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module
from app.utils.bitset import bits_from_windows, windows_from_bits


@pytest.fixture(autouse=True)
def _bitmap_mode_for_apply_range(monkeypatch: pytest.MonkeyPatch):
    """Ensure bitmap mode is enabled for apply-to-range tests."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    yield


@pytest.fixture
def bitmap_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability enabled."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)

    yield app.main

    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
    reload(availability_service_module)
    reload(availability_routes)
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
    windows_by_day: dict[date, list[tuple[str, str]]],
) -> None:
    """Helper to seed bitmap availability for tests."""
    items = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        wins = windows_by_day.get(day, [])
        items.append((day, bits_from_windows(wins) if wins else bits_from_windows([])))
    repo.upsert_week(instructor_id, items)


class TestApplyBitmapPatternAcrossWeeksExactCopy:
    """Test that apply-to-date-range copies patterns exactly."""

    def test_apply_bitmap_pattern_across_weeks_exact_copy(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        """Apply pattern across 4 weeks; each target week equals source bit-for-bit."""
        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        # Seed source week with a pattern (Mon/Wed/Fri windows)
        source_week = date(2025, 11, 3)  # Monday
        monday = source_week
        wednesday = source_week + timedelta(days=2)
        friday = source_week + timedelta(days=4)

        source_windows = {
            monday: [("09:00:00", "10:00:00")],
            wednesday: [("14:00:00", "15:00:00")],
            friday: [("16:00:00", "17:00:00")],
        }

        _upsert_week(repo, test_instructor.id, source_week, source_windows)
        db.commit()

        # POST /instructors/availability/apply-to-date-range to extend 4 weeks
        start_date = source_week + timedelta(days=7)  # Next week Monday
        end_date = start_date + timedelta(days=27)  # 4 weeks later (28 days inclusive)

        apply_resp = bitmap_client.post(
            "/instructors/availability/apply-to-date-range",
            json={
                "from_week_start": source_week.isoformat(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            headers=auth_headers_instructor,
        )

        assert apply_resp.status_code == 200
        apply_body = apply_resp.json()
        # weeks_applied is calculated from date range: (28 days + 6) // 7 = 4
        assert apply_body.get("weeks_applied") == 4
        # When source has bits, should create windows and write days
        assert apply_body.get("windows_created", 0) > 0
        assert apply_body.get("days_written", 0) > 0

        # For each target week Monday, GET /week equals the source bit pattern bit-for-bit
        seen_etags: set[str] = set()
        week_offsets = [0, 1, 2, 3]
        expected_windows = {
            0: [("09:00:00", "10:00:00")],
            2: [("14:00:00", "15:00:00")],
            4: [("16:00:00", "17:00:00")],
        }

        for week_offset in week_offsets:
            target_week_start = start_date + timedelta(days=7 * week_offset)
            # Align to Monday
            days_since_monday = target_week_start.weekday()
            target_monday = target_week_start - timedelta(days=days_since_monday)

            get_resp = bitmap_client.get(
                "/instructors/availability/week",
                params={"start_date": target_monday.isoformat()},
                headers=auth_headers_instructor,
            )
            assert get_resp.status_code == 200
            week_body = get_resp.json()

            # Check pattern matches: Mon/Wed/Fri should have windows, other days empty
            target_mon = target_monday
            target_wed = target_monday + timedelta(days=2)
            target_fri = target_monday + timedelta(days=4)

            assert week_body[target_mon.isoformat()] == [{"start_time": "09:00:00", "end_time": "10:00:00"}]
            assert week_body[target_wed.isoformat()] == [{"start_time": "14:00:00", "end_time": "15:00:00"}]
            assert week_body[target_fri.isoformat()] == [{"start_time": "16:00:00", "end_time": "17:00:00"}]

            # Other days should be empty
            for offset in [1, 3, 5, 6]:  # Tue, Thu, Sat, Sun
                day = target_monday + timedelta(days=offset)
                assert week_body[day.isoformat()] == []

            # ETag should be present (may be same across weeks if bits are identical)
            etag = get_resp.headers.get("ETag")
            assert etag is not None
            assert len(etag) > 0
            seen_etags.add(etag)

            # Verify database bits equal source pattern bit-for-bit
            stored_week = repo.get_week(test_instructor.id, target_monday)
            for offset, expected_windows_list in expected_windows.items():
                day = target_monday + timedelta(days=offset)
                stored_bits = stored_week.get(day)
                assert stored_bits is not None
                assert windows_from_bits(stored_bits) == expected_windows_list
            for offset in [1, 3, 5, 6]:
                day = target_monday + timedelta(days=offset)
                stored_bits = stored_week.get(day)
                if stored_bits:
                    assert windows_from_bits(stored_bits) == []
                else:
                    assert day not in stored_week

        # Version should be present for each week (identical patterns may yield same ETag)
        assert len(seen_etags) >= 1


class TestApplyBitmapEmptySourceReturnsNoopMessage:
    """Test that apply-to-date-range handles empty source week correctly."""

    def test_apply_bitmap_empty_source_returns_noop_message(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        """Apply range with empty source week returns noop message."""
        repo = AvailabilityDayRepository(db)
        # Explicitly clear any pre-seeded rows for this instructor/week
        source_week = date(2025, 11, 10)  # Monday
        db.query(AvailabilityDay).filter(
            AvailabilityDay.instructor_id == test_instructor.id,
            AvailabilityDay.day_date >= source_week,
            AvailabilityDay.day_date < source_week + timedelta(days=7),
        ).delete()
        db.commit()

        # Verify source week has no bitmap rows
        source_bits = repo.get_week(test_instructor.id, source_week)
        assert len(source_bits) == 0

        # Apply range to a future date window
        start_date = source_week + timedelta(days=7)  # Next week Monday
        end_date = start_date + timedelta(days=13)  # 2 weeks later

        apply_resp = bitmap_client.post(
            "/instructors/availability/apply-to-date-range",
            json={
                "from_week_start": source_week.isoformat(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            headers=auth_headers_instructor,
        )

        assert apply_resp.status_code == 200
        apply_body = apply_resp.json()

        # Response JSON message contains exact literal (locking this message)
        message = apply_body.get("message", "")
        assert message == "Source week has no availability bits; nothing applied."

        # Follow-up GET weeks unchanged
        week_offsets = [0, 1]
        for week_offset in week_offsets:
            current_start = start_date + timedelta(days=7 * week_offset)
            target_monday = current_start - timedelta(days=current_start.weekday())

            get_resp = bitmap_client.get(
                "/instructors/availability/week",
                params={"start_date": target_monday.isoformat()},
                headers=auth_headers_instructor,
            )
            assert get_resp.status_code == 200
            week_body = get_resp.json()

            # All days should be empty
            for offset in range(7):
                day = target_monday + timedelta(days=offset)
                assert week_body[day.isoformat()] == []

        # No day writes counted
        assert apply_body.get("days_written", -1) == 0
        assert apply_body.get("windows_created", -1) == 0
