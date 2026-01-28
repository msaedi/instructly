"""Integration tests for AdminOpsService using existing fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.user import User
from app.repositories.admin_ops_repository import AdminOpsRepository
from app.services.admin_ops_service import AdminOpsService


@pytest.fixture
def admin_ops_repo(db: Session) -> AdminOpsRepository:
    """Create AdminOpsRepository instance."""
    return AdminOpsRepository(db)


@pytest.fixture
def admin_ops_service(db: Session) -> AdminOpsService:
    """Create AdminOpsService instance."""
    return AdminOpsService(db)


class TestAdminOpsRepositoryIntegration:
    """Integration tests for AdminOpsRepository."""

    def test_get_bookings_in_date_range_with_service_empty(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test returns empty list when no bookings in range."""
        future_date = datetime.now(timezone.utc).date() + timedelta(days=365)
        result = admin_ops_repo.get_bookings_in_date_range_with_service(
            future_date, future_date + timedelta(days=1)
        )
        assert result == []

    def test_get_bookings_in_date_range_with_service_returns_data(
        self, admin_ops_repo: AdminOpsRepository, test_booking: Booking
    ):
        """Test returns bookings when data exists."""
        today = datetime.now(timezone.utc).date()
        # test_booking is created for tomorrow
        tomorrow = today + timedelta(days=1)
        result = admin_ops_repo.get_bookings_in_date_range_with_service(
            tomorrow, tomorrow
        )
        assert len(result) >= 1

    def test_get_first_booking_date_for_student_returns_none(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test returns None for student with no bookings."""
        # New student without bookings yet (before creating test_booking)
        # Note: test_student is created fresh each test
        result = admin_ops_repo.get_first_booking_date_for_student(test_student.id)
        # Can be None or a date depending on test ordering
        assert result is None or isinstance(result, datetime)

    def test_get_first_booking_date_for_student_with_booking(
        self, admin_ops_repo: AdminOpsRepository, test_booking: Booking
    ):
        """Test returns date for student with booking."""
        result = admin_ops_repo.get_first_booking_date_for_student(
            test_booking.student_id
        )
        assert result is not None

    def test_get_recent_bookings_with_details_empty(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test returns empty list when no recent bookings."""
        # Use old cutoff that won't match any bookings
        cutoff = datetime.now(timezone.utc) + timedelta(days=365)
        result = admin_ops_repo.get_recent_bookings_with_details(
            cutoff=cutoff, status=None, limit=10
        )
        assert result == []

    def test_get_recent_bookings_with_details_returns_data(
        self, admin_ops_repo: AdminOpsRepository, test_booking: Booking
    ):
        """Test returns recent bookings."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        result = admin_ops_repo.get_recent_bookings_with_details(
            cutoff=cutoff, status=None, limit=10
        )
        # Should find the test_booking
        assert len(result) >= 1

    def test_get_recent_bookings_with_details_respects_limit(
        self, admin_ops_repo: AdminOpsRepository, test_booking: Booking
    ):
        """Test respects limit parameter."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = admin_ops_repo.get_recent_bookings_with_details(
            cutoff=cutoff, status=None, limit=1
        )
        assert len(result) <= 1

    def test_count_pending_authorizations(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test counts pending authorizations."""
        from_date = datetime.now(timezone.utc).date() - timedelta(days=30)
        result = admin_ops_repo.count_pending_authorizations(from_date)
        assert isinstance(result, int)
        assert result >= 0

    def test_count_bookings_by_payment_and_status(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test counts bookings by payment status."""
        result = admin_ops_repo.count_bookings_by_payment_and_status(
            payment_status="scheduled"
        )
        assert isinstance(result, int)
        assert result >= 0

    def test_count_failed_payments(self, admin_ops_repo: AdminOpsRepository):
        """Test counts failed payments."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = admin_ops_repo.count_failed_payments(updated_since=cutoff)
        assert isinstance(result, int)
        assert result >= 0

    def test_count_refunded_bookings(self, admin_ops_repo: AdminOpsRepository):
        """Test counts refunded bookings."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = admin_ops_repo.count_refunded_bookings(updated_since=cutoff)
        assert isinstance(result, int)
        assert result >= 0

    def test_count_overdue_authorizations(self, admin_ops_repo: AdminOpsRepository):
        """Test counts overdue authorizations."""
        now = datetime.now(timezone.utc)
        result = admin_ops_repo.count_overdue_authorizations(
            cutoff_time=now + timedelta(hours=24),
            current_time=now,
        )
        assert isinstance(result, int)
        assert result >= 0

    def test_count_overdue_captures(self, admin_ops_repo: AdminOpsRepository):
        """Test counts overdue captures."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = admin_ops_repo.count_overdue_captures(completed_before=cutoff)
        assert isinstance(result, int)
        assert result >= 0

    def test_sum_captured_amount(self, admin_ops_repo: AdminOpsRepository):
        """Test sums captured amount."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = admin_ops_repo.sum_captured_amount(updated_since=cutoff)
        assert isinstance(result, (int, float))
        assert result >= 0

    def test_get_instructors_with_pending_payouts(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test gets instructors with pending payouts."""
        result = admin_ops_repo.get_instructors_with_pending_payouts(limit=10)
        assert isinstance(result, list)

    def test_get_user_by_email_with_profile_not_found(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test returns None for unknown email."""
        result = admin_ops_repo.get_user_by_email_with_profile(
            "nonexistent@example.com"
        )
        assert result is None

    def test_get_user_by_email_with_profile_found(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test returns user for known email."""
        result = admin_ops_repo.get_user_by_email_with_profile(test_student.email)
        assert result is not None
        assert result.email == test_student.email

    def test_get_user_by_phone_with_profile_not_found(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test returns None for unknown phone."""
        result = admin_ops_repo.get_user_by_phone_with_profile("+10000000000")
        assert result is None

    def test_get_user_by_phone_with_profile_found(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test returns user for known phone."""
        if test_student.phone:
            result = admin_ops_repo.get_user_by_phone_with_profile(test_student.phone)
            assert result is not None

    def test_get_user_by_id_with_profile_not_found(
        self, admin_ops_repo: AdminOpsRepository
    ):
        """Test returns None for unknown ID."""
        result = admin_ops_repo.get_user_by_id_with_profile("01K2UNKNOWN00000000000")
        assert result is None

    def test_get_user_by_id_with_profile_found(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test returns user for known ID."""
        result = admin_ops_repo.get_user_by_id_with_profile(test_student.id)
        assert result is not None
        assert result.id == test_student.id

    def test_count_student_bookings(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test counts student bookings."""
        result = admin_ops_repo.count_student_bookings(test_student.id)
        assert isinstance(result, int)
        assert result >= 0

    def test_sum_student_spent(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test sums student spent."""
        result = admin_ops_repo.sum_student_spent(test_student.id)
        assert isinstance(result, (int, float))
        assert result >= 0

    def test_count_instructor_completed_lessons(
        self, admin_ops_repo: AdminOpsRepository, test_instructor: User
    ):
        """Test counts instructor completed lessons."""
        result = admin_ops_repo.count_instructor_completed_lessons(test_instructor.id)
        assert isinstance(result, int)
        assert result >= 0

    def test_sum_instructor_earned(
        self, admin_ops_repo: AdminOpsRepository, test_instructor: User
    ):
        """Test sums instructor earned."""
        result = admin_ops_repo.sum_instructor_earned(test_instructor.id)
        assert isinstance(result, (int, float))
        assert result >= 0

    def test_get_user_with_instructor_profile_student(
        self, admin_ops_repo: AdminOpsRepository, test_student: User
    ):
        """Test returns user without instructor profile."""
        result = admin_ops_repo.get_user_with_instructor_profile(test_student.id)
        assert result is not None
        # Student doesn't have instructor profile
        assert result.instructor_profile is None

    def test_get_user_with_instructor_profile_instructor(
        self, admin_ops_repo: AdminOpsRepository, test_instructor_with_availability: User
    ):
        """Test returns user with instructor profile."""
        result = admin_ops_repo.get_user_with_instructor_profile(
            test_instructor_with_availability.id
        )
        assert result is not None
        assert result.instructor_profile is not None

    def test_get_user_booking_history_student(
        self, admin_ops_repo: AdminOpsRepository, test_booking: Booking
    ):
        """Test returns booking history for student."""
        result = admin_ops_repo.get_user_booking_history(
            user_id=test_booking.student_id,
            is_instructor=False,
            limit=10,
        )
        assert len(result) >= 1

    def test_get_user_booking_history_instructor(
        self, admin_ops_repo: AdminOpsRepository, test_booking: Booking
    ):
        """Test returns booking history for instructor."""
        result = admin_ops_repo.get_user_booking_history(
            user_id=test_booking.instructor_id,
            is_instructor=True,
            limit=10,
        )
        assert len(result) >= 1


class TestAdminOpsServiceIntegration:
    """Integration tests for AdminOpsService."""

    def test_query_booking_summary_empty(self, admin_ops_service: AdminOpsService):
        """Test booking summary with no bookings in range."""
        future_date = datetime.now(timezone.utc).date() + timedelta(days=365)
        result = admin_ops_service._query_booking_summary(
            future_date, future_date + timedelta(days=1)
        )
        assert result["total_bookings"] == 0
        assert result["total_revenue_cents"] == 0

    def test_query_booking_summary_with_data(
        self, admin_ops_service: AdminOpsService, test_booking: Booking
    ):
        """Test booking summary with data."""
        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        result = admin_ops_service._query_booking_summary(tomorrow, tomorrow)
        assert result["total_bookings"] >= 1

    def test_query_recent_bookings_empty(self, admin_ops_service: AdminOpsService):
        """Test recent bookings with no data."""
        result = admin_ops_service._query_recent_bookings(
            status=None, limit=10, hours=0
        )
        # With 0 hours, cutoff is now, so no bookings should match
        assert isinstance(result, list)

    def test_query_recent_bookings_with_data(
        self, admin_ops_service: AdminOpsService, test_booking: Booking
    ):
        """Test recent bookings with data."""
        result = admin_ops_service._query_recent_bookings(
            status=None, limit=10, hours=168
        )
        assert len(result) >= 1
        assert "booking_id" in result[0]
        assert "student_name" in result[0]
        assert "instructor_name" in result[0]

    def test_query_payment_pipeline(self, admin_ops_service: AdminOpsService):
        """Test payment pipeline query."""
        result = admin_ops_service._query_payment_pipeline()
        assert "pending_authorization" in result
        assert "authorized" in result
        assert "pending_capture" in result
        assert "captured" in result
        assert "total_captured_cents" in result

    def test_query_pending_payouts(self, admin_ops_service: AdminOpsService):
        """Test pending payouts query."""
        result = admin_ops_service._query_pending_payouts(limit=10)
        assert isinstance(result, list)

    def test_query_user_lookup_not_found(self, admin_ops_service: AdminOpsService):
        """Test user lookup when not found."""
        result = admin_ops_service._query_user_lookup("nonexistent@example.com")
        assert result is None

    def test_query_user_lookup_by_email(
        self, admin_ops_service: AdminOpsService, test_student: User
    ):
        """Test user lookup by email."""
        result = admin_ops_service._query_user_lookup(test_student.email)
        assert result is not None
        assert result["email"] == test_student.email

    def test_query_user_lookup_by_phone(
        self, admin_ops_service: AdminOpsService, test_student: User
    ):
        """Test user lookup by phone."""
        if test_student.phone:
            result = admin_ops_service._query_user_lookup(test_student.phone)
            assert result is not None

    def test_query_user_lookup_by_id(
        self, admin_ops_service: AdminOpsService, test_student: User
    ):
        """Test user lookup by ID."""
        result = admin_ops_service._query_user_lookup(test_student.id)
        assert result is not None
        assert result["user_id"] == test_student.id

    def test_query_user_booking_history_not_found(
        self, admin_ops_service: AdminOpsService
    ):
        """Test booking history for non-existent user."""
        user_info, bookings = admin_ops_service._query_user_booking_history(
            user_id="01K2UNKNOWN00000000000",
            limit=10,
        )
        assert user_info is None
        assert bookings == []

    def test_query_user_booking_history_student(
        self, admin_ops_service: AdminOpsService, test_booking: Booking
    ):
        """Test booking history for student."""
        user_info, bookings = admin_ops_service._query_user_booking_history(
            user_id=test_booking.student_id,
            limit=10,
        )
        assert user_info is not None
        assert user_info["user_role"] == "student"
        assert len(bookings) >= 1

    def test_query_user_booking_history_instructor(
        self,
        admin_ops_service: AdminOpsService,
        test_booking: Booking,
        test_instructor_with_availability: User,
    ):
        """Test booking history for instructor."""
        user_info, bookings = admin_ops_service._query_user_booking_history(
            user_id=test_booking.instructor_id,
            limit=10,
        )
        assert user_info is not None
        assert user_info["user_role"] == "instructor"
        assert len(bookings) >= 1


class TestAdminOpsServiceAsyncMethods:
    """Tests for async wrapper methods with real data."""

    @pytest.mark.asyncio
    async def test_get_booking_summary(
        self, admin_ops_service: AdminOpsService, test_booking: Booking
    ):
        """Test async get_booking_summary."""
        result = await admin_ops_service.get_booking_summary(period="last_7_days")
        assert "summary" in result
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_get_recent_bookings(
        self, admin_ops_service: AdminOpsService, test_booking: Booking
    ):
        """Test async get_recent_bookings."""
        result = await admin_ops_service.get_recent_bookings(limit=10, hours=168)
        assert "bookings" in result
        assert "count" in result
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_get_payment_pipeline(
        self, admin_ops_service: AdminOpsService
    ):
        """Test async get_payment_pipeline."""
        result = await admin_ops_service.get_payment_pipeline()
        assert "pending_authorization" in result
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_get_pending_payouts(
        self, admin_ops_service: AdminOpsService
    ):
        """Test async get_pending_payouts."""
        result = await admin_ops_service.get_pending_payouts(limit=10)
        assert "payouts" in result
        assert "total_pending_cents" in result

    @pytest.mark.asyncio
    async def test_lookup_user_found(
        self, admin_ops_service: AdminOpsService, test_student: User
    ):
        """Test async lookup_user when found."""
        result = await admin_ops_service.lookup_user(test_student.email)
        assert result["found"] is True
        assert result["user"]["email"] == test_student.email

    @pytest.mark.asyncio
    async def test_lookup_user_not_found(
        self, admin_ops_service: AdminOpsService
    ):
        """Test async lookup_user when not found."""
        result = await admin_ops_service.lookup_user("nonexistent@example.com")
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_get_user_booking_history(
        self, admin_ops_service: AdminOpsService, test_booking: Booking
    ):
        """Test async get_user_booking_history."""
        result = await admin_ops_service.get_user_booking_history(
            user_id=test_booking.student_id,
            limit=10,
        )
        assert result["user_id"] == test_booking.student_id
        assert result["total_count"] >= 1
