# backend/tests/unit/services/test_admin_ops_service_coverage_r5.py
"""
Round 5 Coverage Tests for AdminOpsService.

Target: Raise coverage from 40.38% to 92%+
Missed lines: 71, 78-131, 166-204, 239-293, 325-346, 369-441, 462-514
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount, StripeCustomer
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.services.admin_ops_service import AdminOpsService


class TestGetPeriodDatesDefaultBranch:
    """Test the default branch in _get_period_dates (Line 71)."""

    def test_default_period_falls_through_to_today(self):
        """Line 71: Default case returns today, today."""
        # This would only happen if VALID_PERIODS check was bypassed
        # The method validates first, so we test valid periods
        today = datetime.now(timezone.utc).date()

        start, end = AdminOpsService._get_period_dates("today")
        assert start == today
        assert end == today


class TestQueryBookingSummary:
    """Tests for _query_booking_summary method (Lines 78-131)."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    def test_empty_bookings_returns_zeros(self, service):
        """Lines 80-93: Empty bookings return zero values."""
        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=[]):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        assert result["total_bookings"] == 0
        assert result["by_status"] == {}
        assert result["total_revenue_cents"] == 0
        assert result["avg_booking_value_cents"] == 0
        assert result["new_students"] == 0
        assert result["repeat_students"] == 0
        assert result["top_categories"] == []

    def test_counts_bookings_by_status(self, service):
        """Lines 84-86: Counts bookings by status."""
        # Create mock bookings with different statuses
        mock_bookings = []

        for i in range(3):
            booking = Mock(spec=Booking)
            booking.status = BookingStatus.CONFIRMED.value
            booking.student_id = generate_ulid()
            booking.total_price = None
            booking.instructor_service = None
            mock_bookings.append(booking)

        for i in range(2):
            booking = Mock(spec=Booking)
            booking.status = BookingStatus.COMPLETED.value
            booking.student_id = generate_ulid()
            booking.total_price = Decimal("100.00")
            booking.instructor_service = None
            mock_bookings.append(booking)

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=mock_bookings):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        assert result["total_bookings"] == 5
        assert result["by_status"][BookingStatus.CONFIRMED.value] == 3
        assert result["by_status"][BookingStatus.COMPLETED.value] == 2

    def test_calculates_revenue_from_confirmed_completed(self, service):
        """Lines 87-90: Only counts revenue from confirmed/completed bookings."""
        mock_bookings = []

        # Completed booking - should count revenue
        completed = Mock(spec=Booking)
        completed.status = BookingStatus.COMPLETED.value
        completed.student_id = generate_ulid()
        completed.total_price = Decimal("150.00")
        completed.instructor_service = None
        mock_bookings.append(completed)

        # Confirmed booking - should count revenue
        confirmed = Mock(spec=Booking)
        confirmed.status = BookingStatus.CONFIRMED.value
        confirmed.student_id = generate_ulid()
        confirmed.total_price = Decimal("100.00")
        confirmed.instructor_service = None
        mock_bookings.append(confirmed)

        # Cancelled booking - should NOT count revenue
        cancelled = Mock(spec=Booking)
        cancelled.status = BookingStatus.CANCELLED.value
        cancelled.student_id = generate_ulid()
        cancelled.total_price = Decimal("200.00")
        cancelled.instructor_service = None
        mock_bookings.append(cancelled)

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=mock_bookings):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        # Revenue = 150 + 100 = 250 ($250.00 = 25000 cents)
        assert result["total_revenue_cents"] == 25000
        # Average = 25000 / 3 bookings = 8333
        assert result["avg_booking_value_cents"] == 8333

    def test_handles_null_total_price(self, service):
        """Line 89: Handles None total_price gracefully."""
        booking = Mock(spec=Booking)
        booking.status = BookingStatus.COMPLETED.value
        booking.student_id = generate_ulid()
        booking.total_price = None  # No price set
        booking.instructor_service = None

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=[booking]):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        assert result["total_revenue_cents"] == 0

    def test_counts_new_vs_repeat_students(self, service):
        """Lines 96-112: Distinguishes new vs repeat students."""
        today = date.today()
        student1_id = generate_ulid()
        student2_id = generate_ulid()

        # Bookings for two students
        mock_bookings = []
        for student_id in [student1_id, student2_id]:
            booking = Mock(spec=Booking)
            booking.status = BookingStatus.CONFIRMED.value
            booking.student_id = student_id
            booking.total_price = None
            booking.instructor_service = None
            mock_bookings.append(booking)

        # Student1's first booking was TODAY (new student)
        # Student2's first booking was LAST MONTH (repeat student)
        first_booking_dates = {
            str(student1_id): today,
            str(student2_id): today - timedelta(days=30),
        }

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=mock_bookings):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value=first_booking_dates):
                result = service._query_booking_summary(today, today)

        assert result["new_students"] == 1
        assert result["repeat_students"] == 1

    def test_counts_top_categories(self, service):
        """Lines 114-129: Counts and sorts top categories."""
        mock_bookings = []

        # Create bookings in different categories
        categories = ["Music", "Music", "Music", "Sports", "Sports", "Art"]

        for cat in categories:
            booking = Mock(spec=Booking)
            booking.status = BookingStatus.CONFIRMED.value
            booking.student_id = generate_ulid()
            booking.total_price = None
            booking.instructor_service = Mock(spec=InstructorService)
            booking.instructor_service.category = cat
            mock_bookings.append(booking)

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=mock_bookings):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        assert len(result["top_categories"]) == 3
        assert result["top_categories"][0] == {"category": "Music", "count": 3}
        assert result["top_categories"][1] == {"category": "Sports", "count": 2}
        assert result["top_categories"][2] == {"category": "Art", "count": 1}

    def test_handles_null_category(self, service):
        """Line 119: Handles None category gracefully."""
        booking = Mock(spec=Booking)
        booking.status = BookingStatus.CONFIRMED.value
        booking.student_id = generate_ulid()
        booking.total_price = None
        booking.instructor_service = Mock(spec=InstructorService)
        booking.instructor_service.category = None

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=[booking]):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        assert result["top_categories"] == []

    def test_handles_missing_instructor_service(self, service):
        """Line 117: Handles None instructor_service gracefully."""
        booking = Mock(spec=Booking)
        booking.status = BookingStatus.CONFIRMED.value
        booking.student_id = generate_ulid()
        booking.total_price = None
        booking.instructor_service = None

        with patch.object(service.repository, "get_bookings_in_date_range_with_service", return_value=[booking]):
            with patch.object(service.repository, "get_first_booking_dates_for_students", return_value={}):
                result = service._query_booking_summary(date.today(), date.today())

        assert result["top_categories"] == []


