"""Booking lock satellite table."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingLock(Base):
    """Lock lifecycle state for a single booking."""

    __tablename__ = "booking_locks"
    __table_args__ = (
        CheckConstraint(
            "lock_resolution IS NULL OR lock_resolution IN ("
            "'new_lesson_completed',"
            "'new_lesson_cancelled_ge12',"
            "'new_lesson_cancelled_lt12',"
            "'instructor_cancelled',"
            "'completed',"
            "'cancelled_by_student',"
            "'cancelled_by_instructor',"
            "'expired'"
            ")",
            name="ck_booking_locks_lock_resolution",
        ),
    )

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_amount_cents = Column(Integer, nullable=True)
    lock_resolved_at = Column(DateTime(timezone=True), nullable=True)
    lock_resolution = Column(String(50), nullable=True)

    booking = relationship("Booking", back_populates="lock_detail")

    def __repr__(self) -> str:
        return f"<BookingLock booking={self.booking_id} resolution={self.lock_resolution}>"
