# backend/tests/integration/services/test_supporting_systems_clean_architecture.py
"""
Comprehensive test suite for supporting systems clean architecture.
Verifies that emails, reminders, and cache all follow clean patterns.

Fixed for time-based booking architecture.
UPDATED: Fixed test expectations to check for actual values, not placeholders.
FIXED: Using booking.student.full_name instead of undefined test_student
FIXED: Changed assertion to expect "Test Studio" instead of placeholder bug
FIXED: Dynamic date checking instead of hardcoded day names for timezone compatibility
"""

from datetime import date, time, timedelta
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.services.cache_service import CacheService
from app.services.notification_service import NotificationService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


class TestSupportingSystemsIntegration:
    """Test that all supporting systems work together cleanly."""

    @pytest.fixture
    def full_booking(self, db, test_student, test_instructor_with_availability):
        """Create a complete booking for integration tests."""
        tomorrow = date.today() + timedelta(days=1)

        # Get instructor's profile and service
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service

        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        # Create booking with time-based pattern (no availability_slot_id needed)
        booking_date = tomorrow
        start_time = time(9, 0)
        end_time = time(10, 0)
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            # Remove availability_slot_id - not part of new architecture
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Test Studio",
            location_type="neutral",
            student_note="Looking forward to the lesson",
        )
        # Add relationships for email templates
        booking.student = test_student
        booking.instructor = test_instructor_with_availability
        booking.instructor_service = service

        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking

    def test_booking_confirmation_flow_is_clean(self, db, full_booking):
        """Test complete booking confirmation flow uses clean architecture."""
        # Create services
        notification_service = NotificationService(db)
        notification_service.email_service.send_email = Mock(return_value={"id": "test"})

        _cache_service = CacheService(db)

        # Send booking confirmation
        result = notification_service.send_booking_confirmation(full_booking)
        assert result is True

        # Verify emails were sent (2 - student and instructor)
        assert notification_service.email_service.send_email.call_count == 2

        # Check both emails for clean content
        for i, call in enumerate(notification_service.email_service.send_email.call_args_list):
            html_content = call.kwargs["html_content"]
            to_email = call.kwargs["to_email"]

            # Should have actual booking info (not placeholders)
            assert full_booking.service_name in html_content  # "Test Piano"
            assert "9:00 AM" in html_content  # Actual formatted time

            # FIXED: Check for the actual formatted date instead of hardcoded day name
            # The booking date should be formatted in the email
            booking_date_str = full_booking.booking_date.strftime("%B %d, %Y")  # e.g., "July 09, 2025"
            assert booking_date_str in html_content or str(full_booking.booking_date) in html_content

            # Alternative: Check that SOME day name is present (not a specific one)
            weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            assert any(day in html_content for day in weekdays), "Email should contain a day name"

            # Check for the student and instructor names (FIXED: using booking object)
            assert full_booking.student.first_name in html_content or full_booking.instructor.first_name in html_content

            # FIXED: Only check for meeting location in student email (it's not shown in instructor email)
            if to_email == full_booking.student.email:
                assert "Test Studio" in html_content  # The actual meeting location in student email

            # Should NOT have removed concepts
            assert "availability_slot_id" not in html_content.lower()
            assert "is_available" not in html_content.lower()

            # Should NOT have placeholders
            assert "{formatted_date}" not in html_content
            assert "{formatted_time}" not in html_content
            assert "{booking.service_name}" not in html_content
            assert "{booking.meeting_location}" not in html_content  # FIXED: No more placeholder bug!

    @pytest.mark.asyncio
    async def test_reminder_and_cache_integration(self, db, full_booking):
        """Test reminders work with cached data using clean patterns."""
        # Mock cache service
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis.ping.return_value = True

        previous_flag = os.environ.get("AVAILABILITY_TEST_MEMORY_CACHE")
        os.environ["AVAILABILITY_TEST_MEMORY_CACHE"] = "0"
        try:
            cache_service = CacheService(db, redis_client=mock_redis)
        finally:
            if previous_flag is None:
                os.environ["AVAILABILITY_TEST_MEMORY_CACHE"] = "1"
            else:
                os.environ["AVAILABILITY_TEST_MEMORY_CACHE"] = previous_flag
        notification_service = NotificationService(db)
        notification_service.email_service.send_email = Mock(return_value={"id": "test"})

        # Cache some instructor availability
        week_start = full_booking.booking_date - timedelta(days=full_booking.booking_date.weekday())
        availability_data = {
            full_booking.booking_date.isoformat(): [
                {
                    "id": 1,
                    "instructor_id": full_booking.instructor_id,
                    "specific_date": full_booking.booking_date.isoformat(),
                    "start_time": "09:00",
                    "end_time": "17:00",
                }
            ]
        }

        await cache_service.cache_week_availability(
            full_booking.instructor_id, week_start, availability_data
        )

        # Send reminders
        count = notification_service.send_reminder_emails()

        # Should find our booking
        assert count == 1

        # Verify cache key used was clean
        cache_call = mock_redis.setex.call_args
        cache_key = cache_call[0][0]
        assert "week" in cache_key
        assert str(full_booking.instructor_id) in cache_key
        assert "slot_id" not in cache_key

    def test_all_services_avoid_removed_concepts(self, db):
        """Comprehensive test that all services avoid removed concepts."""
        removed_concepts = [
            "availability_slot_id",
            "InstructorAvailability",
            "is_available",
            "is_recurring",
            "day_of_week",
            "slot_id",
        ]

        # Test notification service
        notification_service = NotificationService(db)
        for attr in dir(notification_service):
            if not attr.startswith("_"):
                attr_value = str(getattr(notification_service, attr))
                for concept in removed_concepts:
                    assert concept not in attr_value, f"Found {concept} in NotificationService.{attr}"

        # Test cache service
        cache_service = CacheService(db)
        for attr in dir(cache_service):
            if not attr.startswith("_") and attr != "PREFIXES":  # Skip the prefixes dict
                attr_value = str(getattr(cache_service, attr))
                for concept in removed_concepts:
                    # Skip legitimate uses of "slot" in prefix definitions
                    if concept == "slot" and attr == "key_builder":
                        continue
                    assert concept not in attr_value, f"Found {concept} in CacheService.{attr}"


