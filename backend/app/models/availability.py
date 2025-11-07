# backend/app/models/availability.py
"""
Availability models for InstaInstru platform.

This module defines the database models for managing instructor availability,
including blackout dates.

Note: Availability data is stored in availability_days table (bitmap format).
See app.models.availability_day for the AvailabilityDay model.

Classes:
    BlackoutDate: Tracks instructor vacation/unavailable days
"""

import logging

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base

logger = logging.getLogger(__name__)


class BlackoutDate(Base):
    """Instructor blackout/vacation dates"""

    __tablename__ = "blackout_dates"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    instructor = relationship("User", back_populates="blackout_dates")

    # Constraints
    __table_args__ = (
        UniqueConstraint("instructor_id", "date", name="unique_instructor_blackout_date"),
        Index("idx_blackout_dates_instructor_date", "instructor_id", "date"),
    )

    def __repr__(self) -> str:
        return f"<BlackoutDate {self.date} - {self.reason or 'No reason'}>"
