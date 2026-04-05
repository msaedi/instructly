# backend/app/models/booking.py
"""Booking model for InstaInstru platform.

Represents self-contained instant bookings between students and instructors.
Bookings store instructor, date, and time data directly so they persist as
commitments regardless of availability changes ("Rug and Person" principle).
"""

from datetime import date, datetime, timezone
from enum import Enum
import logging
import os
from typing import Any, Callable, Final, Optional, cast

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
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base

logger = logging.getLogger(__name__)

IS_SQLITE = os.getenv("DB_DIALECT", "").lower().startswith("sqlite")


class _Unset:
    """Sentinel for 'caller did not pass this argument'."""


_UNSET: Final = _Unset()


class BookingStatus(str, Enum):
    """Booking lifecycle statuses.

    Case-insensitive: accepts 'completed', 'COMPLETED', or 'Completed'.
    """

    PENDING = "PENDING"  # Booking exists but payment/setup is not complete
    CONFIRMED = "CONFIRMED"  # Booking confirmed after payment succeeds
    COMPLETED = "COMPLETED"  # Lesson completed
    CANCELLED = "CANCELLED"  # Booking cancelled
    PAYMENT_FAILED = "PAYMENT_FAILED"  # Booking never confirmed because payment failed
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
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Cancellation tracking
    cancelled_by_id = Column(String(26), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # NOTE: student_credit_amount and refunded_to_card_amount remain on the core
    # bookings table because they represent student-facing refund disposition
    # (set during cancellation), not payment processing state. The payment
    # satellite (BookingPayment) holds instructor-facing and Stripe-facing fields
    # (settlement_outcome, instructor_payout_amount, credits_reserved_cents).
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
    video_session = relationship(
        "BookingVideoSession",
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
    rescheduled_from_booking_id = Column(
        String(26), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
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
            "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'PAYMENT_FAILED', 'NO_SHOW')",
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

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with instant confirmation by default."""
        super().__init__(**kwargs)
        if not self.status:
            self.status = BookingStatus.CONFIRMED
        if self.status == BookingStatus.CONFIRMED and self.confirmed_at is None:
            # Services usually pass this explicitly; this is the fallback that keeps
            # any other confirmed-booking creation path from missing the timestamp.
            self.confirmed_at = datetime.now(timezone.utc)
        logger.info(
            "Creating booking for student %s with instructor %s",
            self.student_id,
            self.instructor_id,
        )

    _ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
        BookingStatus.PENDING: {
            BookingStatus.CONFIRMED,
            # Admin override — skip CONFIRMED for manual completion.
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.PAYMENT_FAILED,
        },
        BookingStatus.CONFIRMED: {
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
        },
        BookingStatus.COMPLETED: {
            # Admin refund — post-completion cancellation with refund.
            BookingStatus.CANCELLED,
            # Admin correction — dispute resolution can reverse a completion.
            BookingStatus.NO_SHOW,
        },
        BookingStatus.CANCELLED: set(),
        BookingStatus.PAYMENT_FAILED: set(),
        BookingStatus.NO_SHOW: {
            # No-show resolution — cancelled dispute restores original state.
            BookingStatus.CONFIRMED,
            # No-show resolution — dispute upheld, lesson actually occurred.
            BookingStatus.COMPLETED,
            # No-show resolution — admin cancels after no-show.
            BookingStatus.CANCELLED,
        },
    }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Booking {self.id}: student={self.student_id}, "
            f"instructor={self.instructor_id}, date={self.booking_date}, "
            f"time={self.start_time}-{self.end_time}, status={self.status}>"
        )

    @property
    def normalized_status(self) -> BookingStatus:
        """Return the enum value for the current booking status."""
        return BookingStatus(self.status)

    def can_transition_to(self, next_status: BookingStatus | str) -> bool:
        """Return whether the booking can move to the requested status."""
        target = BookingStatus(next_status)
        current = self.normalized_status
        return target == current or target in self._ALLOWED_TRANSITIONS.get(current, set())

    def assert_can_transition_to(self, next_status: BookingStatus | str) -> BookingStatus:
        """Raise when the requested status change is not allowed."""
        target = BookingStatus(next_status)
        if not self.can_transition_to(target):
            raise ValueError(f"Invalid booking status transition: {self.status} -> {target.value}")
        return target

    def mark_confirmed(self, *, confirmed_at: datetime | None | _Unset = _UNSET) -> None:
        """Mark booking as confirmed."""
        self.assert_can_transition_to(BookingStatus.CONFIRMED)
        self.status = BookingStatus.CONFIRMED
        if confirmed_at is _UNSET:
            if self.confirmed_at is None:
                self.confirmed_at = datetime.now(timezone.utc)
        else:
            self.confirmed_at = cast(datetime | None, confirmed_at)
        logger.info("Booking %s marked as confirmed", self.id)

    def mark_pending(self, *, confirmed_at: datetime | None | _Unset = _UNSET) -> None:
        """Mark booking as pending."""
        # Intentionally same-state-only: this is used to clear confirmed_at on
        # already-PENDING bookings during payment setup/retry flows.
        self.assert_can_transition_to(BookingStatus.PENDING)
        self.status = BookingStatus.PENDING
        if confirmed_at is not _UNSET:
            self.confirmed_at = cast(datetime | None, confirmed_at)
        logger.info("Booking %s marked as pending", self.id)

    def mark_cancelled(
        self,
        *,
        cancelled_at: datetime | None | _Unset = _UNSET,
        cancelled_by_user_id: str | None | _Unset = _UNSET,
        reason: Optional[str] | _Unset = _UNSET,
    ) -> None:
        """Mark booking as cancelled."""
        self.assert_can_transition_to(BookingStatus.CANCELLED)
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = (
            datetime.now(timezone.utc)
            if cancelled_at is _UNSET
            else cast(datetime | None, cancelled_at)
        )
        if cancelled_by_user_id is not _UNSET:
            self.cancelled_by_id = cast(str | None, cancelled_by_user_id)
        if reason is not _UNSET:
            self.cancellation_reason = cast(Optional[str], reason)
        logger.info("Booking %s marked as cancelled", self.id)

    def cancel(self, cancelled_by_user_id: str, reason: Optional[str] = None) -> None:
        """Cancel this booking."""
        self.mark_cancelled(
            cancelled_by_user_id=cancelled_by_user_id,
            reason=reason,
        )

    def mark_completed(self, *, completed_at: datetime | None | _Unset = _UNSET) -> None:
        """Mark booking as completed."""
        self.assert_can_transition_to(BookingStatus.COMPLETED)
        self.status = BookingStatus.COMPLETED
        self.completed_at = (
            datetime.now(timezone.utc)
            if completed_at is _UNSET
            else cast(datetime | None, completed_at)
        )
        logger.info("Booking %s marked as completed", self.id)

    def complete(self) -> None:
        """Mark booking as completed."""
        self.mark_completed()

    def mark_no_show(
        self,
        *,
        cancelled_at: datetime | None | _Unset = _UNSET,
        cancelled_by_user_id: str | None | _Unset = _UNSET,
    ) -> None:
        """Mark booking as no-show."""
        self.assert_can_transition_to(BookingStatus.NO_SHOW)
        self.status = BookingStatus.NO_SHOW
        if cancelled_at is not _UNSET:
            self.cancelled_at = cast(datetime | None, cancelled_at)
        if cancelled_by_user_id is not _UNSET:
            self.cancelled_by_id = cast(str | None, cancelled_by_user_id)
        logger.info("Booking %s marked as no-show", self.id)

    def mark_payment_failed(self) -> None:
        """Mark booking as payment failed without treating it as cancelled."""
        self.assert_can_transition_to(BookingStatus.PAYMENT_FAILED)
        self.status = BookingStatus.PAYMENT_FAILED
        self.confirmed_at = None
        logger.info("Booking %s marked as payment failed", self.id)

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

    @staticmethod
    def _serialize_dt(value: Any) -> Any:
        return value.isoformat() if value else None

    def _base_dict(self) -> dict[str, Any]:
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
            "created_at": self._serialize_dt(self.created_at),
            "updated_at": self._serialize_dt(self.updated_at),
            "confirmed_at": self._serialize_dt(self.confirmed_at),
            "completed_at": self._serialize_dt(self.completed_at),
            "cancelled_at": self._serialize_dt(self.cancelled_at),
            "cancelled_by_id": self.cancelled_by_id,
            "cancellation_reason": self.cancellation_reason,
        }

    def _merge_payment_detail(self, data: dict[str, Any]) -> None:
        pd = getattr(self, "payment_detail", None)
        if pd is None:
            return
        data.update(
            {
                "payment_method_id": pd.payment_method_id,
                "payment_intent_id": pd.payment_intent_id,
                "payment_status": pd.payment_status,
                "auth_scheduled_for": self._serialize_dt(pd.auth_scheduled_for),
                "auth_attempted_at": self._serialize_dt(pd.auth_attempted_at),
                "auth_failure_count": pd.auth_failure_count,
                "auth_last_error": pd.auth_last_error,
                "auth_failure_first_email_sent_at": self._serialize_dt(
                    pd.auth_failure_first_email_sent_at
                ),
                "auth_failure_t13_warning_sent_at": self._serialize_dt(
                    pd.auth_failure_t13_warning_sent_at
                ),
                "credits_reserved_cents": pd.credits_reserved_cents,
                "settlement_outcome": pd.settlement_outcome,
                "instructor_payout_amount": pd.instructor_payout_amount,
                "capture_failed_at": self._serialize_dt(pd.capture_failed_at),
                "capture_escalated_at": self._serialize_dt(pd.capture_escalated_at),
                "capture_retry_count": pd.capture_retry_count,
                "capture_error": pd.capture_error,
            }
        )

    def _merge_no_show_detail(self, data: dict[str, Any]) -> None:
        ns = getattr(self, "no_show_detail", None)
        if ns is None:
            return
        data.update(
            {
                "no_show_reported_by": ns.no_show_reported_by,
                "no_show_reported_at": self._serialize_dt(ns.no_show_reported_at),
                "no_show_type": ns.no_show_type,
                "no_show_disputed": ns.no_show_disputed,
                "no_show_disputed_at": self._serialize_dt(ns.no_show_disputed_at),
                "no_show_dispute_reason": ns.no_show_dispute_reason,
                "no_show_resolved_at": self._serialize_dt(ns.no_show_resolved_at),
                "no_show_resolution": ns.no_show_resolution,
            }
        )

    def _merge_lock_detail(self, data: dict[str, Any]) -> None:
        lk = getattr(self, "lock_detail", None)
        if lk is None:
            return
        data.update(
            {
                "locked_at": self._serialize_dt(lk.locked_at),
                "locked_amount_cents": lk.locked_amount_cents,
                "lock_resolved_at": self._serialize_dt(lk.lock_resolved_at),
                "lock_resolution": lk.lock_resolution,
            }
        )

    def _merge_reschedule_detail(self, data: dict[str, Any]) -> None:
        rs = getattr(self, "reschedule_detail", None)
        if rs is None:
            return
        data.update(
            {
                "late_reschedule_used": rs.late_reschedule_used,
                "reschedule_count": rs.reschedule_count,
                "rescheduled_to_booking_id": rs.rescheduled_to_booking_id,
                "original_lesson_datetime": self._serialize_dt(rs.original_lesson_datetime),
            }
        )

    def _merge_dispute_detail(self, data: dict[str, Any]) -> None:
        dp = getattr(self, "dispute", None)
        if dp is None:
            return
        data.update(
            {
                "dispute_id": dp.dispute_id,
                "dispute_status": dp.dispute_status,
                "dispute_amount": dp.dispute_amount,
                "dispute_created_at": self._serialize_dt(dp.dispute_created_at),
                "dispute_resolved_at": self._serialize_dt(dp.dispute_resolved_at),
            }
        )

    def _merge_transfer_detail(self, data: dict[str, Any]) -> None:
        tr = getattr(self, "transfer", None)
        if tr is None:
            return
        data.update(
            {
                "stripe_transfer_id": tr.stripe_transfer_id,
                "transfer_failed_at": self._serialize_dt(tr.transfer_failed_at),
                "transfer_error": tr.transfer_error,
                "transfer_retry_count": tr.transfer_retry_count,
                "transfer_reversed": tr.transfer_reversed,
                "transfer_reversal_id": tr.transfer_reversal_id,
                "transfer_reversal_failed": tr.transfer_reversal_failed,
                "transfer_reversal_error": tr.transfer_reversal_error,
                "transfer_reversal_failed_at": self._serialize_dt(tr.transfer_reversal_failed_at),
                "transfer_reversal_retry_count": tr.transfer_reversal_retry_count,
                "refund_id": tr.refund_id,
                "refund_failed_at": self._serialize_dt(tr.refund_failed_at),
                "refund_error": tr.refund_error,
                "refund_retry_count": tr.refund_retry_count,
                "payout_transfer_id": tr.payout_transfer_id,
                "advanced_payout_transfer_id": tr.advanced_payout_transfer_id,
                "payout_transfer_failed_at": self._serialize_dt(tr.payout_transfer_failed_at),
                "payout_transfer_error": tr.payout_transfer_error,
                "payout_transfer_retry_count": tr.payout_transfer_retry_count,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses and audit trails."""
        data = self._base_dict()
        self._merge_payment_detail(data)
        self._merge_no_show_detail(data)
        self._merge_lock_detail(data)
        self._merge_reschedule_detail(data)
        self._merge_dispute_detail(data)
        self._merge_transfer_detail(data)
        return data


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
