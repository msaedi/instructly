"""Booking dispute satellite table."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingDispute(Base):
    """Dispute state for a single booking."""

    __tablename__ = "booking_disputes"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    dispute_id = Column(String(100), nullable=True)
    dispute_status = Column(String(30), nullable=True)
    dispute_amount = Column(Integer, nullable=True)
    dispute_created_at = Column(DateTime(timezone=True), nullable=True)
    dispute_resolved_at = Column(DateTime(timezone=True), nullable=True)

    booking = relationship("Booking", back_populates="dispute")

    def __repr__(self) -> str:
        return f"<BookingDispute booking={self.booking_id} status={self.dispute_status}>"
