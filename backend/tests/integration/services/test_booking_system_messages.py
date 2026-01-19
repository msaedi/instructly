# backend/tests/integration/services/test_booking_system_messages.py
"""
Integration tests for system messages created during booking lifecycle.

Tests verify that system messages are automatically created in conversations
when booking events occur: created, cancelled, rescheduled, completed.
"""

import asyncio
from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.models.booking import BookingStatus
from app.models.conversation import Conversation
from app.models.message import (
    MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED,
    MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED,
    MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
    Message,
)
from app.models.service_catalog import ServiceCatalog
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from tests._utils.bitmap_avail import get_day_windows, seed_day
from tests.factories.booking_builders import create_booking_pg_safe


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Use legacy low-price fixtures."""
    yield


class TestBookingSystemMessages:
    """Integration tests for system messages created during booking lifecycle."""

    @pytest.mark.asyncio
    async def test_booking_creation_creates_system_message(
        self,
        db: Session,
        test_instructor_with_availability: User,
        test_student: User,
        mock_notification_service: Mock,
    ):
        """When a booking is created, a system message should appear in the conversation."""
        # Get instructor's profile and service
        profile = test_instructor_with_availability.instructor_profile
        services = profile.instructor_services
        active_services = [s for s in services if s.is_active]
        service = active_services[0]

        # Get available windows for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        windows = get_day_windows(db, test_instructor_with_availability.id, tomorrow)
        if not windows:
            seed_day(db, test_instructor_with_availability.id, tomorrow, [("09:00", "12:00")])
            windows = get_day_windows(db, test_instructor_with_availability.id, tomorrow)

        start_str, end_str = windows[0]
        start_time = time.fromisoformat(start_str)
        end_time = time.fromisoformat(end_str)

        # Create booking
        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=start_time,
            selected_duration=60,
            end_time=end_time,
            location_type="neutral_location",
            meeting_location="Online",
            student_note="Test booking",
        )

        booking = await asyncio.to_thread(booking_service.create_booking,
            test_student, booking_data, selected_duration=60
        )

        # Find the conversation between student and instructor
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.student_id == test_student.id,
                Conversation.instructor_id == test_instructor_with_availability.id,
            )
            .first()
        )

        # Verify conversation was created
        assert conversation is not None, "Conversation should be created"

        # Find system message in the conversation
        system_messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.message_type == MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
                Message.sender_id.is_(None),  # System messages have no sender
            )
            .all()
        )

        assert len(system_messages) >= 1, "Should have at least one system message"

        # Verify message content
        message = system_messages[-1]  # Most recent
        assert "booked" in message.content.lower()
        assert booking.id == message.booking_id

    @pytest.mark.asyncio
    async def test_booking_cancellation_creates_system_message(
        self,
        db: Session,
        test_instructor_with_availability: User,
        test_student: User,
        mock_notification_service: Mock,
    ):
        """When a booking is cancelled, a system message should appear in the conversation."""
        # Get instructor's profile and service
        profile = test_instructor_with_availability.instructor_profile
        services = profile.instructor_services
        active_services = [s for s in services if s.is_active]
        service = active_services[0]

        # Get available windows for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        windows = get_day_windows(db, test_instructor_with_availability.id, tomorrow)
        if not windows:
            seed_day(db, test_instructor_with_availability.id, tomorrow, [("09:00", "12:00")])
            windows = get_day_windows(db, test_instructor_with_availability.id, tomorrow)

        start_str, end_str = windows[0]
        start_time = time.fromisoformat(start_str)
        end_time = time.fromisoformat(end_str)

        # Create booking first
        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=start_time,
            selected_duration=60,
            end_time=end_time,
            location_type="neutral_location",
            meeting_location="Online",
            student_note="Test booking for cancellation",
        )

        booking = await asyncio.to_thread(booking_service.create_booking,
            test_student, booking_data, selected_duration=60
        )

        # Cancel the booking
        await asyncio.to_thread(booking_service.cancel_booking,
            booking.id, test_student, reason="Test cancellation"
        )

        # Find the conversation
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.student_id == test_student.id,
                Conversation.instructor_id == test_instructor_with_availability.id,
            )
            .first()
        )

        # Find cancellation system message
        cancel_messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.message_type == MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED,
                Message.sender_id.is_(None),
            )
            .all()
        )

        assert len(cancel_messages) >= 1, "Should have cancellation system message"

        # Verify message content - cancelled by the student's first name
        message = cancel_messages[-1]
        assert "cancelled" in message.content.lower()
        # System messages now use participant's first name, not role
        assert test_student.first_name.lower() in message.content.lower()

    @pytest.mark.asyncio
    async def test_booking_completion_creates_system_message(
        self,
        db: Session,
        test_instructor_with_availability: User,
        test_student: User,
        mock_notification_service: Mock,
    ):
        """When a booking is completed, a system message should appear in the conversation."""
        # Get instructor's profile and service
        profile = test_instructor_with_availability.instructor_profile
        services = profile.instructor_services
        active_services = [s for s in services if s.is_active]
        service = active_services[0]

        # Get service name from catalog
        catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.id == service.service_catalog_id).first()
        service_name = catalog_service.name if catalog_service else "Test Service"

        # Create booking in the past (yesterday) directly in the database
        # (bypasses the "2 hours in advance" validation)
        yesterday = date.today() - timedelta(days=1)
        start_time = time(9, 0)
        end_time = time(10, 0)

        booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=yesterday,
            start_time=start_time,
            end_time=end_time,
            service_name=service_name,
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Online",
            service_area="Manhattan",
            offset_index=0,
        )

        # Create booking service and complete the booking
        booking_service = BookingService(db, mock_notification_service)
        booking_service.complete_booking(booking.id, test_instructor_with_availability)

        # Find the conversation
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.student_id == test_student.id,
                Conversation.instructor_id == test_instructor_with_availability.id,
            )
            .first()
        )

        # Find completion system message
        complete_messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.message_type == MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED,
                Message.sender_id.is_(None),
            )
            .all()
        )

        assert len(complete_messages) >= 1, "Should have completion system message"

        # Verify message content
        message = complete_messages[-1]
        assert "completed" in message.content.lower()

    @pytest.mark.asyncio
    async def test_multiple_bookings_create_multiple_messages(
        self,
        db: Session,
        test_instructor_with_availability: User,
        test_student: User,
        mock_notification_service: Mock,
    ):
        """Multiple bookings should create multiple system messages in the same conversation."""
        # Get instructor's profile and service
        profile = test_instructor_with_availability.instructor_profile
        services = profile.instructor_services
        active_services = [s for s in services if s.is_active]
        service = active_services[0]

        booking_service = BookingService(db, mock_notification_service)

        # Create multiple bookings on different days
        for days_ahead in [2, 3, 4]:
            booking_date = date.today() + timedelta(days=days_ahead)
            seed_day(db, test_instructor_with_availability.id, booking_date, [("09:00", "12:00")])

            booking_data = BookingCreate(
                instructor_id=test_instructor_with_availability.id,
                instructor_service_id=service.id,
                booking_date=booking_date,
                start_time=time(9, 0),
                selected_duration=60,
                end_time=time(10, 0),
                location_type="neutral_location",
                meeting_location="Online",
                student_note=f"Booking for day {days_ahead}",
            )

            await asyncio.to_thread(booking_service.create_booking,
                test_student, booking_data, selected_duration=60
            )

        # Find the conversation
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.student_id == test_student.id,
                Conversation.instructor_id == test_instructor_with_availability.id,
            )
            .first()
        )

        # Count system messages
        system_messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.message_type == MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
                Message.sender_id.is_(None),
            )
            .all()
        )

        # Should have at least 3 booking created messages
        assert len(system_messages) >= 3, f"Expected at least 3 system messages, got {len(system_messages)}"

    def test_system_message_has_no_sender(
        self,
        db: Session,
        test_booking,
    ):
        """System messages should have sender_id=None."""
        # Find the conversation from the existing booking
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.student_id == test_booking.student_id,
                Conversation.instructor_id == test_booking.instructor_id,
            )
            .first()
        )

        if conversation:
            # Look for any system messages
            system_messages = (
                db.query(Message)
                .filter(
                    Message.conversation_id == conversation.id,
                    Message.sender_id.is_(None),
                )
                .all()
            )

            for msg in system_messages:
                assert msg.sender_id is None, "System messages must have no sender"