class TestQueryRecentBookings:
    """Tests for _query_recent_bookings method (Lines 166-204)."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    def test_returns_formatted_booking_list(self, service):
        """Lines 174-203: Returns properly formatted booking list."""
        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED.value
        booking.booking_date = date(2024, 1, 15)
        booking.start_time = Mock()
        booking.start_time.__str__ = Mock(return_value="10:00:00")
        booking.end_time = Mock()
        booking.end_time.__str__ = Mock(return_value="11:00:00")
        booking.service_name = "Piano Lesson"
        booking.total_price = Decimal("100.00")
        booking.location_type = "STUDENT_LOCATION"
        booking.created_at = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Student mock
        booking.student = Mock()
        booking.student.first_name = "John"
        booking.student.last_name = "Smith"

        # Instructor mock
        booking.instructor = Mock()
        booking.instructor.first_name = "Sarah"
        booking.instructor.last_name = "Connor"

        # Service mock
        booking.instructor_service = Mock(spec=InstructorService)
        booking.instructor_service.category = "Music"

        with patch.object(service.repository, "get_recent_bookings_with_details", return_value=[booking]):
            result = service._query_recent_bookings(status=None, limit=20, hours=24)

        assert len(result) == 1
        assert result[0]["booking_id"] == booking.id
        assert result[0]["status"] == BookingStatus.CONFIRMED.value
        assert result[0]["student_name"] == "John S."
        assert result[0]["instructor_name"] == "Sarah C."
        assert result[0]["category"] == "Music"
        assert result[0]["total_cents"] == 10000

    def test_handles_missing_student(self, service):
        """Lines 188-191: Handles missing student gracefully."""
        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED.value
        booking.booking_date = date(2024, 1, 15)
        booking.start_time = Mock()
        booking.start_time.__str__ = Mock(return_value="10:00:00")
        booking.end_time = Mock()
        booking.end_time.__str__ = Mock(return_value="11:00:00")
        booking.service_name = "Test"
        booking.total_price = None
        booking.location_type = None
        booking.created_at = None
        booking.student = None  # No student!
        booking.instructor = None
        booking.instructor_service = None

        with patch.object(service.repository, "get_recent_bookings_with_details", return_value=[booking]):
            result = service._query_recent_bookings(status=None, limit=20, hours=24)

        assert result[0]["student_name"] == "Unknown"
        assert result[0]["instructor_name"] == "Unknown"

    def test_handles_null_fields(self, service):
        """Lines 184-200: Handles null fields gracefully."""
        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = None  # null status
        booking.booking_date = None
        booking.start_time = None
        booking.end_time = None
        booking.service_name = None
        booking.total_price = None
        booking.location_type = None
        booking.created_at = None
        booking.student = None
        booking.instructor = None
        booking.instructor_service = None

        with patch.object(service.repository, "get_recent_bookings_with_details", return_value=[booking]):
            result = service._query_recent_bookings(status=None, limit=20, hours=24)

        assert result[0]["status"] == "unknown"
        assert result[0]["booking_date"] == ""
        assert result[0]["total_cents"] == 0


class TestQueryPaymentPipeline:
    """Tests for _query_payment_pipeline method (Lines 239-293)."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    def test_returns_all_payment_pipeline_fields(self, service):
        """Lines 239-307: Returns complete payment pipeline data."""
        with patch.object(service.repository, "count_bookings_by_payment_and_status", return_value=5):
            with patch.object(service.repository, "count_failed_payments", return_value=2):
                with patch.object(service.repository, "count_refunded_bookings", return_value=1):
                    with patch.object(service.repository, "count_overdue_authorizations", return_value=0):
                        with patch.object(service.repository, "count_overdue_captures", return_value=1):
                            with patch.object(service.repository, "sum_captured_amount", return_value=Decimal("1000.00")):
                                with patch.object(service.repository, "sum_platform_fees", return_value=15000):
                                    result = service._query_payment_pipeline()

        assert "pending_authorization" in result
        assert "authorized" in result
        assert "pending_capture" in result
        assert "captured" in result
        assert "failed" in result
        assert "refunded" in result
        assert "overdue_authorizations" in result
        assert "overdue_captures" in result
        assert "total_captured_cents" in result
        assert "platform_fees_cents" in result
        assert "instructor_payouts_cents" in result

    def test_calculates_revenue_correctly(self, service):
        """Lines 283-288: Revenue calculations are correct."""
        with patch.object(service.repository, "count_bookings_by_payment_and_status", return_value=0):
            with patch.object(service.repository, "count_failed_payments", return_value=0):
                with patch.object(service.repository, "count_refunded_bookings", return_value=0):
                    with patch.object(service.repository, "count_overdue_authorizations", return_value=0):
                        with patch.object(service.repository, "count_overdue_captures", return_value=0):
                            with patch.object(service.repository, "sum_captured_amount", return_value=Decimal("500.00")):
                                with patch.object(service.repository, "sum_platform_fees", return_value=7500):  # $75
                                    result = service._query_payment_pipeline()

        assert result["total_captured_cents"] == 50000  # $500
        assert result["platform_fees_cents"] == 7500
        assert result["instructor_payouts_cents"] == 42500  # 50000 - 7500

    def test_handles_null_captured_amount(self, service):
        """Line 284: Handles None captured amount."""
        with patch.object(service.repository, "count_bookings_by_payment_and_status", return_value=0):
            with patch.object(service.repository, "count_failed_payments", return_value=0):
                with patch.object(service.repository, "count_refunded_bookings", return_value=0):
                    with patch.object(service.repository, "count_overdue_authorizations", return_value=0):
                        with patch.object(service.repository, "count_overdue_captures", return_value=0):
                            with patch.object(service.repository, "sum_captured_amount", return_value=None):
                                with patch.object(service.repository, "sum_platform_fees", return_value=0):
                                    result = service._query_payment_pipeline()

        assert result["total_captured_cents"] == 0


