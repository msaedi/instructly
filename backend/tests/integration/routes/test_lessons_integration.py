"""Full-stack integration tests for /api/v1/lessons endpoints.

These tests exercise the complete path: HTTP → route → VideoService →
BookingRepository → DB. Only the 100ms HTTP client is faked via
FakeHundredMsClient. Auth is overridden via dependency injection
(standard pattern for route-level tests in this codebase).
"""

from __future__ import annotations

from datetime import datetime as dt, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
from tests.factories.booking_builders import create_booking_pg_safe

from app.api.dependencies.auth import get_current_active_user
from app.integrations.hundredms_client import FakeHundredMsClient
from app.main import fastapi_app as app
from app.models.service_catalog import InstructorService
from app.routes.v1.lessons import get_video_service
from app.services.video_service import VideoService

# ── Helpers ─────────────────────────────────────────────────────────────


async def _sync_to_thread(func, /, *args, **kwargs):
    """Replace asyncio.to_thread: run func synchronously in the event loop.

    The lesson routes use asyncio.to_thread to run VideoService in a thread
    pool. SQLAlchemy sessions aren't thread-safe, so we bypass threading
    and run the service synchronously, sharing the test session safely.
    """
    return func(*args, **kwargs)


def _make_online_booking(
    db: Session,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    start_utc: dt,
    duration_minutes: int = 60,
    status: str = "CONFIRMED",
    location_type: str = "online",
) -> str:
    """Create an online booking with explicit UTC start time."""
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=start_utc.date(),
        start_time=start_utc.time(),
        end_time=(start_utc + timedelta(minutes=duration_minutes)).time(),
        duration_minutes=duration_minutes,
        status=status,
        location_type=location_type,
        allow_overlap=True,
        instructor_timezone="UTC",
        service_name="Test Lesson",
        hourly_rate=50.0,
        total_price=50.0,
        meeting_location="Online",
        service_area="Manhattan",
    )
    db.flush()
    # Persist setup data across service transaction boundaries.
    # VideoService uses a lock-unlock-lock flow that ends the current DB
    # transaction before calling the external provider.
    db.commit()
    db.refresh(booking)
    return booking.id


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def _video_base(client, db):
    """Base fixture: wires up VideoService + settings + asyncio bypass.

    Does NOT set auth — callers must also use _as_student or _as_instructor.
    Yields the TestClient.
    """
    svc = VideoService(db=db, hundredms_client=FakeHundredMsClient())

    app.dependency_overrides[get_video_service] = lambda: svc

    with (
        patch("app.routes.v1.lessons.settings") as mock_settings,
        patch("app.routes.v1.lessons.asyncio") as mock_asyncio,
    ):
        mock_settings.hundredms_enabled = True
        mock_asyncio.to_thread = _sync_to_thread
        yield client

    app.dependency_overrides.pop(get_video_service, None)


@pytest.fixture()
def video_client_student(_video_base, test_student):
    """Video client authenticated as the test student."""
    app.dependency_overrides[get_current_active_user] = lambda: test_student
    yield _video_base
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture()
def video_client_instructor(_video_base, test_instructor):
    """Video client authenticated as the test instructor."""
    app.dependency_overrides[get_current_active_user] = lambda: test_instructor
    yield _video_base
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture()
def video_client_instructor_2(_video_base, test_instructor_2):
    """Video client authenticated as the second test instructor (non-participant)."""
    app.dependency_overrides[get_current_active_user] = lambda: test_instructor_2
    yield _video_base
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture()
def instructor_service_id(db, test_instructor):
    """Get the first InstructorService id for the test instructor."""
    svc = (
        db.query(InstructorService)
        .filter_by(instructor_profile_id=test_instructor.instructor_profile.id)
        .first()
    )
    assert svc is not None, "test_instructor must have at least one service"
    return svc.id


# ── POST /join ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestJoinLessonIntegration:
    """Full-stack join lesson tests (real DB, fake 100ms client)."""

    def test_student_joins_online_lesson(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """Student joins within join window → 200 with auth_token, room_id, role=guest."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        response = video_client_student.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.json()}"
        )
        data = response.json()
        assert data["auth_token"]
        assert data["room_id"]
        assert data["role"] == "guest"
        assert data["booking_id"] == booking_id

    def test_instructor_joins_and_gets_host_role(
        self,
        video_client_instructor,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """Instructor joins → 200 with role=host."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        response = video_client_instructor.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 200
        assert response.json()["role"] == "host"

    def test_non_participant_rejected(
        self,
        video_client_instructor_2,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """Third user cannot join → 404."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        response = video_client_instructor_2.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 404

    def test_join_before_window_opens(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """Booking starts in 2 hours → 400 'not opened yet'."""
        start_utc = dt.now(timezone.utc) + timedelta(hours=2)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        response = video_client_student.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 400
        assert "not opened yet" in response.json()["detail"]

    def test_join_after_window_closes(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """Booking started 70 min ago (grace of 15 min for 60-min lesson expired) → 400."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=70)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        response = video_client_student.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 400
        assert "has closed" in response.json()["detail"]

    def test_in_person_booking_rejected(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """In-person booking → 400 'not an online lesson'."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
            location_type="student_location",
        )

        response = video_client_student.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 400
        assert "not an online lesson" in response.json()["detail"]

    def test_cancelled_booking_rejected(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """Cancelled booking → 400 'not confirmed'."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
            status="CANCELLED",
        )

        response = video_client_student.post(
            f"/api/v1/lessons/{booking_id}/join",
        )

        assert response.status_code == 400
        assert "not confirmed" in response.json()["detail"]


# ── GET /video-session ──────────────────────────────────────────────────


@pytest.mark.integration
class TestGetVideoSessionIntegration:
    """Full-stack video session status tests."""

    def test_get_session_after_join(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """After joining, GET video-session → 200 with room_id."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        # Join first
        join_resp = video_client_student.post(
            f"/api/v1/lessons/{booking_id}/join",
        )
        assert join_resp.status_code == 200
        room_id = join_resp.json()["room_id"]

        # Get session status
        response = video_client_student.get(
            f"/api/v1/lessons/{booking_id}/video-session",
        )

        assert response.status_code == 200
        assert response.json()["room_id"] == room_id

    def test_get_session_before_join(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        instructor_service_id,
    ):
        """No join yet → 404 'No video session found'."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        response = video_client_student.get(
            f"/api/v1/lessons/{booking_id}/video-session",
        )

        assert response.status_code == 404
        assert "No video session found" in response.json()["detail"]

    def test_non_participant_cannot_view_video_session(
        self,
        video_client_student,
        db,
        test_student,
        test_instructor,
        test_instructor_2,
        instructor_service_id,
    ):
        """Third user cannot read another lesson's video session → 404."""
        start_utc = dt.now(timezone.utc) - timedelta(minutes=1)

        booking_id = _make_online_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service_id,
            start_utc=start_utc,
        )

        join_resp = video_client_student.post(f"/api/v1/lessons/{booking_id}/join")
        assert join_resp.status_code == 200

        app.dependency_overrides[get_current_active_user] = lambda: test_instructor_2
        try:
            response = video_client_student.get(f"/api/v1/lessons/{booking_id}/video-session")
        finally:
            app.dependency_overrides[get_current_active_user] = lambda: test_student
        assert response.status_code == 404
