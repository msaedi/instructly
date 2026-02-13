# backend/app/models/booking.py
"""
Booking model for InstaInstru platform.

Represents instant bookings between students and instructors.
Bookings are self-contained records with all necessary information,
achieving complete independence from availability slots.

Architecture: Bookings store instructor, date, and time data directly.
This allows bookings to persist as commitments regardless of
availability changes ("Rug and Person" principle).
"""

from datetime import date, datetime, timezone
from enum import Enum
import logging
import os
from typing import Any, Callable, Optional, cast

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import object_session, relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base

logger = logging.getLogger(__name__)

IS_SQLITE = os.getenv("DB_DIALECT", "").lower().startswith("sqlite")


def _build_payment_hybrid(field_name: str) -> Any:
    """Return a hybrid descriptor backed by BookingPayment.<field_name>."""

    def _getter(self: "Booking") -> Any:
        return self._get_payment_detail_value(field_name)

    def _setter(self: "Booking", value: Any) -> None:
        self._set_payment_detail_value(field_name, value)

    def _expression(owner_cls: type["Booking"]) -> Any:
        from .booking_payment import BookingPayment

        return (
            select(getattr(BookingPayment, field_name))
            .where(BookingPayment.booking_id == owner_cls.id)
            .correlate_except(BookingPayment)
            .scalar_subquery()
        )

    descriptor = hybrid_property(_getter)
    descriptor = descriptor.setter(_setter)
    descriptor = descriptor.expression(_expression)
    return descriptor


class BookingStatus(str, Enum):
    """Booking lifecycle statuses.

    Case-insensitive: accepts 'completed', 'COMPLETED', or 'Completed'.
    """

    PENDING = "PENDING"  # Reserved for future use
    CONFIRMED = "CONFIRMED"  # Default - instant booking
    COMPLETED = "COMPLETED"  # Lesson completed
    CANCELLED = "CANCELLED"  # Booking cancelled
    NO_SHOW = "NO_SHOW"  # Student didn't attend

    @classmethod
    def _missing_(cls, value: object) -> "BookingStatus | None":
        """Handle case-insensitive enum lookup."""
        if isinstance(value, str):
            upper_value = value.upper()
            for member in cls:
                if member.value == upper_value:
                    return member
        return None


class PaymentStatus(str, Enum):
    """Canonical payment statuses per v2.1.1 policy."""

    SCHEDULED = "scheduled"
    AUTHORIZED = "authorized"
    PAYMENT_METHOD_REQUIRED = "payment_method_required"
    MANUAL_REVIEW = "manual_review"
    LOCKED = "locked"
    SETTLED = "settled"

    @classmethod
    def _missing_(cls, value: object) -> "PaymentStatus | None":
        """Handle case-insensitive enum lookup."""
        if isinstance(value, str):
            lower_value = value.lower()
            for member in cls:
                if member.value == lower_value:
                    return member
        return None


class LocationType(str, Enum):
    """Where the lesson will take place."""

    STUDENT_LOCATION = "student_location"
    INSTRUCTOR_LOCATION = "instructor_location"
    ONLINE = "online"
    NEUTRAL_LOCATION = "neutral_location"