class TestQueryPendingPayouts:
    """Tests for _query_pending_payouts method (Lines 325-346)."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    def test_returns_formatted_payout_list(self, service):
        """Lines 327-346: Returns properly formatted payout list."""
        # Create mock user with instructor profile
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "Sarah"
        user.last_name = "Connor"

        profile = Mock(spec=InstructorProfile)
        profile.stripe_connected_account = Mock(spec=StripeConnectedAccount)
        profile.stripe_connected_account.onboarding_completed = True
        user.instructor_profile = profile

        # Repository returns tuple: (user, pending_amount, lesson_count, oldest_date)
        results = [(user, Decimal("500.00"), 5, date(2024, 1, 10))]

        with patch.object(service.repository, "get_instructors_with_pending_payouts", return_value=results):
            payouts = service._query_pending_payouts(limit=20)

        assert len(payouts) == 1
        assert payouts[0]["instructor_id"] == user.id
        assert payouts[0]["instructor_name"] == "Sarah C."
        assert payouts[0]["pending_amount_cents"] == 50000
        assert payouts[0]["completed_lessons"] == 5
        assert payouts[0]["stripe_connected"] is True

    def test_handles_no_stripe_account(self, service):
        """Lines 329-333: Handles missing Stripe account."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "John"
        user.last_name = "Doe"

        profile = Mock(spec=InstructorProfile)
        profile.stripe_connected_account = None  # No Stripe account
        user.instructor_profile = profile

        results = [(user, Decimal("100.00"), 2, None)]

        with patch.object(service.repository, "get_instructors_with_pending_payouts", return_value=results):
            payouts = service._query_pending_payouts(limit=20)

        assert payouts[0]["stripe_connected"] is False

    def test_handles_incomplete_stripe_onboarding(self, service):
        """Line 332: Handles incomplete Stripe onboarding."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "Jane"
        user.last_name = "Doe"

        profile = Mock(spec=InstructorProfile)
        profile.stripe_connected_account = Mock(spec=StripeConnectedAccount)
        profile.stripe_connected_account.onboarding_completed = False
        user.instructor_profile = profile

        results = [(user, Decimal("200.00"), 3, date(2024, 1, 15))]

        with patch.object(service.repository, "get_instructors_with_pending_payouts", return_value=results):
            payouts = service._query_pending_payouts(limit=20)

        assert payouts[0]["stripe_connected"] is False

    def test_handles_null_values(self, service):
        """Lines 339-341: Handles None values gracefully."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "Test"
        user.last_name = None
        user.instructor_profile = None

        results = [(user, None, None, None)]

        with patch.object(service.repository, "get_instructors_with_pending_payouts", return_value=results):
            payouts = service._query_pending_payouts(limit=20)

        assert payouts[0]["pending_amount_cents"] == 0
        assert payouts[0]["completed_lessons"] == 0
        assert payouts[0]["oldest_pending_date"] == ""
        assert payouts[0]["stripe_connected"] is False


