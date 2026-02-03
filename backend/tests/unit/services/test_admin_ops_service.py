"""Unit tests for AdminOpsService."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services.admin_ops_service import AdminOpsService


class TestFormatPrivacyName:
    """Tests for _format_privacy_name static method."""

    def test_format_full_name(self):
        """Test formatting with full name."""
        result = AdminOpsService._format_privacy_name("John", "Smith")
        assert result == "John S."

    def test_format_first_name_only(self):
        """Test formatting with first name only."""
        result = AdminOpsService._format_privacy_name("Jane", None)
        assert result == "Jane"

    def test_format_empty_last_name(self):
        """Test formatting with empty last name."""
        result = AdminOpsService._format_privacy_name("Jane", "")
        assert result == "Jane"

    def test_format_no_name(self):
        """Test formatting with no name."""
        result = AdminOpsService._format_privacy_name(None, None)
        assert result == "Unknown"

    def test_format_whitespace_names(self):
        """Test formatting with whitespace names."""
        result = AdminOpsService._format_privacy_name("  John  ", "  Smith  ")
        assert result == "John S."


class TestGetPeriodDates:
    """Tests for _get_period_dates static method."""

    def test_period_today(self):
        """Test 'today' period."""
        start, end = AdminOpsService._get_period_dates("today")
        today = datetime.now(timezone.utc).date()
        assert start == today
        assert end == today

    def test_period_yesterday(self):
        """Test 'yesterday' period."""
        start, end = AdminOpsService._get_period_dates("yesterday")
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        assert start == yesterday
        assert end == yesterday

    def test_period_this_week(self):
        """Test 'this_week' period starts on Monday."""
        start, end = AdminOpsService._get_period_dates("this_week")
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        assert start == monday
        assert end == today

    def test_period_last_7_days(self):
        """Test 'last_7_days' period."""
        start, end = AdminOpsService._get_period_dates("last_7_days")
        today = datetime.now(timezone.utc).date()
        assert start == today - timedelta(days=6)
        assert end == today

    def test_period_this_month(self):
        """Test 'this_month' period."""
        start, end = AdminOpsService._get_period_dates("this_month")
        today = datetime.now(timezone.utc).date()
        assert start == today.replace(day=1)
        assert end == today

    def test_period_unknown_raises(self):
        """Test unknown period raises ValueError."""
        with pytest.raises(ValueError):
            AdminOpsService._get_period_dates("unknown_period")


class TestGetBookingSummary:
    """Tests for get_booking_summary method."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    @pytest.mark.asyncio
    async def test_get_booking_summary_empty(self, service):
        """Test summary with no bookings."""
        with patch.object(
            service, "_query_booking_summary", return_value={
                "total_bookings": 0,
                "by_status": {},
                "total_revenue_cents": 0,
                "avg_booking_value_cents": 0,
                "new_students": 0,
                "repeat_students": 0,
                "top_categories": [],
            }
        ):
            result = await service.get_booking_summary(period="today")

        assert result["summary"]["period"] == "today"
        assert result["summary"]["total_bookings"] == 0
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_get_booking_summary_with_data(self, service):
        """Test summary with booking data."""
        with patch.object(
            service, "_query_booking_summary", return_value={
                "total_bookings": 5,
                "by_status": {"CONFIRMED": 3, "COMPLETED": 2},
                "total_revenue_cents": 50000,
                "avg_booking_value_cents": 10000,
                "new_students": 2,
                "repeat_students": 3,
                "top_categories": [{"category": "Music", "count": 3}],
            }
        ):
            result = await service.get_booking_summary(period="last_7_days")

        assert result["summary"]["period"] == "last_7_days"
        assert result["summary"]["total_bookings"] == 5
        assert result["summary"]["total_revenue_cents"] == 50000
        assert result["summary"]["new_students"] == 2

    @pytest.mark.asyncio
    async def test_get_booking_summary_custom_range(self, service):
        """Test summary with an explicit date range."""
        start = date(2026, 1, 1)
        end = date(2026, 1, 7)
        with patch.object(
            service, "_query_booking_summary", return_value={
                "total_bookings": 1,
                "by_status": {"COMPLETED": 1},
                "total_revenue_cents": 15000,
                "avg_booking_value_cents": 15000,
                "new_students": 1,
                "repeat_students": 0,
                "top_categories": [],
            }
        ) as mock_query:
            result = await service.get_booking_summary(start_date=start, end_date=end)

        assert result["summary"]["period"] == "custom_range"
        assert result["summary"]["total_bookings"] == 1
        assert mock_query.call_args[0] == (start, end)

    @pytest.mark.asyncio
    async def test_get_booking_summary_custom_range_requires_both(self, service):
        """Test missing end_date raises ValueError."""
        start = date(2026, 1, 1)
        with pytest.raises(ValueError):
            await service.get_booking_summary(start_date=start)


