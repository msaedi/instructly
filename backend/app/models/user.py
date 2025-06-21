# backend/app/models/user.py
"""
User model for InstaInstru platform.

This module defines the User model which serves as the base for both
instructors and students in the system. It includes authentication fields,
role management, and relationships to various user-specific data.

Classes:
    UserRole: Enum defining the possible user roles
    User: Main user model for authentication and role management
"""

import enum
import logging

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base

logger = logging.getLogger(__name__)


class UserRole(str, enum.Enum):
    """
    Enumeration of possible user roles in the system.

    Values:
        INSTRUCTOR: Users who provide instruction services
        STUDENT: Users who book instruction services
    """

    INSTRUCTOR = "instructor"
    STUDENT = "student"


class User(Base):
    """
    Main user model for authentication and profile management.

    This model handles user authentication, role assignment, and serves as
    the central point for user-related relationships. Both instructors and
    students are represented by this model, differentiated by the role field.

    Attributes:
        id: Primary key
        email: Unique email address used for login
        hashed_password: Bcrypt hashed password
        full_name: User's display name
        is_active: Whether the user account is active
        role: User's role (instructor or student)
        created_at: Account creation timestamp
        updated_at: Last update timestamp

    Relationships:
        instructor_profile: One-to-one with InstructorProfile (instructors only)
        availability: One-to-many with InstructorAvailability (instructors only)
        blackout_dates: One-to-many with BlackoutDate (instructors only)
        password_reset_tokens: One-to-many with PasswordResetToken

    Note:
        The old recurring_availability relationship has been removed as part
        of the system refactoring to use only date-specific availability.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    # Using String instead of Enum to avoid SQLAlchemy enum issues
    # The database has a check constraint to ensure valid values
    role = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="user", uselist=False)

    # Availability relationships - UPDATED
    availability = relationship(
        "InstructorAvailability",
        back_populates="instructor",
        cascade="all, delete-orphan",
    )
    blackout_dates = relationship("BlackoutDate", back_populates="instructor", cascade="all, delete-orphan")

    # Password reset relationships
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        """Initialize a new user and log the creation."""
        super().__init__(**kwargs)
        logger.info(f"Creating new {kwargs.get('role', 'unknown')} user with email: {kwargs.get('email', 'unknown')}")

    def __repr__(self):
        """String representation of the User object."""
        return f"<User {self.email} ({self.role.value if self.role else 'no role'})>"

    @property
    def is_instructor(self):
        """Check if the user is an instructor."""
        return self.role == UserRole.INSTRUCTOR

    @property
    def is_student(self):
        """Check if the user is a student."""
        return self.role == UserRole.STUDENT
