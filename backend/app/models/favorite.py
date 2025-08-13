"""User favorites model for InstaInstru platform."""

from datetime import datetime

import ulid
from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class UserFavorite(Base):
    """Junction table for students favoriting instructors."""

    __tablename__ = "user_favorites"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    student_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    student = relationship("User", foreign_keys=[student_id])
    instructor = relationship("User", foreign_keys=[instructor_id])

    __table_args__ = (UniqueConstraint("student_id", "instructor_id", name="unique_student_instructor_favorite"),)
