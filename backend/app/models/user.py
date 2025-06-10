from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
from .availability import AvailabilityWindow, BlackoutDate
import enum

class UserRole(str, enum.Enum):
    INSTRUCTOR = "instructor"
    STUDENT = "student"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship to InstructorProfile
    instructor_profile = relationship("InstructorProfile", back_populates="user", uselist=False)
    bookings_as_student = relationship("Booking", foreign_keys="Booking.student_id", back_populates="student")
    bookings_as_instructor = relationship("Booking", foreign_keys="Booking.instructor_id", back_populates="instructor")
    availability_windows = relationship("AvailabilityWindow", back_populates="instructor", cascade="all, delete-orphan")
    blackout_dates = relationship("BlackoutDate", back_populates="instructor", cascade="all, delete-orphan")