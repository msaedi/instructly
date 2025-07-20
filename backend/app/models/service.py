# backend/app/models/service.py
"""
Service model for InstaInstru platform.

This module defines the Service model which represents the various
services/skills that instructors offer to students.

Supports soft delete via is_active flag to preserve booking integrity
while allowing instructors to manage their service offerings.
"""

import logging
from typing import List

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .types import IntegerArrayType

logger = logging.getLogger(__name__)


class Service(Base):
    """
    Model representing a service offered by an instructor.

    Each service has a skill name, hourly rate, and optional description.
    Services can have a custom duration that overrides the default.

    Supports soft delete via is_active flag to preserve booking history
    while allowing instructors to remove services from their active offerings.

    Attributes:
        id: Primary key
        instructor_profile_id: Foreign key to instructor_profiles
        skill: The name of the skill/service (e.g., "Piano", "Yoga")
        hourly_rate: Rate per hour in USD
        description: Optional description of the service
        duration_options: List of available duration options in minutes (default: [60])
        is_active: Whether the service is currently offered (soft delete)

    Relationships:
        instructor_profile: The instructor offering this service
    """

    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    instructor_profile_id = Column(Integer, ForeignKey("instructor_profiles.id", ondelete="CASCADE"))
    skill = Column(String, nullable=False)
    hourly_rate = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    duration_options: Mapped[List[int]] = mapped_column(IntegerArrayType, nullable=False, default=[60])
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="services")

    def __init__(self, **kwargs):
        """Initialize service with logging."""
        super().__init__(**kwargs)
        logger.debug(
            f"Creating service '{kwargs.get('skill')}' for instructor profile {kwargs.get('instructor_profile_id')}"
        )

    def __repr__(self):
        """String representation of the Service."""
        status = " (inactive)" if not self.is_active else ""
        return f"<Service {self.skill} ${self.hourly_rate}/hr{status}>"

    def session_price(self, duration_minutes: int) -> float:
        """
        Calculate the price for a session of given duration.

        Args:
            duration_minutes: Duration of the session in minutes

        Returns:
            float: Price for the session
        """
        return (self.hourly_rate * duration_minutes) / 60.0

    def deactivate(self) -> None:
        """
        Soft delete this service by marking it as inactive.

        Preserves the record for historical bookings while removing
        it from active service listings.
        """
        self.is_active = False
        logger.info(f"Deactivated service {self.id}: {self.skill}")

    def activate(self) -> None:
        """
        Reactivate a previously deactivated service.

        Makes the service available for booking again.
        """
        self.is_active = True
        logger.info(f"Activated service {self.id}: {self.skill}")
