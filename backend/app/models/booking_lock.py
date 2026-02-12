"""Booking lock satellite table."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingLock(Base):
    """Lock lifecycle state for a single booking."""

    __tablename__ = "booking_locks"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_amount_cents = Column(Integer, nullable=True)
    lock_resolved_at = Column(DateTime(timezone=True), nullable=True)
    lock_resolution = Column(String(50), nullable=True)

    booking = relationship("Booking", back_populates="lock_detail")

    def __repr__(self) -> str:
        return f"<BookingLock booking={self.booking_id} resolution={self.lock_resolution}>"
