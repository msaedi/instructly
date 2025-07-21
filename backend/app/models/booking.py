# backend/app/models/booking.py
"""
Booking model for InstaInstru platform.

Represents instant bookings between students and instructors.
Bookings are self-contained records with all necessary information,
achieving complete independence from availability slots.

Architecture: Bookings store instructor, date, and time data directly.
This allows bookings to persist as commitments regardless of
availability changes ("Rug and Person" principle).
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
    """Booking lifecycle statuses."""

    PENDING = "PENDING"  # Reserved for future use
    CONFIRMED = "CONFIRMED"  # Default - instant booking
    COMPLETED = "COMPLETED"  # Lesson completed
    CANCELLED = "CANCELLED"  # Booking cancelled
    NO_SHOW = "NO_SHOW"  # Student didn't attend


class LocationType(str, Enum):
    """Where the lesson will take place."""

    STUDENT_HOME = "student_home"
    INSTRUCTOR_LOCATION = "instructor_location"
    NEUTRAL = "neutral"


class Booking(Base):
    """
    Self-contained booking record between student and instructor.

    Design: Bookings are instant (confirmed immediately) and store all
    necessary data directly, with no dependency on availability slots.
    Service details are snapshotted at booking time for historical accuracy.
    """

    __tablename__ = "bookings"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Core relationships
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_service_id = Column(Integer, ForeignKey("instructor_services.id"), nullable=False)

    # Self-contained booking data
    booking_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Service snapshot (preserved for history)
    service_name = Column(String, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    # Booking details
    status = Column(String(20), nullable=False, default=BookingStatus.CONFIRMED, index=True)
    service_area = Column(String, nullable=True)
    location_type = Column(String(50), nullable=True, default=LocationType.NEUTRAL)
    meeting_location = Column(Text, nullable=True)
    student_note = Column(Text, nullable=True)
    instructor_note = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Cancellation tracking
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Relationships
    student = relationship("User", foreign_keys=[student_id], backref="student_bookings")
    instructor = relationship("User", foreign_keys=[instructor_id], backref="instructor_bookings")
    instructor_service = relationship("InstructorService", backref="bookings")
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])

    # Data integrity constraints
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
        """Initialize with instant confirmation by default."""
        super().__init__(**kwargs)
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
        """Cancel this booking."""
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = datetime.utcnow()
        self.cancelled_by_id = cancelled_by_user_id
        self.cancellation_reason = reason
        logger.info(f"Booking {self.id} cancelled by user {cancelled_by_user_id}")

    def complete(self) -> None:
        """Mark booking as completed."""
        self.status = BookingStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        logger.info(f"Booking {self.id} marked as completed")

    def mark_no_show(self) -> None:
        """Mark booking as no-show."""
        self.status = BookingStatus.NO_SHOW
        logger.info(f"Booking {self.id} marked as no-show")

    @property
    def is_cancellable(self) -> bool:
        """Check if booking can be cancelled."""
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]

    @property
    def is_upcoming(self) -> bool:
        """Check if booking is in the future."""
        from datetime import date

        return self.booking_date > date.today() and self.status == BookingStatus.CONFIRMED

    @property
    def is_past(self) -> bool:
        """Check if booking date has passed."""
        from datetime import date

        return self.booking_date < date.today()

    @property
    def location_type_display(self) -> str:
        """Get human-readable location type."""
        return {
            LocationType.STUDENT_HOME: "Student's Home",
            LocationType.INSTRUCTOR_LOCATION: "Instructor's Location",
            LocationType.NEUTRAL: "Neutral Location",
        }.get(self.location_type, "Neutral Location")

    @property
    def can_be_modified_by(self, user_id: int) -> bool:
        """Check if user can modify this booking."""
        return user_id in [self.student_id, self.instructor_id]

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "student_id": self.student_id,
            "instructor_id": self.instructor_id,
            "instructor_service_id": self.instructor_service_id,
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
