"""User favorites model for InstaInstru platform."""

from datetime import datetime
from typing import TYPE_CHECKING

import ulid
from sqlalchemy import TIMESTAMP, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .user import User


class UserFavorite(Base):
    """Junction table for students favoriting instructors."""

    __tablename__ = "user_favorites"

    # Primary key with ULID
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Foreign keys with indexes for performance
    student_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Index for faster lookups by student
    )

    instructor_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Index for faster lookups by instructor
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id], back_populates="student_favorites")

    instructor: Mapped["User"] = relationship(
        "User", foreign_keys=[instructor_id], back_populates="instructor_favorites"
    )

    __table_args__ = (UniqueConstraint("student_id", "instructor_id", name="unique_student_instructor_favorite"),)

    def __repr__(self) -> str:
        return f"<UserFavorite(student={self.student_id}, instructor={self.instructor_id})>"
