"""Lock tests for the bitmap apply-to-date-range endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from importlib import reload

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_seed import next_monday, seed_week_bits

from app.core.config import settings
import app.main
from app.models import AvailabilityDay, User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.services.availability_service as availability_service_module
from app.utils.bitset import windows_from_bits

pytestmark = pytest.mark.usefixtures("bitmap_env_relaxed")


@pytest.fixture
def bitmap_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the application with bitmap availability enabled."""
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)

    yield app.main

    reload(availability_service_module)
    reload(availability_routes)
    reload(app.main)


@pytest.fixture
def bitmap_client(bitmap_app) -> TestClient:
    client = TestClient(bitmap_app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def _prepare_source_week(
    db: Session, instructor_id: str, *, weeks_ahead: int = 1
) -> tuple[date, dict[int, list[tuple[str, str]]]]:
    source_week = next_monday(date.today() + timedelta(days=7 * weeks_ahead))
    pattern = {
        0: [("09:00:00", "10:00:00")],
        2: [("14:00:00", "15:00:00")],
        4: [("16:00:00", "17:00:00")],
    }
    written = seed_week_bits(
        db,
        instructor_id=instructor_id,
        week_start=source_week,
        windows_by_weekday=pattern,
        clear_existing=True,
    )
    assert written == len(pattern)
    return source_week, pattern


class TestApplyBitmapPatternAcrossWeeksExactCopy:
    """Test that apply-to-date-range copies patterns exactly."""

    def test_apply_bitmap_pattern_across_weeks_exact_copy(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        from app.core.config import settings

        source_week, pattern = _prepare_source_week(db, test_instructor.id, weeks_ahead=8)
        assert settings.clamp_copy_to_future is False

        source_bits = repo.get_week(test_instructor.id, source_week)
        for weekday, expected in pattern.items():
            day = source_week + timedelta(days=weekday)
            bits = source_bits.get(day)
            assert bits is not None
            assert windows_from_bits(bits) == expected

        target_start = source_week + timedelta(days=7)
        weeks_to_apply = 4
        week_offsets = list(range(weeks_to_apply))
        target_end = target_start + timedelta(days=7 * weeks_to_apply - 1)

        apply_resp = bitmap_client.post(
            "/api/v1/instructors/availability/apply-to-date-range",
            json={
                "from_week_start": source_week.isoformat(),
                "start_date": target_start.isoformat(),
                "end_date": target_end.isoformat(),
            },
            headers=auth_headers_instructor,
        )
        assert apply_resp.status_code == 200
        apply_body = apply_resp.json()
        assert apply_body.get("weeks_applied") == len(week_offsets)
        assert apply_body.get("weeks_affected") == len(week_offsets)
        windows_per_week = sum(len(windows) for windows in pattern.values())
        expected_windows = windows_per_week * len(week_offsets)
        assert apply_body.get("windows_created") == expected_windows
        assert apply_body.get("days_written") == len(pattern) * len(week_offsets)

        seen_etags: set[str] = set()
        for week_index in week_offsets:
            target_monday = target_start + timedelta(days=7 * week_index)
            get_resp = bitmap_client.get(
                "/api/v1/instructors/availability/week",
                params={"start_date": target_monday.isoformat()},
                headers=auth_headers_instructor,
            )
            assert get_resp.status_code == 200
            week_payload = get_resp.json()
            etag = get_resp.headers.get("ETag")
            assert etag
            seen_etags.add(etag)

            stored_week = repo.get_week(test_instructor.id, target_monday)
            for weekday in range(7):
                target_day = target_monday + timedelta(days=weekday)
                expected = pattern.get(weekday, [])
                bits = stored_week.get(target_day)
                if not bits:
                    assert expected == []
                else:
                    assert windows_from_bits(bits) == expected
                expected_payload = [
                    {"start_time": start, "end_time": end} for start, end in expected
                ]
                day_key = target_day.isoformat()
                if expected_payload:
                    assert day_key in week_payload
                    assert week_payload[day_key] == expected_payload
                else:
                    if settings.include_empty_days_in_tests:
                        assert day_key in week_payload
                        assert week_payload[day_key] == []
                    else:
                        assert day_key not in week_payload

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
        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        source_week = next_monday(date.today() + timedelta(days=7))
        seed_week_bits(
            db,
            instructor_id=test_instructor.id,
            week_start=source_week,
            windows_by_weekday={},
            clear_existing=True,
        )

        target_start = source_week + timedelta(days=7)
        target_end = target_start + timedelta(days=13)

        apply_resp = bitmap_client.post(
            "/api/v1/instructors/availability/apply-to-date-range",
            json={
                "from_week_start": source_week.isoformat(),
                "start_date": target_start.isoformat(),
                "end_date": target_end.isoformat(),
            },
            headers=auth_headers_instructor,
        )
        assert apply_resp.status_code == 200
        apply_body = apply_resp.json()
        assert apply_body.get("message") == "Source week has no availability bits; nothing applied."
        expected_weeks_applied = len(range(0, (target_end - target_start).days + 1, 7))
        assert apply_body.get("weeks_applied") == expected_weeks_applied
        assert apply_body.get("weeks_affected", 0) == 0
        assert apply_body.get("days_written", 0) == 0
        assert apply_body.get("windows_created", 0) == 0
        assert apply_body.get("skipped_past_targets", 0) == 0

        for offset in range(0, (target_end - target_start).days + 1, 7):
            target_monday = target_start + timedelta(days=offset)
            stored_week = repo.get_week(test_instructor.id, target_monday)
            for bits in stored_week.values():
                assert windows_from_bits(bits) == []

            get_resp = bitmap_client.get(
                "/api/v1/instructors/availability/week",
                params={"start_date": target_monday.isoformat()},
                headers=auth_headers_instructor,
            )
            assert get_resp.status_code == 200
        payload = get_resp.json()
        if settings.include_empty_days_in_tests:
            assert len(payload) == 7
            assert all(not entries for entries in payload.values())
        else:
            assert payload == {}
