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

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)

    # Direct time storage - primary booking info
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    # Booking details
    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.PENDING)
    total_price = Column(Float, nullable=False)

    # Cancellation fields
    cancellation_deadline = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships - use back_populates instead of backref
    student = relationship("User", foreign_keys=[student_id], back_populates="bookings_as_student")
    instructor = relationship("User", foreign_keys=[instructor_id], back_populates="bookings_as_instructor")
    service = relationship("Service", back_populates="bookings")