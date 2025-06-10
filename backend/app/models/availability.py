# app/models/availability.py

from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, Enum, DateTime, CheckConstraint, UniqueConstraint
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

class AvailabilityWindow(Base):
    __tablename__ = "availability_windows"
    
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Either recurring (day_of_week) OR one-time (specific_date)
    day_of_week = Column(String(10), nullable=True, index=True)
    specific_date = Column(Date, nullable=True, index=True)
    
    # Time range
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    # Flags
    is_recurring = Column(Boolean, default=True, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    is_cleared = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instructor = relationship("User", back_populates="availability_windows")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            '(day_of_week IS NOT NULL AND specific_date IS NULL) OR (day_of_week IS NULL AND specific_date IS NOT NULL)',
            name='check_day_or_date'
        ),
        CheckConstraint('end_time > start_time', name='check_time_order'),
    )
    
    def __repr__(self):
        if self.day_of_week:
            return f"<AvailabilityWindow {self.day_of_week.value} {self.start_time}-{self.end_time}>"
        return f"<AvailabilityWindow {self.specific_date} {self.start_time}-{self.end_time}>"

class BlackoutDate(Base):
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