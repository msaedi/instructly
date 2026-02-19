"""Unit tests for video no-show detection Celery task."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helper: _determine_no_show_type
# ---------------------------------------------------------------------------


class TestDetermineNoShowType:
    """Tests for no-show type determination from video session data."""

    def _make_vs(
        self,
        instructor_joined: bool = False,
        student_joined: bool = False,
    ) -> MagicMock:
        vs = MagicMock()
        vs.instructor_joined_at = (
            datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc) if instructor_joined else None
        )
        vs.student_joined_at = (
            datetime(2024, 6, 15, 14, 1, tzinfo=timezone.utc) if student_joined else None
        )
        return vs

    def test_both_joined_returns_none(self) -> None:
        from app.tasks.video_tasks import _determine_no_show_type

        vs = self._make_vs(instructor_joined=True, student_joined=True)
        assert _determine_no_show_type(vs) is None

    def test_instructor_absent_student_present(self) -> None:
        from app.tasks.video_tasks import _determine_no_show_type

        vs = self._make_vs(instructor_joined=False, student_joined=True)
        assert _determine_no_show_type(vs) == "instructor"

    def test_student_absent_instructor_present(self) -> None:
        from app.tasks.video_tasks import _determine_no_show_type

        vs = self._make_vs(instructor_joined=True, student_joined=False)
        assert _determine_no_show_type(vs) == "student"

    def test_neither_joined_returns_mutual(self) -> None:
        from app.tasks.video_tasks import _determine_no_show_type

        vs = self._make_vs(instructor_joined=False, student_joined=False)
        assert _determine_no_show_type(vs) == "mutual"

    def test_no_video_session_returns_mutual(self) -> None:
        from app.tasks.video_tasks import _determine_no_show_type

        assert _determine_no_show_type(None) == "mutual"


# ---------------------------------------------------------------------------
# Task: detect_video_no_shows
# ---------------------------------------------------------------------------


class TestDetectVideoNoShows:
    """Tests for the Celery task that detects video no-shows."""

    def setup_method(self) -> None:
        self._settings_patcher = patch("app.tasks.video_tasks.settings")
        mock_settings = self._settings_patcher.start()
        mock_settings.hundredms_enabled = True

    def teardown_method(self) -> None:
        self._settings_patcher.stop()

    def _make_booking(
        self,
        booking_id: str = "01HYXZ5G6KFXJKZ9CHQM4E3P7G",
        duration_minutes: int = 60,
        start_minutes_ago: int = 30,
        status: str = "CONFIRMED",
    ) -> MagicMock:
        booking = MagicMock()
        booking.id = booking_id
        booking.duration_minutes = duration_minutes
        booking.status = status
        booking.booking_start_utc = datetime.now(timezone.utc) - timedelta(
            minutes=start_minutes_ago
        )
        return booking

    def _make_video_session(
        self,
        instructor_joined: bool = False,
        student_joined: bool = False,
    ) -> MagicMock:
        vs = MagicMock()
        vs.instructor_joined_at = (
            datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc) if instructor_joined else None
        )
        vs.student_joined_at = (
            datetime(2024, 6, 15, 14, 1, tzinfo=timezone.utc) if student_joined else None
        )
        return vs

    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_empty_candidates(
        self, mock_get_db, mock_factory, mock_svc_cls
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = []
        mock_factory.get_booking_repository.return_value = mock_repo

        result = detect_video_no_shows()

        assert result["processed"] == 0
        assert result["reported"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 0

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_reports_instructor_no_show(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # TESTING-ONLY: revert before production (was start_minutes_ago=30)
        booking = self._make_booking(start_minutes_ago=60, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_repo.get_no_show_by_booking_id.return_value = None
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_svc = MagicMock()
        mock_svc.report_automated_no_show.return_value = {"success": True}
        mock_svc_cls.return_value = mock_svc

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        # Re-read booking under lock still CONFIRMED
        mock_repo.get_by_id.return_value = booking

        result = detect_video_no_shows()

        assert result["reported"] == 1
        mock_svc.report_automated_no_show.assert_called_once()
        call_kwargs = mock_svc.report_automated_no_show.call_args[1]
        assert call_kwargs["no_show_type"] == "instructor"

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_reports_student_no_show(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # TESTING-ONLY: revert before production (was start_minutes_ago=30)
        booking = self._make_booking(start_minutes_ago=60, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=True, student_joined=False)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_repo.get_no_show_by_booking_id.return_value = None
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_svc = MagicMock()
        mock_svc.report_automated_no_show.return_value = {"success": True}
        mock_svc_cls.return_value = mock_svc

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_by_id.return_value = booking

        result = detect_video_no_shows()

        assert result["reported"] == 1
        call_kwargs = mock_svc.report_automated_no_show.call_args[1]
        assert call_kwargs["no_show_type"] == "student"

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_both_joined_skipped(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = self._make_booking(start_minutes_ago=30, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=True, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_factory.get_booking_repository.return_value = mock_repo

        result = detect_video_no_shows()

        assert result["skipped"] >= 1
        mock_svc_cls.return_value.report_automated_no_show.assert_not_called()

    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_within_grace_period_skipped(
        self, mock_get_db, mock_factory, mock_svc_cls
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # 60-min lesson started 10 min ago → grace is 15 min, so still within grace
        booking = self._make_booking(start_minutes_ago=10, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_factory.get_booking_repository.return_value = mock_repo

        result = detect_video_no_shows()

        assert result["skipped"] >= 1
        mock_svc_cls.return_value.report_automated_no_show.assert_not_called()

    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_30min_lesson_shorter_grace(
        self, mock_get_db, mock_factory, mock_svc_cls
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # TESTING-ONLY: revert before production (was start_minutes_ago=10, grace was 7.5min)
        # 30-min lesson → grace = max(30-5, 7.5) = 25min → need >25 min ago
        booking = self._make_booking(start_minutes_ago=30, duration_minutes=30)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_repo.get_no_show_by_booking_id.return_value = None
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_svc = MagicMock()
        mock_svc.report_automated_no_show.return_value = {"success": True}
        mock_svc_cls.return_value = mock_svc

        # Need lock mock for the reporting path
        with patch("app.tasks.video_tasks.booking_lock_sync") as mock_lock:
            mock_lock.return_value.__enter__ = MagicMock(return_value=True)
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            mock_repo.get_by_id.return_value = booking

            result = detect_video_no_shows()

        assert result["reported"] == 1

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_lock_not_acquired_skipped(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = self._make_booking(start_minutes_ago=30, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_factory.get_booking_repository.return_value = mock_repo

        # Lock not acquired
        mock_lock.return_value.__enter__ = MagicMock(return_value=False)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        result = detect_video_no_shows()

        assert result["skipped"] >= 1
        mock_svc_cls.return_value.report_automated_no_show.assert_not_called()

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_already_reported_skipped(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = self._make_booking(start_minutes_ago=30, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_by_id.return_value = booking

        # Already has a no-show report
        existing_no_show = MagicMock()
        existing_no_show.no_show_reported_at = datetime.now(timezone.utc)
        mock_repo.get_no_show_by_booking_id.return_value = existing_no_show

        result = detect_video_no_shows()

        assert result["skipped"] >= 1
        mock_svc_cls.return_value.report_automated_no_show.assert_not_called()

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_status_changed_skipped(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = self._make_booking(start_minutes_ago=30, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)

        # Re-read under lock: status changed to CANCELLED
        refreshed = MagicMock()
        refreshed.status = "CANCELLED"
        mock_repo.get_by_id.return_value = refreshed

        result = detect_video_no_shows()

        assert result["skipped"] >= 1
        mock_svc_cls.return_value.report_automated_no_show.assert_not_called()

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_mutual_no_show_no_video_session(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        """Neither participant clicked Join → no BookingVideoSession → mutual no-show."""
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # TESTING-ONLY: revert before production (was start_minutes_ago=30)
        booking = self._make_booking(start_minutes_ago=60, duration_minutes=60)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, None)]
        mock_repo.get_no_show_by_booking_id.return_value = None
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_svc = MagicMock()
        mock_svc.report_automated_no_show.return_value = {"success": True}
        mock_svc_cls.return_value = mock_svc

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_by_id.return_value = booking

        result = detect_video_no_shows()

        assert result["reported"] == 1
        call_kwargs = mock_svc.report_automated_no_show.call_args[1]
        assert call_kwargs["no_show_type"] == "mutual"

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_mutual_no_show_both_clicked_neither_connected(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        """Video session exists but both joined_at are None → mutual no-show."""
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # TESTING-ONLY: revert before production (was start_minutes_ago=30)
        booking = self._make_booking(start_minutes_ago=60, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=False)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_repo.get_no_show_by_booking_id.return_value = None
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_svc = MagicMock()
        mock_svc.report_automated_no_show.return_value = {"success": True}
        mock_svc_cls.return_value = mock_svc

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_by_id.return_value = booking

        result = detect_video_no_shows()

        assert result["reported"] == 1
        call_kwargs = mock_svc.report_automated_no_show.call_args[1]
        assert call_kwargs["no_show_type"] == "mutual"

    @patch("app.tasks.video_tasks.booking_lock_sync")
    @patch("app.tasks.video_tasks.BookingService")
    @patch("app.tasks.video_tasks.RepositoryFactory")
    @patch("app.tasks.video_tasks.get_db")
    def test_exception_handled(
        self, mock_get_db, mock_factory, mock_svc_cls, mock_lock
    ) -> None:
        from app.tasks.video_tasks import detect_video_no_shows

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # TESTING-ONLY: revert before production (was start_minutes_ago=30)
        booking = self._make_booking(start_minutes_ago=60, duration_minutes=60)
        vs = self._make_video_session(instructor_joined=False, student_joined=True)

        mock_repo = MagicMock()
        mock_repo.get_video_no_show_candidates.return_value = [(booking, vs)]
        mock_repo.get_no_show_by_booking_id.return_value = None
        mock_factory.get_booking_repository.return_value = mock_repo

        mock_lock.return_value.__enter__ = MagicMock(return_value=True)
        mock_lock.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_by_id.return_value = booking

        mock_svc = MagicMock()
        mock_svc.report_automated_no_show.side_effect = RuntimeError("boom")
        mock_svc_cls.return_value = mock_svc

        result = detect_video_no_shows()

        assert result["failed"] == 1
        assert result["reported"] == 0
