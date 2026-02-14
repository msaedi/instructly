"""Tests for satellite table patterns introduced by bookings normalization.

Covers:
- ensure_* IntegrityError retry path
- CHECK constraint violations on satellite tables
- Booking.to_dict() with satellite data loaded/unloaded
- _extract_satellite_fields shared helper
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.base_repository import RepositoryException
from app.schemas.booking import _extract_satellite_fields

# ---------------------------------------------------------------------------
# Test 1: ensure_* IntegrityError retry path
# ---------------------------------------------------------------------------


class TestEnsurePaymentRetry:
    """When two threads call ensure_payment simultaneously, the loser
    should catch IntegrityError, rollback savepoint, and return the
    winner's row."""

    def test_concurrent_create_retries_and_returns_existing(self) -> None:
        from app.repositories.booking_repository import BookingRepository

        mock_db = MagicMock()
        repo = BookingRepository.__new__(BookingRepository)
        repo.db = mock_db
        repo.model = MagicMock()
        repo.logger = MagicMock()

        # First call: no existing row
        mock_db.query.return_value.filter.return_value.one_or_none.side_effect = [
            None,       # initial get_payment_by_booking_id → None
            MagicMock(booking_id="bk_1"),  # retry after IntegrityError → found
        ]

        mock_nested = MagicMock()
        mock_db.begin_nested.return_value = mock_nested

        # flush raises IntegrityError (concurrent insert won)
        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        result = repo.ensure_payment("bk_1")
        assert result is not None
        assert result.booking_id == "bk_1"
        mock_nested.rollback.assert_called_once()

    def test_raises_repository_exception_when_retry_also_fails(self) -> None:
        from app.repositories.booking_repository import BookingRepository

        mock_db = MagicMock()
        repo = BookingRepository.__new__(BookingRepository)
        repo.db = mock_db
        repo.model = MagicMock()
        repo.logger = MagicMock()

        # Both lookups return None
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        mock_nested = MagicMock()
        mock_db.begin_nested.return_value = mock_nested
        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        with pytest.raises(RepositoryException, match="retry"):
            repo.ensure_payment("bk_1")

    def test_non_integrity_error_rolls_back_savepoint(self) -> None:
        """Non-IntegrityError should rollback savepoint and re-raise."""
        from app.repositories.booking_repository import BookingRepository

        mock_db = MagicMock()
        repo = BookingRepository.__new__(BookingRepository)
        repo.db = mock_db
        repo.model = MagicMock()
        repo.logger = MagicMock()

        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        mock_nested = MagicMock()
        mock_db.begin_nested.return_value = mock_nested
        mock_db.flush.side_effect = RuntimeError("deadlock")

        with pytest.raises(RuntimeError, match="deadlock"):
            repo.ensure_payment("bk_1")
        mock_nested.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: CHECK constraint violations (integration — requires DB)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCheckConstraints:
    """Database rejects values not in CHECK constraints."""

    def test_invalid_payment_status_rejected(self, db, test_booking) -> None:
        from app.models.booking_payment import BookingPayment

        bp = BookingPayment(booking_id=test_booking.id, payment_status="BOGUS_STATUS")
        db.add(bp)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_invalid_no_show_type_rejected(self, db, test_booking) -> None:
        from app.models.booking_no_show import BookingNoShow

        ns = BookingNoShow(booking_id=test_booking.id, no_show_type="BOGUS")
        db.add(ns)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_invalid_lock_resolution_rejected(self, db, test_booking) -> None:
        from app.models.booking_lock import BookingLock

        lock = BookingLock(booking_id=test_booking.id, lock_resolution="BOGUS")
        db.add(lock)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