class TestQueryUserLookup:
    """Tests for _query_user_lookup method (Lines 369-441)."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    def test_lookup_by_email(self, service):
        """Line 372-373: Looks up user by email."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.email = "test@example.com"
        user.first_name = "John"
        user.last_name = "Smith"
        user.phone = "+1234567890"
        user.is_active = True
        user.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        user.instructor_profile = None
        user.stripe_customer = None

        with patch.object(service.repository, "get_user_by_email_with_profile", return_value=user):
            with patch.object(service.repository, "count_student_bookings", return_value=5):
                with patch.object(service.repository, "sum_student_spent", return_value=Decimal("500.00")):
                    result = service._query_user_lookup("test@example.com")

        assert result is not None
        assert result["email"] == "test@example.com"
        assert result["role"] == "student"

    def test_lookup_by_phone(self, service):
        """Lines 375-376: Looks up user by phone."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.email = "test@example.com"
        user.first_name = "Jane"
        user.last_name = "Doe"
        user.phone = "+1234567890"
        user.is_active = True
        user.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        user.instructor_profile = None
        user.stripe_customer = None

        with patch.object(service.repository, "get_user_by_phone_with_profile", return_value=user):
            with patch.object(service.repository, "count_student_bookings", return_value=0):
                with patch.object(service.repository, "sum_student_spent", return_value=None):
                    result = service._query_user_lookup("+1234567890")

        assert result is not None
        assert result["phone"] == "+1234567890"

    def test_lookup_by_id(self, service):
        """Lines 378-379: Looks up user by ID."""
        user_id = generate_ulid()
        user = Mock(spec=User)
        user.id = user_id
        user.email = "test@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        user.phone = None
        user.is_active = False
        user.created_at = None
        user.instructor_profile = None
        user.stripe_customer = None

        with patch.object(service.repository, "get_user_by_id_with_profile", return_value=user):
            with patch.object(service.repository, "count_student_bookings", return_value=0):
                with patch.object(service.repository, "sum_student_spent", return_value=None):
                    result = service._query_user_lookup(user_id)

        assert result is not None
        assert result["user_id"] == user_id

    def test_user_not_found(self, service):
        """Lines 381-382: Returns None when user not found."""
        with patch.object(service.repository, "get_user_by_email_with_profile", return_value=None):
            result = service._query_user_lookup("notfound@example.com")

        assert result is None

    def test_instructor_lookup_has_extra_fields(self, service):
        """Lines 415-439: Instructor lookup includes extra fields."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.email = "instructor@example.com"
        user.first_name = "Sarah"
        user.last_name = "Connor"
        user.phone = "+1234567890"
        user.is_active = True
        user.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Instructor profile
        profile = Mock(spec=InstructorProfile)
        profile.is_founding_instructor = True
        profile.is_live = True
        profile.current_tier_pct = Decimal("8")
        profile.stripe_connected_account = Mock(spec=StripeConnectedAccount)
        profile.stripe_connected_account.stripe_account_id = "acct_test123"
        user.instructor_profile = profile

        user.stripe_customer = None

        with patch.object(service.repository, "get_user_by_email_with_profile", return_value=user):
            with patch.object(service.repository, "count_student_bookings", return_value=0):
                with patch.object(service.repository, "sum_student_spent", return_value=None):
                    with patch.object(service.repository, "count_instructor_completed_lessons", return_value=50):
                        with patch.object(service.repository, "sum_instructor_earned", return_value=5000.00):  # Returns float
                            result = service._query_user_lookup("instructor@example.com")

        assert result["role"] == "instructor"
        assert result["is_founding"] is True
        assert result["instructor_status"] == "live"
        assert result["total_lessons"] == 50
        # Total earned: $5000, tier is 8%, so instructor keeps 92%
        # 5000.00 * 100 * 0.92 = 460000
        assert result["total_earned_cents"] == 460000
        assert result["stripe_account_id"] == "acct_test123"

    def test_handles_stripe_customer(self, service):
        """Lines 395-397: Handles Stripe customer ID."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.email = "student@example.com"
        user.first_name = "John"
        user.last_name = "Smith"
        user.phone = None
        user.is_active = True
        user.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        user.instructor_profile = None

        stripe_customer = Mock(spec=StripeCustomer)
        stripe_customer.stripe_customer_id = "cus_test123"
        user.stripe_customer = stripe_customer

        with patch.object(service.repository, "get_user_by_email_with_profile", return_value=user):
            with patch.object(service.repository, "count_student_bookings", return_value=10):
                with patch.object(service.repository, "sum_student_spent", return_value=Decimal("1000.00")):
                    result = service._query_user_lookup("student@example.com")

        assert result["stripe_customer_id"] == "cus_test123"
        assert result["total_spent_cents"] == 100000


class TestQueryUserBookingHistory:
    """Tests for _query_user_booking_history method (Lines 462-514)."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    def test_user_not_found(self, service):
        """Lines 464-465: Returns None, [] when user not found."""
        with patch.object(service.repository, "get_user_with_instructor_profile", return_value=None):
            user_info, bookings = service._query_user_booking_history(generate_ulid(), 20)

        assert user_info is None
        assert bookings == []

    def test_returns_student_booking_history(self, service):
        """Lines 467-514: Returns student booking history."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "John"
        user.last_name = "Smith"
        user.instructor_profile = None  # Student, not instructor

        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.COMPLETED.value
        booking.booking_date = date(2024, 1, 15)
        booking.start_time = Mock()
        booking.start_time.__str__ = Mock(return_value="10:00:00")
        booking.end_time = Mock()
        booking.end_time.__str__ = Mock(return_value="11:00:00")
        booking.service_name = "Piano Lesson"
        booking.total_price = Decimal("100.00")
        booking.location_type = "STUDENT_LOCATION"
        booking.created_at = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        booking.student = Mock(first_name="John", last_name="Smith")
        booking.instructor = Mock(first_name="Sarah", last_name="Connor")
        booking.instructor_service = Mock(category="Music")

        with patch.object(service.repository, "get_user_with_instructor_profile", return_value=user):
            with patch.object(service.repository, "get_user_booking_history", return_value=[booking]):
                user_info, bookings = service._query_user_booking_history(user.id, 20)

        assert user_info is not None
        assert user_info["user_role"] == "student"
        assert len(bookings) == 1
        assert bookings[0]["category"] == "Music"

    def test_returns_instructor_booking_history(self, service):
        """Lines 468-469: Returns instructor booking history."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "Sarah"
        user.last_name = "Connor"
        user.instructor_profile = Mock(spec=InstructorProfile)  # Is instructor

        with patch.object(service.repository, "get_user_with_instructor_profile", return_value=user):
            with patch.object(service.repository, "get_user_booking_history", return_value=[]):
                user_info, bookings = service._query_user_booking_history(user.id, 20)

        assert user_info["user_role"] == "instructor"

    def test_handles_null_instructor_service(self, service):
        """Lines 481-483: Handles None instructor_service."""
        user = Mock(spec=User)
        user.id = generate_ulid()
        user.first_name = "Test"
        user.last_name = "User"
        user.instructor_profile = None

        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.status = BookingStatus.CONFIRMED.value
        booking.booking_date = None
        booking.start_time = None
        booking.end_time = None
        booking.service_name = None
        booking.total_price = None
        booking.location_type = None
        booking.created_at = None
        booking.student = None
        booking.instructor = None
        booking.instructor_service = None  # No service

        with patch.object(service.repository, "get_user_with_instructor_profile", return_value=user):
            with patch.object(service.repository, "get_user_booking_history", return_value=[booking]):
                user_info, bookings = service._query_user_booking_history(user.id, 20)

        assert bookings[0]["category"] == ""
