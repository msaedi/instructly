"""
Instructor profile model for InstaInstru platform.

This module defines the InstructorProfile model which extends the base User
model with instructor-specific information such as bio, experience, and
areas of service.

Classes:
    InstructorProfile: Extended profile information for instructor users
"""

import logging

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base

logger = logging.getLogger(__name__)


class InstructorProfile(Base):
    """
    Extended profile information for instructors.

    This model stores additional information specific to instructors that isn't
    needed for regular users. It has a one-to-one relationship with the User model.

    Attributes:
        id: Primary key
        user_id: Foreign key to users table (one-to-one)
        bio: Instructor's biography/description
        areas_of_service: Comma-separated list of NYC areas served
        years_experience: Years of teaching experience
        created_at: Profile creation timestamp
        updated_at: Last update timestamp

    Removed Attributes (from old booking system):
        - default_session_duration: Now handled per service
        - buffer_time: No longer needed without time slot booking
        - minimum_advance_hours: Will be reimplemented in booking v2

    Relationships:
        user: One-to-one with User model
        services: One-to-many with Service model

    Note:
        The old booking-related columns have been removed as part of the
        system refactoring. These will be reimplemented differently in
        the new booking system.
    """

    __tablename__ = "instructor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    bio = Column(String, nullable=True)
    areas_of_service = Column(String, nullable=True)  # Comma-separated list of NYC areas
    years_experience = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    min_advance_booking_hours = Column(Integer, nullable=False, default=2)
    buffer_time_minutes = Column(Integer, nullable=False, default=0)

    # REMOVED: Old booking system columns
    # default_session_duration = Column(Integer, nullable=False, default=60)
    # buffer_time = Column(Integer, nullable=False, default=0)
    # minimum_advance_hours = Column(Integer, nullable=False, default=2)

    # Relationships
    user = relationship("User", back_populates="instructor_profile")
    services = relationship("Service", back_populates="instructor_profile", cascade="all, delete-orphan")

    # Table-level constraints
    __table_args__ = (CheckConstraint("years_experience >= 0", name="check_years_experience_non_negative"),)

    def __init__(self, **kwargs):
        """Initialize instructor profile with logging."""
        super().__init__(**kwargs)
        logger.info(f"Creating instructor profile for user_id: {kwargs.get('user_id')}")

    def __repr__(self):
        """String representation of the InstructorProfile."""
        return f"<InstructorProfile user_id={self.user_id} experience={self.years_experience}yrs>"

    @property
    def areas_list(self):
        """Convert comma-separated areas string to list."""
        if self.areas_of_service:
            return [area.strip() for area in self.areas_of_service.split(",")]
        return []

    def set_areas(self, areas_list):
        """Set areas of service from a list."""
        if areas_list:
            self.areas_of_service = ", ".join(areas_list)
            logger.debug(f"Updated areas of service for instructor {self.user_id}: {self.areas_of_service}")
        else:
            self.areas_of_service = None

    # Property for active services only
    @property
    def active_services(self):
        """Return only active services."""
        return [service for service in self.services if service.is_active]
