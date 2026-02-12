"""Booking transfer/refund/reversal satellite table."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingTransfer(Base):
    """Transfer and refund state for a single booking."""

    __tablename__ = "booking_transfers"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    stripe_transfer_id = Column(String(100), nullable=True)
    transfer_failed_at = Column(DateTime(timezone=True), nullable=True)
    transfer_error = Column(String(500), nullable=True)
    transfer_retry_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    transfer_reversed = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    transfer_reversal_id = Column(String(100), nullable=True)
    transfer_reversal_failed = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    transfer_reversal_error = Column(String(500), nullable=True)
    transfer_reversal_failed_at = Column(DateTime(timezone=True), nullable=True)
    transfer_reversal_retry_count = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    refund_id = Column(String(100), nullable=True)
    refund_failed_at = Column(DateTime(timezone=True), nullable=True)
    refund_error = Column(String(500), nullable=True)
    refund_retry_count = Column(Integer, nullable=False, default=0, server_default=text("0"))

    payout_transfer_id = Column(String(100), nullable=True)
    advanced_payout_transfer_id = Column(String(100), nullable=True)
    payout_transfer_failed_at = Column(DateTime(timezone=True), nullable=True)
    payout_transfer_error = Column(String(500), nullable=True)
    payout_transfer_retry_count = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    booking = relationship("Booking", back_populates="transfer")

    def __repr__(self) -> str:
        return f"<BookingTransfer booking={self.booking_id}>"
