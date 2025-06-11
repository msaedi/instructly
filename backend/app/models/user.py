from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
from .availability import BlackoutDate
import enum

class UserRole(str, enum.Enum):
    INSTRUCTOR = "instructor"
    STUDENT = "student"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="user", uselist=False)
    
    # Availability relationships
    recurring_availability = relationship("RecurringAvailability", back_populates="instructor", cascade="all, delete-orphan")
    specific_date_availability = relationship("SpecificDateAvailability", back_populates="instructor", cascade="all, delete-orphan")
    blackout_dates = relationship("BlackoutDate", back_populates="instructor", cascade="all, delete-orphan")

    # Password reset relationships
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")