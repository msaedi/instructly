"""
Test suite for week availability GET/POST endpoints with ETag and conflict handling.

Locks the current bitmap availability behavior including:
- ETag header presence and format
- Access-Control-Expose-Headers
- X-Allow-Past header
- Version conflict detection (409)
- Override behavior
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
from app.utils.bitset import bits_from_windows


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


class TestWeekGetSetsEtagAndAllowPast:
    """Test GET /week endpoint sets ETag and headers correctly."""

    def test_week_get_sets_etag_and_allow_past(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        """GET /week returns 200 with ETag, Access-Control-Expose-Headers, and X-Allow-Past."""
        week_start = date(2025, 11, 3)  # Monday
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        resp = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        assert len(body) == 7  # All 7 days of the week

        # ETag header present and non-empty
        etag = resp.headers.get("ETag")
        assert etag is not None
        assert len(etag) > 0

        # Access-Control-Expose-Headers includes ETag
        expose_headers = resp.headers.get("Access-Control-Expose-Headers", "")
        assert "ETag" in expose_headers

        # X-Allow-Past reflects server setting
        allow_past = resp.headers.get("X-Allow-Past")
        assert allow_past == "true"  # Should match AVAILABILITY_ALLOW_PAST=true

        # Body shape is dict of ISO dates -> arrays (can be empty)
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            day_key = day.isoformat()
            assert day_key in body
            assert isinstance(body[day_key], list)


class TestWeekPostUpdatesBitsAndChangesEtag:
    """Test POST /week updates bits and changes ETag."""

    def test_week_post_200_updates_bits_and_changes_etag(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        """POST with If-Match updates bits and returns new ETag."""
        week_start = date(2025, 11, 10)  # Monday
        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        # Seed bits for Mon 09:00-10:00
        monday = week_start
        tuesday = week_start + timedelta(days=1)
        _upsert_week(repo, test_instructor.id, week_start, {monday: [("09:00:00", "10:00:00")]})
        db.commit()

        # GET and capture etag1
        get_resp = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp.status_code == 200
        etag1 = get_resp.headers.get("ETag")
        assert etag1 is not None

        # POST with If-Match=etag1 and payload adding Tue 10:00-11:00
        post_body = {
            "week_start": week_start.isoformat(),
            "clear_existing": True,
            "schedule": [
                {
                    "date": monday.isoformat(),
                    "start_time": "09:00:00",
                    "end_time": "10:00:00",
                },
                {
                    "date": tuesday.isoformat(),
                    "start_time": "10:00:00",
                    "end_time": "11:00:00",
                },
            ],
        }

        post_resp = bitmap_client.post(
            "/instructors/availability/week",
            json=post_body,
            headers={**auth_headers_instructor, "If-Match": etag1},
        )

        assert post_resp.status_code == 200
        etag2 = post_resp.headers.get("ETag")
        assert etag2 is not None
        assert etag2 != etag1
        expose_headers = post_resp.headers.get("Access-Control-Expose-Headers", "")
        assert "ETag" in expose_headers

        # Follow-up GET reflects both Mon and Tue windows
        get_resp2 = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp2.status_code == 200
        body2 = get_resp2.json()
        assert body2[monday.isoformat()] == [{"start_time": "09:00:00", "end_time": "10:00:00"}]
        assert body2[tuesday.isoformat()] == [{"start_time": "10:00:00", "end_time": "11:00:00"}]


class TestWeekPost409WithStaleIfMatch:
    """Test POST /week returns 409 with stale If-Match header."""

    def test_week_post_409_with_stale_if_match(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        """POST with stale If-Match returns 409 with version_conflict error."""
        week_start = date(2025, 11, 17)  # Monday
        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        # Obtain etagA from GET
        get_resp1 = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp1.status_code == 200
        etagA = get_resp1.headers.get("ETag")
        assert etagA is not None

        # Mutate the week via repo so version changes
        monday = week_start
        _upsert_week(repo, test_instructor.id, week_start, {monday: [("14:00:00", "15:00:00")]})
        db.commit()

        # POST original If-Match=etagA → expect 409
        post_body = {
            "week_start": week_start.isoformat(),
            "clear_existing": True,
            "schedule": [
                {
                    "date": monday.isoformat(),
                    "start_time": "11:00:00",
                    "end_time": "12:00:00",
                }
            ],
        }

        conflict_resp = bitmap_client.post(
            "/instructors/availability/week",
            json=post_body,
            headers={**auth_headers_instructor, "If-Match": etagA},
        )

        assert conflict_resp.status_code == 409
        conflict_json = conflict_resp.json()
        assert isinstance(conflict_json, dict)
        detail = conflict_json.get("detail")
        if isinstance(detail, dict):
            assert detail.get("error") == "version_conflict"

        # The server's latest version should be reflected in both headers and follow-up GET
        server_get = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert server_get.status_code == 200
        server_etag = server_get.headers.get("ETag")
        assert server_etag is not None

        # ETag header with the new version
        new_etag = conflict_resp.headers.get("ETag")
        assert new_etag is not None
        assert new_etag != etagA
        assert new_etag == server_etag
        if isinstance(detail, dict):
            assert detail.get("current_version") == server_etag
        # ETag should be exposed via Access-Control-Expose-Headers
        expose_headers = conflict_resp.headers.get("Access-Control-Expose-Headers", "")
        assert "ETag" in expose_headers
        assert "Last-Modified" in expose_headers
        assert "X-Allow-Past" in expose_headers


class TestWeekPostOverrideTrueBypassesConflict:
    """Test POST /week with override=true bypasses conflict checks."""

    def test_week_post_override_true_bypasses_conflict(
        self,
        bitmap_client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
    ) -> None:
        """POST with override=true succeeds even with stale If-Match."""
        week_start = date(2025, 11, 24)  # Monday
        repo = AvailabilityDayRepository(db)
        db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
        db.commit()

        # Obtain etagA from GET
        get_resp1 = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp1.status_code == 200
        etagA = get_resp1.headers.get("ETag")
        assert etagA is not None

        # Mutate the week via repo
        monday = week_start
        _upsert_week(repo, test_instructor.id, week_start, {monday: [("14:00:00", "15:00:00")]})
        db.commit()

        # POST with override=true (query param) and stale If-Match → expect 200
        post_body = {
            "week_start": week_start.isoformat(),
            "clear_existing": True,
            "schedule": [
                {
                    "date": monday.isoformat(),
                    "start_time": "11:00:00",
                    "end_time": "12:00:00",
                }
            ],
        }

        override_resp = bitmap_client.post(
            "/instructors/availability/week",
            params={"override": "true"},
            json=post_body,
            headers={**auth_headers_instructor, "If-Match": etagA},
        )

        assert override_resp.status_code == 200
        override_etag = override_resp.headers.get("ETag")
        assert override_etag is not None
        assert override_etag != etagA

        # GET reflects changes
        get_resp2 = bitmap_client.get(
            "/instructors/availability/week",
            params={"start_date": week_start.isoformat()},
            headers=auth_headers_instructor,
        )
        assert get_resp2.status_code == 200
        body2 = get_resp2.json()
        assert body2[monday.isoformat()] == [{"start_time": "11:00:00", "end_time": "12:00:00"}]
