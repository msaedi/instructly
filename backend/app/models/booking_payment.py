"""Booking payment satellite table."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingPayment(Base):
    """Payment and capture state for a single booking."""

    __tablename__ = "booking_payments"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    payment_method_id = Column(String(255), nullable=True)
    payment_intent_id = Column(String(255), nullable=True)
    payment_status = Column(String(50), nullable=True)

    auth_scheduled_for = Column(DateTime(timezone=True), nullable=True)
    auth_attempted_at = Column(DateTime(timezone=True), nullable=True)
    auth_failure_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    auth_last_error = Column(String(500), nullable=True)
    auth_failure_first_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    auth_failure_t13_warning_sent_at = Column(DateTime(timezone=True), nullable=True)

    credits_reserved_cents = Column(Integer, nullable=False, default=0, server_default=text("0"))
    settlement_outcome = Column(String(50), nullable=True)
    instructor_payout_amount = Column(Integer, nullable=True)

    capture_failed_at = Column(DateTime(timezone=True), nullable=True)
    capture_escalated_at = Column(DateTime(timezone=True), nullable=True)
    capture_retry_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    capture_error = Column(String(500), nullable=True)

    booking = relationship("Booking", back_populates="payment_detail")

    def __repr__(self) -> str:
        return f"<BookingPayment booking={self.booking_id} status={self.payment_status}>"
