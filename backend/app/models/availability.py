# backend/app/models/availability.py
"""
Availability models for InstaInstru platform.

This module defines the database models for managing instructor availability,
including date-specific availability entries, time slots, and blackout dates.

The availability system uses a single-table design where AvailabilitySlot
contains both date and time information for instructor availability.

Classes:
    AvailabilitySlot: Defines time slots within a date
    BlackoutDate: Tracks instructor vacation/unavailable days
"""

import logging

import ulid
from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, Time, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base

logger = logging.getLogger(__name__)


class AvailabilitySlot(Base):
    """
    Time slots when an instructor is available.

    Single-table design: Each slot contains both date and time information,
    eliminating the need for a separate instructor_availability table.

    Attributes:
        id: Primary key
        instructor_id: Foreign key to users table
        date: The date of this availability slot
        start_time: Start time of this availability slot
        end_time: End time of this availability slot
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated

    Relationships:
        instructor: The User who owns this availability slot

    Note: The relationship to bookings is one-way: Booking → AvailabilitySlot
    """

    __tablename__ = "availability_slots"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    specific_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    instructor = relationship("User", back_populates="availability_slots")

    # Indexes for performance
    __table_args__ = (
        Index("idx_availability_instructor_date", "instructor_id", "specific_date"),
        Index("idx_availability_date", "specific_date"),
        Index("idx_availability_instructor_id", "instructor_id"),
        Index(
            "unique_instructor_date_time_slot", "instructor_id", "specific_date", "start_time", "end_time", unique=True
        ),
    )

    def __repr__(self):
        return f"<AvailabilitySlot {self.specific_date} {self.start_time}-{self.end_time}>"


class BlackoutDate(Base):
    """Instructor blackout/vacation dates"""

    __tablename__ = "blackout_dates"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    instructor = relationship("User", back_populates="blackout_dates")

    # Constraints
    __table_args__ = (
        UniqueConstraint("instructor_id", "date", name="unique_instructor_blackout_date"),
        Index("idx_blackout_dates_instructor_date", "instructor_id", "date"),
    )

    def __repr__(self):
        return f"<BlackoutDate {self.date} - {self.reason or 'No reason'}>"