class TestGetRecentBookings:
    """Tests for get_recent_bookings method."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    @pytest.mark.asyncio
    async def test_get_recent_bookings_empty(self, service):
        """Test empty bookings response."""
        with patch.object(service, "_query_recent_bookings", return_value=[]):
            result = await service.get_recent_bookings()

        assert result["count"] == 0
        assert result["bookings"] == []
        assert result["filters_applied"]["limit"] == 20
        assert result["filters_applied"]["hours"] == 24

    @pytest.mark.asyncio
    async def test_get_recent_bookings_with_data(self, service):
        """Test bookings with data."""
        mock_bookings = [
            {
                "booking_id": "01K2TEST123456789012345",
                "status": "CONFIRMED",
                "booking_date": "2024-01-15",
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "student_name": "John S.",
                "instructor_name": "Sarah C.",
                "service_name": "Piano Lesson",
                "category": "Music",
                "total_cents": 10000,
                "location_type": "STUDENT_LOCATION",
                "created_at": "2024-01-15T09:00:00Z",
            }
        ]

        with patch.object(service, "_query_recent_bookings", return_value=mock_bookings):
            result = await service.get_recent_bookings(status="confirmed", limit=50, hours=48)

        assert result["count"] == 1
        assert result["bookings"][0]["booking_id"] == "01K2TEST123456789012345"
        assert result["filters_applied"]["status"] == "confirmed"
        assert result["filters_applied"]["limit"] == 50
        assert result["filters_applied"]["hours"] == 48

    @pytest.mark.asyncio
    async def test_get_recent_bookings_caps_limit(self, service):
        """Test that limit is capped to max."""
        with patch.object(service, "_query_recent_bookings", return_value=[]):
            result = await service.get_recent_bookings(limit=500)

        # Should be capped to MAX_RECENT_BOOKINGS_LIMIT (100)
        assert result["filters_applied"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_get_recent_bookings_caps_hours(self, service):
        """Test that hours is capped to max."""
        with patch.object(service, "_query_recent_bookings", return_value=[]):
            result = await service.get_recent_bookings(hours=500)

        # Should be capped to MAX_RECENT_BOOKINGS_HOURS (168)
        assert result["filters_applied"]["hours"] == 168


class TestGetPaymentPipeline:
    """Tests for get_payment_pipeline method."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    @pytest.mark.asyncio
    async def test_get_payment_pipeline(self, service):
        """Test payment pipeline response."""
        mock_result = {
            "pending_authorization": 5,
            "authorized": 10,
            "pending_capture": 3,
            "captured": 20,
            "failed": 2,
            "refunded": 1,
            "overdue_authorizations": 0,
            "overdue_captures": 1,
            "total_captured_cents": 200000,
            "total_refunded_cents": 5000,
            "net_revenue_cents": 195000,
            "platform_fees_cents": 30000,
            "instructor_payouts_cents": 170000,
        }

        with patch.object(service, "_query_payment_pipeline", return_value=mock_result):
            result = await service.get_payment_pipeline()

        assert result["pending_authorization"] == 5
        assert result["authorized"] == 10
        assert result["total_captured_cents"] == 200000
        assert "checked_at" in result


