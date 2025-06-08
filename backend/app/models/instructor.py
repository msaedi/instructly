from sqlalchemy import Column, Integer, String, Float, ARRAY, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base

class InstructorProfile(Base):
    __tablename__ = "instructor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    bio = Column(String, nullable=True)
    areas_of_service = Column(String, nullable=True)
    years_experience = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to User
    user = relationship("User", back_populates="instructor_profile")
    services = relationship("Service", back_populates="instructor_profile", cascade="all, delete-orphan")

    # Table-level constraints
    __table_args__ = (
        CheckConstraint('hourly_rate > 0', name='check_hourly_rate_positive'),
        CheckConstraint('years_experience >= 0', name='check_years_experience_non_negative'),
    )