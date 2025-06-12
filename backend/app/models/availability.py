# backend/app/models/availability.py
"""
Availability models for InstaInstru platform.

This module defines the database models for managing instructor availability,
including date-specific availability entries, time slots, and blackout dates.

The availability system uses a two-table hierarchy:
- InstructorAvailability: One entry per instructor per date
- AvailabilitySlot: Multiple time ranges per date

Classes:
    InstructorAvailability: Manages availability for specific dates
    AvailabilitySlot: Defines time slots within a date
    BlackoutDate: Tracks instructor vacation/unavailable days
"""

import logging
from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

logger = logging.getLogger(__name__)

# RecurringAvailability class has been REMOVED - we now use date-specific availability only

class InstructorAvailability(Base):
    """
    Instructor availability for specific dates.
    
    This model represents availability entries for specific dates. Each entry
    can either contain time slots (when is_cleared=False) or mark the entire
    day as unavailable (when is_cleared=True).
    
    Attributes:
        id: Primary key
        instructor_id: Foreign key to users table
        date: The specific date this availability applies to
        is_cleared: If True, the instructor is unavailable this entire day
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated
        
    Relationships:
        instructor: The User who owns this availability
        time_slots: List of AvailabilitySlot objects for this date
    """
    __tablename__ = "instructor_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    is_cleared = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instructor = relationship("User", back_populates="availability")
    time_slots = relationship("AvailabilitySlot", back_populates="availability", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('instructor_id', 'date', name='unique_instructor_date'),
        Index('idx_instructor_availability_instructor_date', 'instructor_id', 'date'),
    )
    
    def __repr__(self):
        return f"<InstructorAvailability {self.date} {'(cleared)' if self.is_cleared else ''}>"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.debug(f"Creating InstructorAvailability for instructor {kwargs.get('instructor_id')} on {kwargs.get('date')}")


class AvailabilitySlot(Base):
    """
    Time slots for a specific date's availability.
    
    Each slot represents a continuous time range when the instructor is available
    on a specific date. Multiple slots can exist for a single date to handle
    split schedules (e.g., 9-12 and 2-5).
    
    Attributes:
        id: Primary key
        availability_id: Foreign key to instructor_availability table
        start_time: Start time of this availability slot
        end_time: End time of this availability slot
        
    Relationships:
        availability: The InstructorAvailability entry this slot belongs to
        
    Example:
        Morning slot: 09:00:00 - 12:00:00
        Afternoon slot: 14:00:00 - 17:00:00
    """
    __tablename__ = "availability_slots"
    
    id = Column(Integer, primary_key=True, index=True)
    availability_id = Column(Integer, ForeignKey("instructor_availability.id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    # Relationships
    availability = relationship("InstructorAvailability", back_populates="time_slots")
    
    # Index for performance
    __table_args__ = (
        Index('idx_availability_slots_availability_id', 'availability_id'),
    )
    
    def __repr__(self):
        return f"<AvailabilitySlot {self.start_time}-{self.end_time}>"

class BlackoutDate(Base):
    """Instructor blackout/vacation dates"""
    __tablename__ = "blackout_dates"
    
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    instructor = relationship("User", back_populates="blackout_dates")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('instructor_id', 'date', name='unique_instructor_blackout_date'),
        Index('idx_blackout_dates_instructor_date', 'instructor_id', 'date'),
    )
    
    def __repr__(self):
        return f"<BlackoutDate {self.date} - {self.reason or 'No reason'}>"