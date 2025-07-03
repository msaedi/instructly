# backend/app/models/booking.py
"""
Booking model for InstaInstru platform.

This module defines the Booking model which represents a confirmed lesson
booking between a student and an instructor. The platform uses instant
booking, so bookings are immediately confirmed upon creation.

Key Features:
- Instant booking confirmation (no approval process)
- Self-contained bookings with all necessary data
- Complete independence from availability slots
- Comprehensive booking lifecycle management
- Location type tracking for instructor convenience
- Cancellation tracking with reason and actor

Database Table: bookings
Primary Key: id
Foreign Keys: student_id, instructor_id, service_id, cancelled_by_id

ARCHITECTURAL DESIGN:
Bookings are self-contained records that store all necessary information
(instructor, date, times) directly. This achieves complete layer independence
between availability and bookings. Bookings are commitments that persist
regardless of availability changes.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base

logger = logging.getLogger(__name__)


class BookingStatus(str, Enum):
    """
    Enum for booking statuses throughout the booking lifecycle.

    Note: Since we use instant booking, PENDING should rarely be used.
    All bookings start as CONFIRMED.

    Values:
        PENDING: Reserved for future use (e.g., if approval flow is added)
        CONFIRMED: Default status - booking is immediately confirmed
        COMPLETED: Lesson has been completed successfully
        CANCELLED: Booking was cancelled by student or instructor
        NO_SHOW: Student didn't show up for the lesson
    """

    PENDING = "PENDING"  # Reserved for future use
    CONFIRMED = "CONFIRMED"  # Default - booking is confirmed
    COMPLETED = "COMPLETED"  # Lesson has been completed
    CANCELLED = "CANCELLED"  # Booking was cancelled
    NO_SHOW = "NO_SHOW"  # Student didn't show up


class LocationType(str, Enum):
    """
    Enum for booking location types.

    Helps instructors quickly understand where they need to go
    and helps with logistics planning.

    Values:
        STUDENT_HOME: Lesson will be at student's home/location
        INSTRUCTOR_LOCATION: Lesson will be at instructor's studio/location
        NEUTRAL: Lesson will be at a neutral location (e.g., park, library)
    """

    STUDENT_HOME = "student_home"
    INSTRUCTOR_LOCATION = "instructor_location"
    NEUTRAL = "neutral"


class Booking(Base):
    """
    Model representing a booking between a student and instructor.

    This model handles instant bookings - when a student books a time slot,
    it's immediately confirmed. The booking captures all relevant information
    at the time of booking to maintain historical accuracy.

    Design Principles:
    1. Self-Contained: All booking data (instructor, date, times) stored directly
    2. Snapshot Approach: Service details (name, rate) are copied at booking time
    3. Instant Confirmation: Bookings are confirmed immediately upon creation
    4. Comprehensive Tracking: All state changes are tracked with timestamps
    5. Layer Independence: No references to availability slots

    Attributes:
        Core Fields:
            id: Primary key
            student_id: The student who made the booking
            instructor_id: The instructor providing the service
            service_id: The service being booked

        Booking Data (self-contained):
            booking_date: Date of the lesson (YYYY-MM-DD)
            start_time: Start time of the lesson (HH:MM:SS)
            end_time: End time of the lesson (HH:MM:SS)

        Snapshot Data (preserved for history):
            service_name: Name of service at booking time
            hourly_rate: Rate at booking time (Decimal)
            total_price: Total price calculated (Decimal)
            duration_minutes: Duration in minutes (Integer)

        Booking Details:
            status: Current booking status (BookingStatus enum)
            service_area: NYC area where service is provided
            location_type: Type of location (LocationType enum)
            meeting_location: Specific location/address details
            student_note: Note from student at booking
            instructor_note: Note from instructor (can be added later)

        Timestamps:
            created_at: When booking was made
            updated_at: When booking was last modified
            confirmed_at: When booking was confirmed (same as created for instant)
            completed_at: When lesson was completed
            cancelled_at: When booking was cancelled (if applicable)

        Cancellation Info:
            cancelled_by_id: User ID who cancelled the booking
            cancellation_reason: Reason for cancellation

    Relationships:
        student: User who made the booking
        instructor: User providing the service
        service: Service being provided
        cancelled_by: User who cancelled (if cancelled)
    """

    __tablename__ = "bookings"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign keys
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)

    # Self-contained booking data - NO reference to availability slots
    booking_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Service snapshot data - preserved for historical accuracy
    service_name = Column(String, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    # Status with check constraint
    status = Column(String(20), nullable=False, default=BookingStatus.CONFIRMED, index=True)

    # Location details
    service_area = Column(String, nullable=True)  # e.g., "Manhattan, Brooklyn"
    location_type = Column(String(50), nullable=True, default=LocationType.NEUTRAL)
    meeting_location = Column(Text, nullable=True)  # Detailed address/instructions

    # Communication
    student_note = Column(Text, nullable=True)  # Note provided during booking
    instructor_note = Column(Text, nullable=True)  # Instructor can add notes later

    # Timestamps - all timezone-aware
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())  # Instant booking
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Cancellation details
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Relationships
    student = relationship("User", foreign_keys=[student_id], backref="student_bookings")
    instructor = relationship("User", foreign_keys=[instructor_id], backref="instructor_bookings")
    service = relationship("Service", backref="bookings")
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])

    # Table constraints to ensure data integrity
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
            name="ck_bookings_status",
        ),
        CheckConstraint(
            "location_type IN ('student_home', 'instructor_location', 'neutral')",
            name="ck_bookings_location_type",
        ),
        CheckConstraint("duration_minutes > 0", name="check_duration_positive"),
        CheckConstraint("total_price >= 0", name="check_price_non_negative"),
        CheckConstraint("hourly_rate > 0", name="check_rate_positive"),
        CheckConstraint("start_time < end_time", name="check_time_order"),
    )

    def __init__(self, **kwargs):
        """
        Initialize booking with instant confirmation.

        Sets default status to CONFIRMED if not provided,
        supporting the instant booking workflow.
        """
        super().__init__(**kwargs)
        # Default to CONFIRMED for instant booking
        if not self.status:
            self.status = BookingStatus.CONFIRMED
        logger.info(f"Creating booking for student {self.student_id} with instructor {self.instructor_id}")

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"<Booking {self.id}: student={self.student_id}, "
            f"instructor={self.instructor_id}, date={self.booking_date}, "
            f"time={self.start_time}-{self.end_time}, status={self.status}>"
        )

    def cancel(self, cancelled_by_user_id: int, reason: Optional[str] = None) -> None:
        """
        Cancel this booking.

        Args:
            cancelled_by_user_id: ID of the user cancelling the booking
            reason: Optional cancellation reason

        Side Effects:
            - Updates status to CANCELLED
            - Sets cancelled_at timestamp
            - Records who cancelled and why
        """
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = datetime.utcnow()
        self.cancelled_by_id = cancelled_by_user_id
        self.cancellation_reason = reason
        logger.info(f"Booking {self.id} cancelled by user {cancelled_by_user_id}")

    def complete(self) -> None:
        """
        Mark this booking as completed.

        Should be called after the lesson has been successfully delivered.

        Side Effects:
            - Updates status to COMPLETED
            - Sets completed_at timestamp
        """
        self.status = BookingStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        logger.info(f"Booking {self.id} marked as completed")

    def mark_no_show(self) -> None:
        """
        Mark this booking as a no-show.

        Should be called when the student doesn't attend the scheduled lesson.

        Side Effects:
            - Updates status to NO_SHOW
        """
        self.status = BookingStatus.NO_SHOW
        logger.info(f"Booking {self.id} marked as no-show")

    @property
    def is_cancellable(self) -> bool:
        """
        Check if booking can still be cancelled.

        Returns:
            bool: True if booking is in a cancellable state (CONFIRMED or PENDING)
        """
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]

    @property
    def is_upcoming(self) -> bool:
        """
        Check if booking is in the future.

        Returns:
            bool: True if booking date is in the future and status is CONFIRMED
        """
        from datetime import date

        return self.booking_date > date.today() and self.status == BookingStatus.CONFIRMED

    @property
    def is_past(self) -> bool:
        """
        Check if booking is in the past.

        Returns:
            bool: True if booking date has passed
        """
        from datetime import date

        return self.booking_date < date.today()

    @property
    def location_type_display(self) -> str:
        """
        Get display-friendly location type.

        Returns:
            str: Human-readable location type
        """
        if self.location_type == LocationType.STUDENT_HOME:
            return "Student's Home"
        elif self.location_type == LocationType.INSTRUCTOR_LOCATION:
            return "Instructor's Location"
        else:
            return "Neutral Location"

    @property
    def can_be_modified_by(self, user_id: int) -> bool:
        """
        Check if a user can modify this booking.

        Args:
            user_id: ID of the user attempting modification

        Returns:
            bool: True if user is either the student or instructor
        """
        return user_id in [self.student_id, self.instructor_id]

    def to_dict(self) -> dict:
        """
        Convert booking to dictionary for API responses.

        Returns:
            dict: Booking data suitable for JSON serialization
        """
        return {
            "id": self.id,
            "student_id": self.student_id,
            "instructor_id": self.instructor_id,
            "service_id": self.service_id,
            "booking_date": self.booking_date.isoformat() if self.booking_date else None,
            "start_time": str(self.start_time) if self.start_time else None,
            "end_time": str(self.end_time) if self.end_time else None,
            "service_name": self.service_name,
            "hourly_rate": float(self.hourly_rate),
            "total_price": float(self.total_price),
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "location_type": self.location_type,
            "location_type_display": self.location_type_display,
            "meeting_location": self.meeting_location,
            "service_area": self.service_area,
            "student_note": self.student_note,
            "instructor_note": self.instructor_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "cancelled_by_id": self.cancelled_by_id,
            "cancellation_reason": self.cancellation_reason,
        }
