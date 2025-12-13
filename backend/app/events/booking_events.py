"""Booking domain events."""
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class BookingCreated:
    """Fired after a booking is successfully created."""

    booking_id: str
    student_id: str
    instructor_id: str
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BookingCancelled:
    """Fired after a booking is cancelled."""

    booking_id: str
    cancelled_by: str  # 'student' or 'instructor'
    cancelled_at: datetime
    refund_amount: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BookingReminder:
    """Fired when a booking reminder should be sent."""

    booking_id: str
    reminder_type: str  # '24h' or '1h'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BookingCompleted:
    """Fired after a booking is marked complete."""

    booking_id: str
    completed_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
