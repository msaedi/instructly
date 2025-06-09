from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Enum, Boolean, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
import enum

class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    instructor = relationship("User", foreign_keys=[instructor_id])
    booking = relationship("Booking", back_populates="time_slot", uselist=False)

    @property
    def is_booked(self):
        return getattr(self, '_is_booked', False)
    
    @is_booked.setter
    def is_booked(self, value):
        self._is_booked = value

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timeslot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.PENDING)
    total_price = Column(Float, nullable=False)
    cancellation_deadline = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    original_duration = Column(Integer, nullable=True)  # in minutes
    adjusted_duration = Column(Integer, nullable=True)  # if modified after booking
    adjustment_reason = Column(String, nullable=True)

    # Relationships
    student = relationship("User", foreign_keys=[student_id])
    instructor = relationship("User", foreign_keys=[instructor_id])
    time_slot = relationship("TimeSlot", back_populates="booking")
    service = relationship("Service", back_populates="bookings")

    @property
    def actual_duration(self):
        """Get the actual duration (adjusted if modified, original otherwise)"""
        return self.adjusted_duration or self.original_duration