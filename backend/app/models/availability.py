# backend/app/models/availability.py
from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, Enum, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from ..database import Base

class DayOfWeek(str, enum.Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

class RecurringAvailability(Base):
    """Weekly recurring schedule patterns"""
    __tablename__ = "recurring_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(String(10), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instructor = relationship("User", back_populates="recurring_availability")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('instructor_id', 'day_of_week', 'start_time', name='unique_recurring_slot'),
        Index('idx_recurring_instructor_day', 'instructor_id', 'day_of_week'),
    )
    
    def __repr__(self):
        return f"<RecurringAvailability {self.day_of_week.value} {self.start_time}-{self.end_time}>"

class SpecificDateAvailability(Base):
    """Specific date overrides (including cleared days)"""
    __tablename__ = "specific_date_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    is_cleared = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instructor = relationship("User", back_populates="specific_date_availability")
    time_slots = relationship("DateTimeSlot", back_populates="date_override", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('instructor_id', 'date', name='unique_instructor_date'),
        Index('idx_specific_date', 'instructor_id', 'date'),
    )
    
    def __repr__(self):
        return f"<SpecificDateAvailability {self.date} {'(cleared)' if self.is_cleared else ''}>"

class DateTimeSlot(Base):
    """Time slots for specific date overrides"""
    __tablename__ = "date_time_slots"
    
    id = Column(Integer, primary_key=True, index=True)
    date_override_id = Column(Integer, ForeignKey("specific_date_availability.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    # Relationships
    date_override = relationship("SpecificDateAvailability", back_populates="time_slots")
    
    def __repr__(self):
        return f"<DateTimeSlot {self.start_time}-{self.end_time}>"

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
    )
    
    def __repr__(self):
        return f"<BlackoutDate {self.date} - {self.reason or 'No reason'}>"
    