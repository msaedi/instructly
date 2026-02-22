"""Booking video session satellite table."""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class BookingVideoSession(Base):
    """100ms video room/session state for a single booking."""

    __tablename__ = "booking_video_sessions"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id = Column(
        String(26),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # 100ms room identifiers
    room_id = Column(String(100), nullable=False)
    room_name = Column(String(255), nullable=True)

    # 100ms session (populated via webhook)
    session_id = Column(String(100), nullable=True)
    session_started_at = Column(DateTime(timezone=True), nullable=True)
    session_ended_at = Column(DateTime(timezone=True), nullable=True)
    session_duration_seconds = Column(Integer, nullable=True)

    # Participant tracking (populated via webhook)
    instructor_peer_id = Column(String(100), nullable=True)
    student_peer_id = Column(String(100), nullable=True)
    instructor_joined_at = Column(DateTime(timezone=True), nullable=True)
    student_joined_at = Column(DateTime(timezone=True), nullable=True)
    instructor_left_at = Column(DateTime(timezone=True), nullable=True)
    student_left_at = Column(DateTime(timezone=True), nullable=True)

    # Raw 100ms data for debugging
    provider_metadata = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"), nullable=True
    )

    # Record timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    booking = relationship("Booking", back_populates="video_session")

    def __repr__(self) -> str:
        return f"<BookingVideoSession booking={self.booking_id} room={self.room_id}>"
