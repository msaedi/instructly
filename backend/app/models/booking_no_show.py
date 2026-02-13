"""Booking no-show satellite table."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingNoShow(Base):
    """No-show report state for a single booking."""

    __tablename__ = "booking_no_shows"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    no_show_reported_by = Column(String(26), ForeignKey("users.id"), nullable=True)
    no_show_reported_at = Column(DateTime(timezone=True), nullable=True)
    no_show_type = Column(String(20), nullable=True)
    no_show_disputed = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    no_show_disputed_at = Column(DateTime(timezone=True), nullable=True)
    no_show_dispute_reason = Column(String(500), nullable=True)
    no_show_resolved_at = Column(DateTime(timezone=True), nullable=True)
    no_show_resolution = Column(String(30), nullable=True)

    booking = relationship("Booking", back_populates="no_show_detail")
    no_show_reporter = relationship("User", foreign_keys=[no_show_reported_by])

    def __repr__(self) -> str:
        return f"<BookingNoShow booking={self.booking_id} type={self.no_show_type}>"