# ---------------------------------------------------------------------------
# Test 3: to_dict() with satellite data
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestToDictWithSatellites:
    """to_dict() correctly includes/excludes satellite fields."""

    def test_to_dict_includes_satellite_fields_when_loaded(self, db, test_booking) -> None:
        from sqlalchemy.orm import selectinload

        from app.models.booking import Booking
        from app.models.booking_no_show import BookingNoShow
        from app.models.booking_payment import BookingPayment

        bp = BookingPayment(booking_id=test_booking.id, payment_status="authorized")
        ns = BookingNoShow(booking_id=test_booking.id, no_show_type="student")
        db.add_all([bp, ns])
        db.flush()

        # Reload with eager loading
        booking = (
            db.query(Booking)
            .options(
                selectinload(Booking.payment_detail),
                selectinload(Booking.no_show_detail),
            )
            .filter(Booking.id == test_booking.id)
            .first()
        )
        assert booking is not None

        d = booking.to_dict()
        assert d.get("payment_status") == "authorized"
        assert d.get("no_show_type") == "student"

    def test_to_dict_handles_missing_satellites(self, db, test_booking) -> None:
        from sqlalchemy.orm import selectinload

        from app.models.booking import Booking

        # No satellites created — just load with options
        booking = (
            db.query(Booking)
            .options(
                selectinload(Booking.payment_detail),
                selectinload(Booking.no_show_detail),
            )
            .filter(Booking.id == test_booking.id)
            .first()
        )
        assert booking is not None
        d = booking.to_dict()
        # Should not raise; satellite fields should be absent or None
        assert d.get("payment_status") is None
        assert d.get("no_show_type") is None


# ---------------------------------------------------------------------------
# Test 4: _extract_satellite_fields shared helper
# ---------------------------------------------------------------------------


class TestExtractSatelliteFields:
    """Shared helper extracts from all satellite relationships."""

    def test_all_satellites_present(self) -> None:
        booking = SimpleNamespace(
            rescheduled_from_booking_id="bk_prev",
            has_locked_funds=True,
            booking_start_utc=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            booking_end_utc=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
            lesson_timezone="America/New_York",
            instructor_tz_at_booking="America/New_York",
            student_tz_at_booking="America/New_York",
            service_area="Manhattan",
            meeting_location="Central Park",
            location_type="neutral_location",
            location_address="123 Park Ave",
            location_lat=40.7,
            location_lng=-73.9,
            location_place_id="ChIJ123",
            student_note="Please bring music",
            instructor_note="Outdoor lesson",
            student_credit_amount=500,
            refunded_to_card_amount=0,
            no_show_detail=SimpleNamespace(
                no_show_reported_by="user_123",
                no_show_reported_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
                no_show_type="student",
                no_show_disputed=False,
                no_show_disputed_at=None,
                no_show_dispute_reason=None,
                no_show_resolved_at=None,
                no_show_resolution=None,
            ),
            lock_detail=SimpleNamespace(
                locked_at=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
                locked_amount_cents=5000,
                lock_resolved_at=None,
                lock_resolution=None,
            ),
            payment_detail=SimpleNamespace(
                settlement_outcome="lesson_completed_full_payout",
                instructor_payout_amount=4400,
                credits_reserved_cents=0,
                auth_scheduled_for=None,
                auth_attempted_at=None,
                auth_failure_count=0,
                auth_last_error=None,
            ),
            reschedule_detail=SimpleNamespace(
                rescheduled_to_booking_id="bk_next",
            ),
        )

        result = _extract_satellite_fields(booking)
        assert result["no_show_type"] == "student"
        assert result["locked_amount_cents"] == 5000
        assert result["settlement_outcome"] == "lesson_completed_full_payout"
        assert result["rescheduled_to_booking_id"] == "bk_next"
        assert result["has_locked_funds"] is True

    def test_all_satellites_none(self) -> None:
        booking = SimpleNamespace(
            rescheduled_from_booking_id=None,
            has_locked_funds=None,
            booking_start_utc=None,
            booking_end_utc=None,
            lesson_timezone=None,
            instructor_tz_at_booking=None,
            student_tz_at_booking=None,
            service_area=None,
            meeting_location=None,
            location_type=None,
            location_address=None,
            location_lat=None,
            location_lng=None,
            location_place_id=None,
            student_note=None,
            instructor_note=None,
            student_credit_amount=None,
            refunded_to_card_amount=None,
            no_show_detail=None,
            lock_detail=None,
            payment_detail=None,
            reschedule_detail=None,
        )

        result = _extract_satellite_fields(booking)
        # Should not raise, all values should be None
        assert result["no_show_type"] is None
        assert result["settlement_outcome"] is None
        assert result["locked_amount_cents"] is None
        assert result["rescheduled_to_booking_id"] is None