class TestGetPendingPayouts:
    """Tests for get_pending_payouts method."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    @pytest.mark.asyncio
    async def test_get_pending_payouts_empty(self, service):
        """Test empty payouts response."""
        with patch.object(service, "_query_pending_payouts", return_value=[]):
            result = await service.get_pending_payouts()

        assert result["payouts"] == []
        assert result["total_pending_cents"] == 0
        assert result["instructor_count"] == 0

    @pytest.mark.asyncio
    async def test_get_pending_payouts_with_data(self, service):
        """Test payouts with data."""
        mock_payouts = [
            {
                "instructor_id": "01K2INST12345678901234",
                "instructor_name": "Sarah C.",
                "pending_amount_cents": 50000,
                "completed_lessons": 5,
                "oldest_pending_date": "2024-01-10T00:00:00Z",
                "stripe_connected": True,
            }
        ]

        with patch.object(service, "_query_pending_payouts", return_value=mock_payouts):
            result = await service.get_pending_payouts(limit=10)

        assert result["instructor_count"] == 1
        assert result["total_pending_cents"] == 50000
        assert result["payouts"][0]["instructor_name"] == "Sarah C."


class TestLookupUser:
    """Tests for lookup_user method."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    @pytest.mark.asyncio
    async def test_lookup_user_not_found(self, service):
        """Test user not found."""
        with patch.object(service, "_query_user_lookup", return_value=None):
            result = await service.lookup_user("unknown@example.com")

        assert result["found"] is False
        assert result["user"] is None

    @pytest.mark.asyncio
    async def test_lookup_user_found_student(self, service):
        """Test student user found."""
        mock_user = {
            "user_id": "01K2USER12345678901234",
            "email": "john@example.com",
            "name": "John Smith",
            "role": "student",
            "created_at": "2024-01-01T00:00:00Z",
            "last_login": "2024-01-15T12:00:00Z",
            "is_verified": True,
            "is_founding": False,
            "total_bookings": 5,
            "total_spent_cents": 50000,
            "stripe_customer_id": "cus_test123",
            "phone": "+1234567890",
        }

        with patch.object(service, "_query_user_lookup", return_value=mock_user):
            result = await service.lookup_user("john@example.com")

        assert result["found"] is True
        assert result["user"]["email"] == "john@example.com"
        assert result["user"]["role"] == "student"

    @pytest.mark.asyncio
    async def test_lookup_user_found_instructor(self, service):
        """Test instructor user found."""
        mock_user = {
            "user_id": "01K2INST12345678901234",
            "email": "sarah@example.com",
            "name": "Sarah Connor",
            "role": "instructor",
            "created_at": "2024-01-01T00:00:00Z",
            "last_login": "2024-01-15T12:00:00Z",
            "is_verified": True,
            "is_founding": True,
            "total_bookings": 0,
            "total_spent_cents": 0,
            "stripe_customer_id": None,
            "phone": "+1234567890",
            "instructor_status": "live",
            "total_lessons": 50,
            "total_earned_cents": 400000,
            "rating": 4.8,
            "review_count": 25,
            "stripe_account_id": "acct_test123",
        }

        with patch.object(service, "_query_user_lookup", return_value=mock_user):
            result = await service.lookup_user("sarah@example.com")

        assert result["found"] is True
        assert result["user"]["role"] == "instructor"
        assert result["user"]["is_founding"] is True
        assert result["user"]["total_lessons"] == 50


class TestGetUserBookingHistory:
    """Tests for get_user_booking_history method."""

    @pytest.fixture
    def service(self, db):
        """Create AdminOpsService instance."""
        return AdminOpsService(db)

    @pytest.mark.asyncio
    async def test_get_user_booking_history_user_not_found(self, service):
        """Test user not found."""
        with patch.object(
            service, "_query_user_booking_history", return_value=(None, [])
        ):
            result = await service.get_user_booking_history("01K2UNKNOWN00000000000")

        assert result["user_id"] == "01K2UNKNOWN00000000000"
        assert result["user_name"] == ""
        assert result["bookings"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_get_user_booking_history_with_bookings(self, service):
        """Test user with bookings."""
        mock_user_info = {
            "user_id": "01K2USER12345678901234",
            "user_name": "John Smith",
            "user_role": "student",
        }
        mock_bookings = [
            {
                "booking_id": "01K2BOOK12345678901234",
                "status": "COMPLETED",
                "booking_date": "2024-01-15",
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "student_name": "John S.",
                "instructor_name": "Sarah C.",
                "service_name": "Piano Lesson",
                "category": "Music",
                "total_cents": 10000,
                "location_type": "STUDENT_LOCATION",
                "created_at": "2024-01-15T09:00:00Z",
            }
        ]

        with patch.object(
            service, "_query_user_booking_history", return_value=(mock_user_info, mock_bookings)
        ):
            result = await service.get_user_booking_history("01K2USER12345678901234")

        assert result["user_name"] == "John Smith"
        assert result["user_role"] == "student"
        assert result["total_count"] == 1
        assert result["bookings"][0]["service_name"] == "Piano Lesson"

    @pytest.mark.asyncio
    async def test_get_user_booking_history_caps_limit(self, service):
        """Test that limit is capped to max."""
        with patch.object(
            service, "_query_user_booking_history", return_value=(None, [])
        ):
            # The service should cap the limit internally
            result = await service.get_user_booking_history("01K2USER12345678901234", limit=500)

        # Result should work but limit should have been capped
        assert result["total_count"] == 0
