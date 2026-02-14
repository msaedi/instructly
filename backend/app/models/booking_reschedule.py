"""Booking reschedule satellite table."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingReschedule(Base):
    """Reschedule state for a single booking."""

    __tablename__ = "booking_reschedules"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    late_reschedule_used = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reschedule_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    rescheduled_to_booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_lesson_datetime = Column(DateTime(timezone=True), nullable=True)

    booking = relationship(
        "Booking",
        back_populates="reschedule_detail",
        foreign_keys=[booking_id],
    )
    rescheduled_to = relationship("Booking", foreign_keys=[rescheduled_to_booking_id])

    def __repr__(self) -> str:
        return f"<BookingReschedule booking={self.booking_id} count={self.reschedule_count}>"
