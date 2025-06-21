# backend/app/models/instructor.py
"""
Instructor Profile model for the InstaInstru platform.

This module defines the InstructorProfile model which extends a User
to have instructor-specific attributes and capabilities. Each instructor
has a profile that contains their bio, experience, service areas, and
booking preferences.
"""

import logging
from typing import TYPE_CHECKING, List

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base

if TYPE_CHECKING:
    from .service import Service

logger = logging.getLogger(__name__)


class InstructorProfile(Base):
    """
    Model representing an instructor's profile.

    An instructor profile contains all the instructor-specific information
    beyond the basic user data. This includes their professional details,
    service offerings, and booking preferences.

    Attributes:
        id: Primary key
        user_id: Foreign key to users table (one-to-one relationship)
        bio: Professional biography/description
        years_experience: Years of teaching experience
        areas_of_service: Comma-separated list of NYC areas served
        min_advance_booking_hours: Minimum hours advance notice for bookings
        buffer_time_minutes: Buffer time between bookings
        created_at: Timestamp when profile was created
        updated_at: Timestamp when profile was last updated

    Relationships:
        user: The User this profile belongs to
        services: List of services offered by this instructor

    Business Rules:
        - Each user can have at most one instructor profile
        - Deleting a profile soft deletes all services (preserves bookings)
        - Profile deletion reverts user role to STUDENT
    """

    __tablename__ = "instructor_profiles"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key to user (one-to-one relationship)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Profile information
    bio = Column(Text, nullable=True)
    years_experience = Column(Integer, nullable=True)

    # Service areas (comma-separated NYC areas)
    areas_of_service = Column(String, nullable=True)

    # Booking preferences
    min_advance_booking_hours = Column(Integer, nullable=False, default=24)
    buffer_time_minutes = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship(
        "User",
        back_populates="instructor_profile",
        uselist=False,
    )

    # IMPORTANT: Do NOT cascade delete services automatically
    # The service layer handles soft/hard delete logic
    services = relationship(
        "Service",
        back_populates="instructor_profile",
        cascade="save-update, merge",  # Only cascade saves and merges, NOT deletes
        passive_deletes=True,  # Don't load services just to delete them
    )

    def __init__(self, **kwargs):
        """Initialize instructor profile."""
        super().__init__(**kwargs)
        logger.info(f"Creating instructor profile for user {kwargs.get('user_id')}")

    def __repr__(self):
        """String representation for debugging."""
        return f"<InstructorProfile {self.user_id} - {self.years_experience} years>"

    @property
    def active_services(self) -> List["Service"]:
        """
        Get only active services for this instructor.

        Returns:
            List of active Service objects
        """
        return [s for s in self.services if s.is_active]

    @property
    def has_active_services(self) -> bool:
        """
        Check if instructor has any active services.

        Returns:
            bool: True if at least one service is active
        """
        return any(s.is_active for s in self.services)

    @property
    def total_services(self) -> int:
        """
        Get total number of services (active and inactive).

        Returns:
            int: Total service count
        """
        return len(self.services)

    @property
    def service_areas_list(self) -> List[str]:
        """
        Get service areas as a list.

        Returns:
            List of area strings
        """
        if not self.areas_of_service:
            return []
        return [area.strip() for area in self.areas_of_service.split(",")]

    def can_accept_booking_at(self, hours_until_booking: int) -> bool:
        """
        Check if instructor accepts bookings with given advance notice.

        Args:
            hours_until_booking: Hours between now and booking time

        Returns:
            bool: True if booking meets advance notice requirement
        """
        return hours_until_booking >= self.min_advance_booking_hours

    def to_dict(self, include_services: bool = True) -> dict:
        """
        Convert profile to dictionary for API responses.

        Args:
            include_services: Whether to include services list

        Returns:
            dict: Profile data suitable for JSON serialization
        """
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "bio": self.bio,
            "years_experience": self.years_experience,
            "areas_of_service": self.areas_of_service,
            "service_areas_list": self.service_areas_list,
            "min_advance_booking_hours": self.min_advance_booking_hours,
            "buffer_time_minutes": self.buffer_time_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_services:
            data["services"] = [s.to_dict() for s in self.active_services]
            data["total_services"] = self.total_services
            data["active_services_count"] = len(self.active_services)

        return data
