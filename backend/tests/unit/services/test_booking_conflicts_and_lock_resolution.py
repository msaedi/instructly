# backend/tests/unit/services/test_conflicts_locks_coverage_gaps.py
"""
Coverage gap tests for:
- availability_conflicts.py  (lines 144, 147-150, 169, 188-195, 313)
- lock_resolution.py         (lines 39, 253, 257, 286-294, 315-335, 367-376, 394-403)
- conflict_checker_repository.py (lines 133, 137-139, 238-240)
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, RepositoryException
from app.models.booking import Booking, PaymentStatus
from app.models.instructor import InstructorProfile
from app.repositories.conflict_checker_repository import ConflictCheckerRepository
from app.services.booking.availability_conflicts import BookingAvailabilityConflictsMixin
from app.services.booking.lock_resolution import BookingLockResolutionMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeConflictsMixin(BookingAvailabilityConflictsMixin):
    """Minimal concrete class so we can test the mixin methods in isolation."""

    def __init__(self) -> None:  # noqa: D107
        self.db = Mock(spec=Session)
        self.conflict_checker = Mock()

    # Stubs for abstract-like helpers declared in TYPE_CHECKING block
    def _validate_location_capability(self, service: Any, location_type: Optional[str]) -> None:
        pass

    def _validate_service_area(self, booking_data: Any, instructor_id: str, service: Any = None) -> None:
        pass

    def _resolve_lesson_timezone(self, booking_data: Any, instructor_profile: Any) -> str:
        return "America/New_York"

    def _resolve_booking_times_utc(self, booking_date: Any, start_time: Any, end_time: Any, lesson_timezone: str) -> tuple[datetime, datetime]:
        return datetime(2025, 6, 1, 14, 0, tzinfo=timezone.utc), datetime(2025, 6, 1, 15, 0, tzinfo=timezone.utc)

    def _resolve_instructor_timezone(self, instructor_profile: Any) -> str:
        return "America/New_York"

    def _get_advance_notice_minutes(self, location_type: Optional[str] = None) -> int:
        return 120

    def _format_advance_notice(self, minutes: int) -> str:
        return f"{minutes} minutes"

    def _check_overnight_protection(self, booking_time_local: Any, lesson_start_local: Any, location_type: str, instructor_profile: Any) -> None:
        pass

    def _build_conflict_details(self, booking_data: Any, student_id: Optional[str]) -> dict[str, str]:
        return {}


def _make_instructor_profile(preferred_places: Any = None) -> InstructorProfile:
    """Build a mock InstructorProfile with configurable preferred_places on user."""
    profile = Mock(spec=InstructorProfile)
    user = Mock()
    user.preferred_places = preferred_places
    profile.user = user
    return profile


class _FakeLockMixin(BookingLockResolutionMixin):
    """Minimal concrete class to test lock_resolution mixin methods."""

    def __init__(self) -> None:  # noqa: D107
        self.db = Mock(spec=Session)
        self.repository = Mock()
        self.config_service = Mock()

    @contextmanager
    def transaction(self) -> Any:
        yield

    def _ensure_transfer_record(self, booking_id: str) -> Any:
        return Mock()

    def _load_lock_instructor_account(self, booking_id: str, instructor_id: str, payment_repo: Any) -> Optional[str]:
        return "acct_test_123"

    def _load_lock_payout_full_cents(self, booking_id: str, payment_repo: Any, pricing_service: Any) -> Optional[int]:
        return 5000

    @staticmethod
    def _initialize_lock_resolution_result() -> Dict[str, Any]:
        return {
            "payout_success": False,
            "payout_transfer_id": None,
            "payout_amount_cents": None,
            "refund_success": False,
            "refund_data": None,
            "error": None,
        }

    def _lock_credit_already_issued(self, payment_repo: Any, booking_id: str) -> bool:
        return False

    def _record_lock_payout_failure(self, booking_id: str, error: Optional[str]) -> Any:
        return Mock()


def _make_locked_booking(
    payment_status: str = PaymentStatus.LOCKED.value,
    lock_resolved_at: Any = None,
) -> Mock:
    """Build a mock Booking with payment_detail and lock_record support."""
    booking = Mock(spec=Booking)
    booking.id = "01AAAAAAAAAAAAAAAAAAAAAAAAA"
    booking.student_id = "01BBBBBBBBBBBBBBBBBBBBBBBBB"
    booking.instructor_id = "01CCCCCCCCCCCCCCCCCCCCCCCCC"
    booking.hourly_rate = 60.0
    booking.duration_minutes = 60
    booking.student_credit_amount = 0
    booking.refunded_to_card_amount = 0

    pd = Mock()
    pd.payment_status = payment_status
    pd.payment_intent_id = "pi_test_123"
    booking.payment_detail = pd

    return booking


def _make_lock_record(resolved_at: Any = None) -> Mock:
    lock = Mock()
    lock.lock_resolved_at = resolved_at
    lock.locked_amount_cents = 6000
    return lock


# ===========================================================================
# Tests for availability_conflicts.py
# ===========================================================================


class TestGetPrimaryTeachingLocation:
    """Lines 144, 146-150: _get_primary_teaching_location edge cases."""

    def setup_method(self) -> None:
        self.mixin = _FakeConflictsMixin()

    def test_returns_none_when_preferred_places_is_none(self) -> None:
        """Line 144: preferred_places is None -> return None."""
        profile = _make_instructor_profile(preferred_places=None)
        assert self.mixin._get_primary_teaching_location(profile) is None

    def test_returns_none_when_no_teaching_location_kind(self) -> None:
        """Lines 146-150: loop finds no teaching_location kind -> return None."""
        place1 = Mock()
        place1.kind = "home"
        place2 = Mock()
        place2.kind = "studio"
        profile = _make_instructor_profile(preferred_places=[place1, place2])
        assert self.mixin._get_primary_teaching_location(profile) is None

    def test_returns_none_when_user_attr_missing(self) -> None:
        """Line 144 via getattr: profile.user is None -> preferred_places is None."""
        profile = Mock(spec=InstructorProfile)
        profile.user = None
        assert self.mixin._get_primary_teaching_location(profile) is None


class TestResolveAvailabilityLocationFields:
    """Line 169: instructor_location but no teaching place -> (None,None,None,None)."""

    def setup_method(self) -> None:
        self.mixin = _FakeConflictsMixin()

    def test_instructor_location_no_teaching_place(self) -> None:
        """Line 169: _get_primary_teaching_location returns None."""
        # preferred_places has items but none with kind=teaching_location
        place = Mock()
        place.kind = "home"
        profile = _make_instructor_profile(preferred_places=[place])
        result = self.mixin._resolve_availability_location_fields(
            location_type="instructor_location",
            instructor_profile=profile,
        )
        assert result == (None, None, None, None)


class TestFormatConflictReasonTime:
    """Lines 188-195: string and unknown-type branches."""

    def test_valid_time_string(self) -> None:
        """Line 188-191: valid string parses to formatted time."""
        result = BookingAvailabilityConflictsMixin._format_conflict_reason_time("14:30:00")
        assert "2:30 PM" in result

    def test_invalid_time_string_returns_raw(self) -> None:
        """Lines 192-193: ValueError in string_to_time -> returns raw string."""
        result = BookingAvailabilityConflictsMixin._format_conflict_reason_time("not-a-time")
        assert result == "not-a-time"

    def test_non_string_non_time_returns_unknown(self) -> None:
        """Line 195: integer input -> 'Unknown time'."""
        result = BookingAvailabilityConflictsMixin._format_conflict_reason_time(42)
        assert result == "Unknown time"

    def test_none_returns_unknown(self) -> None:
        """Line 195: None input -> 'Unknown time'."""
        result = BookingAvailabilityConflictsMixin._format_conflict_reason_time(None)
        assert result == "Unknown time"


class TestEnforceBookingAdvanceNotice:
    """Line 313: advance notice >= 24*60 min but booking is far enough ahead -> return."""

    def setup_method(self) -> None:
        self.mixin = _FakeConflictsMixin()

    def test_advance_notice_ge24h_booking_far_enough(self) -> None:
        """Line 313: min_advance >= 24*60 and booking is 3 days out -> no exception, return."""
        now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        booking_start = datetime(2025, 6, 5, 12, 0, tzinfo=timezone.utc)
        # Should not raise
        self.mixin._enforce_booking_advance_notice(
            booking_start_utc=booking_start,
            now_utc=now,
            min_advance_minutes=24 * 60,
        )

    def test_advance_notice_ge24h_booking_too_soon_raises(self) -> None:
        """Complementary: booking within 24h window -> raises BusinessRuleException."""
        from app.core.exceptions import BusinessRuleException

        now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        booking_start = datetime(2025, 6, 2, 11, 0, tzinfo=timezone.utc)
        with pytest.raises(BusinessRuleException, match="at least"):
            self.mixin._enforce_booking_advance_notice(
                booking_start_utc=booking_start,
                now_utc=now,
                min_advance_minutes=24 * 60,
            )


# ===========================================================================
# Tests for lock_resolution.py
# ===========================================================================


class TestStripeServiceClass:
    """Line 39: source_cls is mock but facade_cls is not."""

    def test_returns_source_cls_when_facade_real_source_mock(self) -> None:
        """Line 39: _is_mock_like(facade)==False, _is_mock_like(source)==True -> returns source."""
        from app.services.booking.lock_resolution import _is_mock_like, _stripe_service_class

        real_facade = type("RealFacade", (), {})
        real_facade.__module__ = "app.services.booking_service"
        mock_source = MagicMock()
        # MagicMock.__module__ starts with 'unittest.mock'

        # Verify our assumptions about _is_mock_like
        assert _is_mock_like(mock_source) is True
        assert _is_mock_like(real_facade) is False

        # The function does `from .. import stripe_service as stripe_service_module`
        # which resolves to app.services.stripe_service in sys.modules.
        # We need to temporarily replace the real module's StripeService with a mock.
        import app.services.stripe_service as real_stripe_mod

        original_stripe_cls = real_stripe_mod.StripeService
        try:
            real_stripe_mod.StripeService = mock_source  # type: ignore[assignment]
            with patch("app.services.booking.lock_resolution._booking_service_module") as bsm:
                bsm.return_value = Mock(StripeService=real_facade)
                result = _stripe_service_class()
                assert result is mock_source
        finally:
            real_stripe_mod.StripeService = original_stripe_cls  # type: ignore[assignment]


class TestRevalidateLockResolutionState:
    """Lines 315-335: Three early-return paths in _revalidate_lock_resolution_state."""

    def setup_method(self) -> None:
        self.mixin = _FakeLockMixin()

    def test_already_resolved(self) -> None:
        """Lines 315-319: lock_record.lock_resolved_at is set -> already_resolved."""
        booking = _make_locked_booking()
        lock = _make_lock_record(resolved_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.mixin.repository.get_lock_by_booking_id.return_value = lock

        result = self.mixin._revalidate_lock_resolution_state(booking)
        assert result is not None
        assert result["reason"] == "already_resolved"
        assert result["success"] is True
        assert result["skipped"] is True

    def test_already_settled(self) -> None:
        """Lines 323-328: payment_status is SETTLED -> already_settled."""
        booking = _make_locked_booking(payment_status=PaymentStatus.SETTLED.value)
        self.mixin.repository.get_lock_by_booking_id.return_value = _make_lock_record(resolved_at=None)

        result = self.mixin._revalidate_lock_resolution_state(booking)
        assert result is not None
        assert result["reason"] == "already_settled"
        assert result["success"] is True

    def test_not_locked(self) -> None:
        """Lines 330-335: payment_status is AUTHORIZED (not LOCKED) -> not_locked."""
        booking = _make_locked_booking(payment_status="authorized")
        self.mixin.repository.get_lock_by_booking_id.return_value = _make_lock_record(resolved_at=None)

        result = self.mixin._revalidate_lock_resolution_state(booking)
        assert result is not None
        assert result["reason"] == "not_locked"
        assert result["success"] is False

    def test_locked_returns_none(self) -> None:
        """Complementary: payment_status is LOCKED -> returns None (proceed)."""
        booking = _make_locked_booking(payment_status=PaymentStatus.LOCKED.value)
        self.mixin.repository.get_lock_by_booking_id.return_value = _make_lock_record(resolved_at=None)

        result = self.mixin._revalidate_lock_resolution_state(booking)
        assert result is None


class TestPersistLockResolutionResultEdgeCases:
    """Lines 253, 257, 286-294 in _persist_lock_resolution_result."""

    def setup_method(self) -> None:
        self.mixin = _FakeLockMixin()

    def test_booking_not_found_raises(self) -> None:
        """Line 253: get_by_id_for_update returns None -> NotFoundException."""
        self.mixin.repository.get_by_id_for_update.return_value = None

        with pytest.raises(NotFoundException, match="Locked booking not found"):
            self.mixin._persist_lock_resolution_result(
                locked_booking_id="01AAAAAAAAAAAAAAAAAAAAAAAAA",
                resolution="new_lesson_completed",
                resolution_ctx={"lesson_price_cents": 6000, "locked_amount_cents": 6000},
                stripe_result={"payout_success": True},
            )

    def test_stale_result_returns_early(self) -> None:
        """Line 257: _revalidate returns non-None -> returns stale result."""
        booking = _make_locked_booking(payment_status=PaymentStatus.SETTLED.value)
        self.mixin.repository.get_by_id_for_update.return_value = booking
        # lock_record with resolved_at set triggers already_resolved
        lock = _make_lock_record(resolved_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.mixin.repository.get_lock_by_booking_id.return_value = lock

        result = self.mixin._persist_lock_resolution_result(
            locked_booking_id=booking.id,
            resolution="new_lesson_completed",
            resolution_ctx={"lesson_price_cents": 6000, "locked_amount_cents": 6000},
            stripe_result={"payout_success": True},
        )
        assert result["skipped"] is True
        assert result["reason"] == "already_resolved"

    @patch("app.services.booking.lock_resolution._booking_service_module")
    @patch("app.repositories.payment_repository.PaymentRepository", create=True)
    @patch("app.services.credit_service.CreditService", create=True)
    def test_unmapped_resolution_falls_through(
        self, _mock_cs: Mock, _mock_pr: Mock, mock_bsm: Mock
    ) -> None:
        """Lines 286-294: resolution='unknown_type' matches no elif -> falls through to lock_record update."""
        now_mock = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        mock_bsm.return_value = Mock(
            datetime=Mock(now=Mock(return_value=now_mock)),
            timezone=Mock(utc=timezone.utc),
        )

        booking = _make_locked_booking(payment_status=PaymentStatus.LOCKED.value)
        self.mixin.repository.get_by_id_for_update.return_value = booking
        self.mixin.repository.get_lock_by_booking_id.return_value = _make_lock_record(resolved_at=None)
        self.mixin.repository.ensure_payment.return_value = Mock(
            settlement_outcome=None,
            instructor_payout_amount=0,
            credits_reserved_cents=0,
            payment_status=PaymentStatus.LOCKED.value,
        )
        lock_rec = Mock()
        lock_rec.lock_resolution = None
        lock_rec.lock_resolved_at = None
        self.mixin.repository.ensure_lock.return_value = lock_rec

        result = self.mixin._persist_lock_resolution_result(
            locked_booking_id=booking.id,
            resolution="totally_unknown_resolution_type",
            resolution_ctx={"lesson_price_cents": 6000, "locked_amount_cents": 6000},
            stripe_result={"payout_success": False, "error": None},
        )
        assert result["success"] is True
        assert result["resolution"] == "totally_unknown_resolution_type"


class TestGe12CreditAlreadyIssued:
    """Lines 367-376: _persist_ge12_lock_resolution when credit already issued."""

    def setup_method(self) -> None:
        self.mixin = _FakeLockMixin()

    def test_skips_issue_credit_when_already_issued(self) -> None:
        """Line 367->376: _lock_credit_already_issued returns True -> skip issue_credit."""
        self.mixin._lock_credit_already_issued = Mock(return_value=True)  # type: ignore[assignment]
        booking = _make_locked_booking()
        credit_service = Mock()
        payment_repo = Mock()
        locked_bp = Mock()

        self.mixin._persist_ge12_lock_resolution(
            locked_booking=booking,
            locked_booking_id=booking.id,
            lesson_price_cents=6000,
            payment_repo=payment_repo,
            credit_service=credit_service,
            locked_bp=locked_bp,
        )

        credit_service.issue_credit.assert_not_called()
        assert locked_bp.settlement_outcome == "locked_cancel_ge12_full_credit"
        assert locked_bp.payment_status == PaymentStatus.SETTLED.value

    def test_issues_credit_when_not_already_issued(self) -> None:
        """Complementary: _lock_credit_already_issued returns False -> calls issue_credit."""
        self.mixin._lock_credit_already_issued = Mock(return_value=False)  # type: ignore[assignment]
        booking = _make_locked_booking()
        credit_service = Mock()
        payment_repo = Mock()
        locked_bp = Mock()

        self.mixin._persist_ge12_lock_resolution(
            locked_booking=booking,
            locked_booking_id=booking.id,
            lesson_price_cents=6000,
            payment_repo=payment_repo,
            credit_service=credit_service,
            locked_bp=locked_bp,
        )

        credit_service.issue_credit.assert_called_once()


class TestLt12CreditAlreadyIssued:
    """Lines 394-403: _persist_lt12_lock_resolution when credit already issued."""

    def setup_method(self) -> None:
        self.mixin = _FakeLockMixin()

    def test_skips_issue_credit_when_already_issued(self) -> None:
        """Line 394->403: _lock_credit_already_issued returns True -> skip issue_credit."""
        self.mixin._lock_credit_already_issued = Mock(return_value=True)  # type: ignore[assignment]
        booking = _make_locked_booking()
        credit_service = Mock()
        payment_repo = Mock()
        locked_bp = Mock()

        self.mixin._persist_lt12_lock_resolution(
            locked_booking=booking,
            locked_booking_id=booking.id,
            lesson_price_cents=6000,
            stripe_result={"payout_success": True, "payout_amount_cents": 3000, "payout_transfer_id": "tr_123"},
            payment_repo=payment_repo,
            credit_service=credit_service,
            locked_bp=locked_bp,
        )

        credit_service.issue_credit.assert_not_called()
        assert locked_bp.settlement_outcome == "locked_cancel_lt12_split_50_50"

    def test_issues_credit_when_not_already_issued(self) -> None:
        """Complementary: _lock_credit_already_issued returns False -> calls issue_credit."""
        self.mixin._lock_credit_already_issued = Mock(return_value=False)  # type: ignore[assignment]
        booking = _make_locked_booking()
        credit_service = Mock()
        payment_repo = Mock()
        locked_bp = Mock()

        self.mixin._persist_lt12_lock_resolution(
            locked_booking=booking,
            locked_booking_id=booking.id,
            lesson_price_cents=6000,
            stripe_result={"payout_success": False, "error": "test_error"},
            payment_repo=payment_repo,
            credit_service=credit_service,
            locked_bp=locked_bp,
        )

        credit_service.issue_credit.assert_called_once()
        # 50% of 6000 = 3000
        call_kwargs = credit_service.issue_credit.call_args
        assert call_kwargs.kwargs.get("amount_cents") == 3000 or call_kwargs[1].get("amount_cents") == 3000


# ===========================================================================
# Tests for conflict_checker_repository.py
# ===========================================================================


class TestConflictCheckerRepositoryEdgeCases:
    """Lines 133, 137-139, 238-240 in ConflictCheckerRepository."""

    def setup_method(self) -> None:
        self.mock_db = Mock(spec=Session)
        self.repo = ConflictCheckerRepository(self.mock_db)

    def test_student_bookings_with_exclude_id(self) -> None:
        """Line 133: exclude_booking_id is truthy -> adds filter."""
        mock_query = Mock()
        self.mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        result = self.repo.get_student_bookings_for_conflict_check(
            student_id="01AAAAAAAAAAAAAAAAAAAAAAAAA",
            check_date=date(2025, 6, 1),
            exclude_booking_id="01BBBBBBBBBBBBBBBBBBBBBBBBB",
        )

        assert result == []
        # The filter is called twice: once for main filters, once for exclude
        assert mock_query.filter.call_count == 2

    def test_student_bookings_db_error_raises_repository_exception(self) -> None:
        """Lines 137-139: exception in query -> RepositoryException."""
        self.mock_db.query.side_effect = RuntimeError("DB connection lost")

        with pytest.raises(RepositoryException, match="Failed to get student conflict bookings"):
            self.repo.get_student_bookings_for_conflict_check(
                student_id="01AAAAAAAAAAAAAAAAAAAAAAAAA",
                check_date=date(2025, 6, 1),
            )

    def test_date_range_db_error_raises_repository_exception(self) -> None:
        """Lines 238-240: exception in get_bookings_for_date_range -> RepositoryException."""
        self.mock_db.query.side_effect = RuntimeError("DB timeout")

        with pytest.raises(RepositoryException, match="Failed to get bookings"):
            self.repo.get_bookings_for_date_range(
                instructor_id="01AAAAAAAAAAAAAAAAAAAAAAAAA",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 7),
            )

    def test_student_bookings_without_exclude_id(self) -> None:
        """Complementary: no exclude_booking_id -> filter called only once."""
        mock_query = Mock()
        self.mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        result = self.repo.get_student_bookings_for_conflict_check(
            student_id="01AAAAAAAAAAAAAAAAAAAAAAAAA",
            check_date=date(2025, 6, 1),
        )

        assert result == []
        # Only the main filter call, no exclude filter
        assert mock_query.filter.call_count == 1