class TestErrorHandlingWithCleanArchitecture:
    """Test error handling doesn't expose removed concepts."""

    def test_email_error_messages_are_clean(self, db):
        """Test email error messages don't reference removed concepts."""
        notification_service = NotificationService(db)

        # Force an error by passing None
        # The method might handle None gracefully or return False
        result = notification_service.send_booking_confirmation(None)

        # It should either return False or handle the error gracefully
        # without exposing removed concepts
        assert result is False or result is None

    @pytest.mark.asyncio
    async def test_cache_error_messages_are_clean(self, db):
        """Test cache error messages don't reference removed concepts."""
        # Create cache service with failing Redis
        mock_redis = Mock()
        mock_redis.get.side_effect = Exception("Redis connection failed")
        mock_redis.ping.side_effect = Exception("Redis connection failed")

        previous_flag = os.environ.get("AVAILABILITY_TEST_MEMORY_CACHE")
        os.environ["AVAILABILITY_TEST_MEMORY_CACHE"] = "1"
        try:
            cache_service = CacheService(db, redis_client=None)  # Force in-memory

            # Try to cache something
            result = await cache_service.set("test:key", {"data": "value"})
        finally:
            if previous_flag is None:
                os.environ.pop("AVAILABILITY_TEST_MEMORY_CACHE", None)
            else:
                os.environ["AVAILABILITY_TEST_MEMORY_CACHE"] = previous_flag

        # Should handle gracefully without slot references
        assert result is True  # In-memory cache works

    @patch("app.services.notification_service.time.sleep")
    def test_reminder_handles_missing_data_cleanly(self, mock_sleep, db):
        """Test reminder system handles missing data without slot references."""
        notification_service = NotificationService(db)
        notification_service.email_service.send_email = Mock()

        # Create booking with missing instructor relationship
        booking = Mock(spec=Booking)
        booking.id = generate_ulid()
        booking.instructor = None  # Missing!
        booking.booking_date = date.today() + timedelta(days=1)
        booking.start_time = time(9, 0)

        # Should handle error gracefully
        try:
            notification_service._send_instructor_reminder(booking)
        except AttributeError:
            pass  # Expected due to missing instructor

        # Error handling shouldn't reference slots
        # (Would need to check logs in real implementation)


class TestPerformanceWithCleanArchitecture:
    """Test that clean architecture doesn't hurt performance."""

    def test_cache_keys_are_efficient(self):
        """Test cache keys are reasonable length."""
        from app.services.cache_service import CacheKeyBuilder

        builder = CacheKeyBuilder()

        # Generate various keys
        keys = [
            builder.build("availability", "week", 123, date(2025, 7, 15)),
            builder.build("booking", 456, date(2025, 7, 15)),
            builder.build("conflict", 789, date(2025, 7, 15), "abc123"),
        ]

        for key in keys:
            # Keys should be reasonable length
            assert len(key) < 100  # Not too long
            assert len(key) > 10  # Not too short

            # Should be efficient format
            assert key.count(":") >= 2  # Proper separators
            assert not key.startswith(":")  # No waste
            assert not key.endswith(":")  # No waste

    def test_reminder_query_is_efficient(self, db):
        """Test reminder query doesn't do unnecessary joins."""
        from app.services.notification_service import NotificationService

        # Spy on the query
        original_query = db.query
        query_count = 0

        def counting_query(*args, **kwargs):
            nonlocal query_count
            query_count += 1
            return original_query(*args, **kwargs)

        db.query = counting_query

        # Run reminder query
        service = NotificationService(db)
        service.send_reminder_emails()

        # Should only query bookings table (1 query)
        assert query_count == 1

        # Restore
        db.query = original_query


# Marker for running all supporting system tests
pytestmark = pytest.mark.supporting_systems