class Booking(Base):
    """
    Self-contained booking record between student and instructor.

    Design: Bookings are instant (confirmed immediately) and store all
    necessary data directly, with no dependency on availability slots.
    Service details are snapshotted at booking time for historical accuracy.
    """

    __tablename__ = "bookings"

    # Primary key
    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))

    # Core relationships
    student_id = Column(String(26), ForeignKey("users.id"), nullable=False)
    instructor_id = Column(String(26), ForeignKey("users.id"), nullable=False)
    instructor_service_id = Column(String(26), ForeignKey("instructor_services.id"), nullable=False)

    # Self-contained booking data
    booking_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    booking_start_utc = Column(DateTime(timezone=True), nullable=False, index=True)
    booking_end_utc = Column(DateTime(timezone=True), nullable=False)
    lesson_timezone = Column(String(50), nullable=True)
    instructor_tz_at_booking = Column(String(50), nullable=True)
    student_tz_at_booking = Column(String(50), nullable=True)

    # Service snapshot (preserved for history)
    service_name = Column(String, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    # Booking details
    status = Column(String(20), nullable=False, default=BookingStatus.CONFIRMED, index=True)
    service_area = Column(String, nullable=True)
    location_type = Column(String(50), nullable=True, default=LocationType.ONLINE)
    meeting_location = Column(Text, nullable=True)
    location_address = Column(Text, nullable=True)
    location_lat = Column(Numeric(10, 8), nullable=True)
    location_lng = Column(Numeric(11, 8), nullable=True)
    location_place_id = Column(String(255), nullable=True)
    student_note = Column(Text, nullable=True)
    instructor_note = Column(Text, nullable=True)
    reminder_24h_sent = Column(Boolean, nullable=False, default=False)
    reminder_1h_sent = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Cancellation tracking
    cancelled_by_id = Column(String(26), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Settlement values still stored on booking core
    student_credit_amount = Column(
        Integer,
        nullable=True,
        comment="Student credit issued in cents (v2.1.1)",
    )
    refunded_to_card_amount = Column(
        Integer,
        nullable=True,
        comment="Refunded to card in cents (v2.1.1)",
    )

    # Relationships
    student = relationship("User", foreign_keys=[student_id], backref="student_bookings")
    instructor = relationship("User", foreign_keys=[instructor_id], backref="instructor_bookings")
    instructor_service = relationship("InstructorService", backref="bookings")
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    messages = relationship("Message", back_populates="booking", cascade="all, delete-orphan")
    payment_intent = relationship(
        "PaymentIntent", back_populates="booking", uselist=False, cascade="all, delete-orphan"
    )
    payment_events = relationship(
        "PaymentEvent", back_populates="booking", cascade="all, delete-orphan"
    )
    payment_detail = relationship(
        "BookingPayment",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    no_show_detail = relationship(
        "BookingNoShow",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    lock_detail = relationship(
        "BookingLock",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    reschedule_detail = relationship(
        "BookingReschedule",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
        foreign_keys="BookingReschedule.booking_id",
    )
    dispute = relationship(
        "BookingDispute",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    transfer = relationship(
        "BookingTransfer",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    generated_credits = relationship(
        "PlatformCredit",
        foreign_keys="PlatformCredit.source_booking_id",
        back_populates="source_booking",
    )
    used_credits = relationship(
        "PlatformCredit",
        foreign_keys="PlatformCredit.used_booking_id",
        back_populates="used_booking",
    )
    reserved_credits = relationship(
        "PlatformCredit",
        foreign_keys="PlatformCredit.reserved_for_booking_id",
        back_populates="reserved_for_booking",
    )
    admin_notes = relationship(
        "BookingNote", back_populates="booking", cascade="all, delete-orphan"
    )

    # Optional linkage when created by reschedule
    rescheduled_from_booking_id = Column(String(26), ForeignKey("bookings.id"), nullable=True)
    rescheduled_from = relationship(
        "Booking",
        remote_side=[id],
        uselist=False,
        post_update=True,
        foreign_keys=[rescheduled_from_booking_id],
    )
    has_locked_funds = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="New booking has funds locked from reschedule (v2.1.1)",
    )

    # Data integrity constraints
    _table_constraints = [
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
            name="ck_bookings_status",
        ),
        CheckConstraint(
            "location_type IN ('student_location', 'instructor_location', 'online', 'neutral_location')",
            name="ck_bookings_location_type",
        ),
        CheckConstraint("duration_minutes > 0", name="check_duration_positive"),
        CheckConstraint("total_price >= 0", name="check_price_non_negative"),
        CheckConstraint("hourly_rate > 0", name="check_rate_positive"),
    ]

    if not IS_SQLITE:
        _table_constraints.append(
            CheckConstraint(
                "CASE " "WHEN end_time < start_time THEN TRUE " "ELSE start_time < end_time " "END",
                name="check_time_order",
            )
        )

    __table_args__ = tuple(_table_constraints)

    def _get_payment_detail_value(self, field_name: str) -> Any:
        payment_detail = getattr(self, "payment_detail", None)
        if payment_detail is None and getattr(self, "id", None):
            session = object_session(self)
            if session is not None:
                from .booking_payment import BookingPayment

                payment_detail = (
                    session.query(BookingPayment)
                    .filter(BookingPayment.booking_id == self.id)
                    .one_or_none()
                )
                if payment_detail is not None:
                    self.payment_detail = payment_detail
        if payment_detail is None:
            return None
        return getattr(payment_detail, field_name, None)

    def _set_payment_detail_value(self, field_name: str, value: Any) -> None:
        payment_detail = getattr(self, "payment_detail", None)
        if payment_detail is None:
            from .booking_payment import BookingPayment

            existing_detail = None
            if getattr(self, "id", None):
                session = object_session(self)
                if session is not None:
                    existing_detail = (
                        session.query(BookingPayment)
                        .filter(BookingPayment.booking_id == self.id)
                        .one_or_none()
                    )
            payment_detail = existing_detail or BookingPayment()
            self.payment_detail = payment_detail
        setattr(payment_detail, field_name, value)

    payment_method_id = _build_payment_hybrid("payment_method_id")
    payment_intent_id = _build_payment_hybrid("payment_intent_id")
    payment_status = _build_payment_hybrid("payment_status")
    auth_scheduled_for = _build_payment_hybrid("auth_scheduled_for")
    auth_attempted_at = _build_payment_hybrid("auth_attempted_at")
    auth_failure_count = _build_payment_hybrid("auth_failure_count")
    auth_last_error = _build_payment_hybrid("auth_last_error")
    auth_failure_first_email_sent_at = _build_payment_hybrid("auth_failure_first_email_sent_at")
    auth_failure_t13_warning_sent_at = _build_payment_hybrid("auth_failure_t13_warning_sent_at")
    credits_reserved_cents = _build_payment_hybrid("credits_reserved_cents")
    settlement_outcome = _build_payment_hybrid("settlement_outcome")
    instructor_payout_amount = _build_payment_hybrid("instructor_payout_amount")
    capture_failed_at = _build_payment_hybrid("capture_failed_at")
    capture_escalated_at = _build_payment_hybrid("capture_escalated_at")
    capture_retry_count = _build_payment_hybrid("capture_retry_count")
    capture_error = _build_payment_hybrid("capture_error")

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with instant confirmation by default."""
        super().__init__(**kwargs)
        if not self.status:
            self.status = BookingStatus.CONFIRMED
        logger.info(
            f"Creating booking for student {self.student_id} with instructor {self.instructor_id}"
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Booking {self.id}: student={self.student_id}, "
            f"instructor={self.instructor_id}, date={self.booking_date}, "
            f"time={self.start_time}-{self.end_time}, status={self.status}>"
        )

    def cancel(self, cancelled_by_user_id: int, reason: Optional[str] = None) -> None:
        """Cancel this booking."""
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = datetime.now(timezone.utc)
        self.cancelled_by_id = cancelled_by_user_id
        self.cancellation_reason = reason
        logger.info(f"Booking {self.id} cancelled by user {cancelled_by_user_id}")

    def complete(self) -> None:
        """Mark booking as completed."""
        self.status = BookingStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        logger.info(f"Booking {self.id} marked as completed")

    def mark_no_show(self) -> None:
        """Mark booking as no-show."""
        self.status = BookingStatus.NO_SHOW
        logger.info(f"Booking {self.id} marked as no-show")

    @property
    def is_cancellable(self) -> bool:
        """Check if booking can be cancelled."""
        return self.status in [BookingStatus.CONFIRMED, BookingStatus.PENDING]

    def is_upcoming(self, user_today: date) -> bool:
        """
        Check if booking is in the future.

        Args:
            user_today: Today's date in user's timezone (required)
        """
        booking_date = cast(date, self.booking_date)
        return booking_date > user_today and self.status == BookingStatus.CONFIRMED

    def is_past(self, user_today: date) -> bool:
        """
        Check if booking date has passed.

        Args:
            user_today: Today's date in user's timezone (required)
        """
        booking_date = cast(date, self.booking_date)
        return booking_date < user_today

    @property
    def location_type_display(self) -> str:
        """Get human-readable location type."""
        location = cast("LocationType | None", self.location_type)
        return {
            LocationType.STUDENT_LOCATION: "Student Location",
            LocationType.INSTRUCTOR_LOCATION: "Instructor's Location",
            LocationType.ONLINE: "Online",
            LocationType.NEUTRAL_LOCATION: "Neutral Location",
        }.get(location or LocationType.ONLINE, "Online")

    @property
    def can_be_modified_by(self) -> Callable[[str], bool]:
        """Return a helper that checks whether the given user can modify this booking."""

        def _checker(user_id: str) -> bool:
            return user_id in (self.student_id, self.instructor_id)

        return _checker

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "student_id": self.student_id,
            "instructor_id": self.instructor_id,
            "instructor_service_id": self.instructor_service_id,
            "booking_date": self.booking_date.isoformat() if self.booking_date else None,
            "start_time": str(self.start_time) if self.start_time else None,
            "end_time": str(self.end_time) if self.end_time else None,
            "service_name": self.service_name,
            "hourly_rate": float(self.hourly_rate),
            "total_price": float(self.total_price),
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "location_type": self.location_type,
            "location_type_display": self.location_type_display,
            "meeting_location": self.meeting_location,
            "location_address": self.location_address,
            "location_lat": float(self.location_lat) if self.location_lat is not None else None,
            "location_lng": float(self.location_lng) if self.location_lng is not None else None,
            "location_place_id": self.location_place_id,
            "service_area": self.service_area,
            "student_note": self.student_note,
            "instructor_note": self.instructor_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "cancelled_by_id": self.cancelled_by_id,
            "cancellation_reason": self.cancellation_reason,
        }


Index(
    "ix_booking_instructor_completed",
    Booking.instructor_id,
    Booking.status,
    Booking.completed_at,
    postgresql_where=(Booking.status == BookingStatus.COMPLETED),
)


Index(
    "ix_booking_student_completed",
    Booking.student_id,
    Booking.status,
    Booking.completed_at,
    postgresql_where=(Booking.status == BookingStatus.COMPLETED),
)

Index(
    "ix_bookings_instructor_date_status",
    Booking.instructor_id,
    Booking.booking_date,
    Booking.status,
)

Index(
    "ix_bookings_student_date_status",
    Booking.student_id,
    Booking.booking_date,
    Booking.status,
)
