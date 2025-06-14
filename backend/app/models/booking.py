"""
Booking model for InstaInstru platform.

This module defines the Booking model which represents a confirmed lesson
booking between a student and an instructor. The platform uses instant
booking, so bookings are immediately confirmed upon creation.
"""

import logging
from typing import Literal
from datetime import datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Numeric, Date, Time, Text, Boolean, CheckConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, backref
from ..database import Base

logger = logging.getLogger(__name__)


class BookingStatus(str, Enum):
    """
    Enum for booking statuses.
    
    Note: Since we use instant booking, PENDING should rarely be used.
    All bookings start as CONFIRMED.
    """
    PENDING = "PENDING"        # Reserved for future use
    CONFIRMED = "CONFIRMED"    # Default - booking is confirmed
    COMPLETED = "COMPLETED"    # Lesson has been completed
    CANCELLED = "CANCELLED"    # Booking was cancelled
    NO_SHOW = "NO_SHOW"       # Student didn't show up


class LocationType(str, Enum):
    """
    Enum for booking location types.
    
    Helps instructors quickly understand where they need to go.
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
    
    Attributes:
        id: Primary key
        student_id: The student who made the booking
        instructor_id: The instructor providing the service
        service_id: The service being booked
        availability_slot_id: The specific time slot being booked
        
        # Snapshot data (preserved for history)
        booking_date: Date of the lesson
        start_time: Start time of the lesson
        end_time: End time of the lesson
        service_name: Name of service at booking time
        hourly_rate: Rate at booking time
        total_price: Total price calculated
        duration_minutes: Duration in minutes
        
        # Booking details
        status: Current booking status
        service_area: NYC area where service is provided
        meeting_location: Specific location/address
        student_note: Note from student at booking
        instructor_note: Note from instructor
        
        # Timestamps
        created_at: When booking was made
        confirmed_at: When booking was confirmed (same as created for instant)
        completed_at: When lesson was completed
        cancelled_at: When booking was cancelled (if applicable)
        
        # Cancellation info
        cancelled_by_id: Who cancelled the booking
        cancellation_reason: Reason for cancellation
    """
    __tablename__ = "bookings"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    availability_slot_id = Column(Integer, ForeignKey("availability_slots.id"), nullable=True)
    
    # Booking snapshot data
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    service_name = Column(String, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    
    # Status with check constraint
    status = Column(String(20), nullable=False, default=BookingStatus.CONFIRMED)
    
    # Location details
    service_area = Column(String, nullable=True)
    location_type = Column(String(50), nullable=True, default=LocationType.NEUTRAL)
    meeting_location = Column(Text, nullable=True)
    
    # Communication
    student_note = Column(Text, nullable=True)
    instructor_note = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Cancellation details
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Relationships
    student = relationship("User", foreign_keys=[student_id], backref="student_bookings")
    instructor = relationship("User", foreign_keys=[instructor_id], backref="instructor_bookings")
    service = relationship("Service", backref="bookings")
    availability_slot = relationship(
        "AvailabilitySlot", 
        foreign_keys=[availability_slot_id],
        backref=backref("booking", uselist=False),
        post_update=True
    )
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    
    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
            name='ck_bookings_status'
        ),
        CheckConstraint(
            "location_type IN ('student_home', 'instructor_location', 'neutral')",
            name='ck_bookings_location_type'
        ),
        CheckConstraint('duration_minutes > 0', name='check_duration_positive'),
        CheckConstraint('total_price >= 0', name='check_price_non_negative'),
        CheckConstraint('hourly_rate > 0', name='check_rate_positive'),
    )
    
    def __init__(self, **kwargs):
        """Initialize booking with instant confirmation."""
        super().__init__(**kwargs)
        # Default to CONFIRMED for instant booking
        if not self.status:
            self.status = BookingStatus.CONFIRMED
        logger.info(f"Creating booking for student {self.student_id} with instructor {self.instructor_id}")
    
    def __repr__(self):
        return f"<Booking {self.id}: {self.student_id}->{self.instructor_id} on {self.booking_date} status={self.status}>"
    
    def cancel(self, cancelled_by_user_id: int, reason: str = None):
        """Cancel this booking."""
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = datetime.utcnow()
        self.cancelled_by_id = cancelled_by_user_id
        self.cancellation_reason = reason
        logger.info(f"Booking {self.id} cancelled by user {cancelled_by_user_id}")
    
    def complete(self):
        """Mark this booking as completed."""
        self.status = BookingStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        logger.info(f"Booking {self.id} marked as completed")
    
    def mark_no_show(self):
        """Mark this booking as a no-show."""
        self.status = BookingStatus.NO_SHOW
        logger.info(f"Booking {self.id} marked as no-show")
    
    @property
    def is_cancellable(self) -> bool:
        """Check if booking can still be cancelled."""
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]
    
    @property
    def is_upcoming(self) -> bool:
        """Check if booking is in the future."""
        from datetime import date
        return self.booking_date > date.today() and self.status == BookingStatus.CONFIRMED
    
    @property
    def location_type_display(self) -> str:
        """Get display-friendly location type."""
        if self.location_type == LocationType.STUDENT_HOME:
            return "Student's Home"
        elif self.location_type == LocationType.INSTRUCTOR_LOCATION:
            return "Instructor's Location"
        else:
            return "Neutral Location"
            
    