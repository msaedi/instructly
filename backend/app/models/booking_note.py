"""Admin notes attached to bookings."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from ..database import Base

if TYPE_CHECKING:
    from .booking import Booking
    from .user import User


class BookingNote(Base):
    """Internal/admin notes for bookings."""

    __tablename__ = "booking_notes"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    booking: Mapped["Booking"] = relationship("Booking", back_populates="admin_notes")
    created_by: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<BookingNote {self.id} booking={self.booking_id} visibility={self.visibility}>"
