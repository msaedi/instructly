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
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base

logger = logging.getLogger(__name__)

IS_SQLITE = os.getenv("DB_DIALECT", "").lower().startswith("sqlite")


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
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Cancellation tracking
    cancelled_by_id = Column(String(26), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # No-show tracking (v2.1.1)
    no_show_reported_by = Column(String(26), ForeignKey("users.id"), nullable=True)
    no_show_reported_at = Column(DateTime(timezone=True), nullable=True)
    no_show_type = Column(String(20), nullable=True)  # "instructor" | "student"
    no_show_disputed = Column(Boolean, nullable=False, default=False)
    no_show_disputed_at = Column(DateTime(timezone=True), nullable=True)
    no_show_dispute_reason = Column(String(500), nullable=True)
    no_show_resolved_at = Column(DateTime(timezone=True), nullable=True)
    no_show_resolution = Column(String(30), nullable=True)

    # Payment fields (Phase 1.2)
    payment_method_id = Column(String(255), nullable=True, comment="Stripe payment method ID")
    payment_intent_id = Column(String(255), nullable=True, comment="Current Stripe payment intent")
    payment_status = Column(
        String(50),
        nullable=True,
        comment="Canonical payment status per v2.1.1 policy",
    )
    auth_scheduled_for = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When authorization is scheduled to run (v2.1.1)",
    )
    auth_attempted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time authorization was attempted (v2.1.1)",
    )
    auth_failure_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Authorization failure count (v2.1.1)",
    )
    auth_last_error = Column(
        String(500),
        nullable=True,
        comment="Last authorization error (v2.1.1)",
    )
    auth_failure_first_email_sent_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="First auth failure email sent at (v2.1.1)",
    )
    auth_failure_t13_warning_sent_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="T-13 warning email sent at (v2.1.1)",
    )
    credits_reserved_cents = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Credits reserved for this booking in cents (v2.1.1)",
    )
    # settlement_outcome values per v2.1.1 policy:
    # - lesson_completed_full_payout
    # - student_cancel_12_24_full_credit
    # - student_cancel_lt12_split_50_50
    # - student_cancel_gt24_no_charge
    # - locked_cancel_ge12_full_credit
    # - locked_cancel_lt12_split_50_50
    # - instructor_cancel_full_refund
    # - instructor_no_show_full_refund
    # - student_wins_dispute_full_refund
    # - capture_failure_instructor_paid
    # - dispute_won
    # - admin_refund
    # - admin_no_refund
    settlement_outcome = Column(
        String(50),
        nullable=True,
        comment="Policy settlement outcome (v2.1.1)",
    )
    student_credit_amount = Column(
        Integer,
        nullable=True,
        comment="Student credit issued in cents (v2.1.1)",
    )
    instructor_payout_amount = Column(
        Integer,
        nullable=True,
        comment="Instructor payout in cents (v2.1.1)",
    )
    refunded_to_card_amount = Column(
        Integer,
        nullable=True,
        comment="Refunded to card in cents (v2.1.1)",
    )

    # Dispute tracking (v2.1.1 failure handling)
    dispute_id = Column(String(100), nullable=True, comment="Stripe dispute id (v2.1.1)")
    dispute_status = Column(String(30), nullable=True, comment="Stripe dispute status (v2.1.1)")
    dispute_amount = Column(Integer, nullable=True, comment="Dispute amount in cents (v2.1.1)")
    dispute_created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Dispute opened at (v2.1.1)",
    )
    dispute_resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Dispute resolved at (v2.1.1)",
    )

    # Transfer reversal tracking (v2.1.1 failure handling)
    stripe_transfer_id = Column(
        String(100),
        nullable=True,
        comment="Stripe transfer id (v2.1.1)",
    )
    refund_id = Column(
        String(100),
        nullable=True,
        comment="Stripe refund id (v2.1.1)",
    )
    payout_transfer_id = Column(
        String(100),
        nullable=True,
        comment="Manual payout transfer id (v2.1.1)",
    )
    advanced_payout_transfer_id = Column(
        String(100),
        nullable=True,
        comment="Manual payout transfer id for capture failure escalation (v2.1.1)",
    )
    transfer_failed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Transfer failure timestamp (v2.1.1)",
    )
    transfer_error = Column(
        String(500),
        nullable=True,
        comment="Transfer error (v2.1.1)",
    )
    transfer_retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Transfer retry count (v2.1.1)",
    )
    transfer_reversed = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Transfer reversed (v2.1.1)",
    )
    transfer_reversal_id = Column(
        String(100),
        nullable=True,
        comment="Stripe transfer reversal id (v2.1.1)",
    )
    transfer_reversal_failed = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Transfer reversal failed (v2.1.1)",
    )
    transfer_reversal_error = Column(
        String(500),
        nullable=True,
        comment="Transfer reversal error (v2.1.1)",
    )
    transfer_reversal_failed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Transfer reversal failure timestamp (v2.1.1)",
    )
    transfer_reversal_retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Transfer reversal retry count (v2.1.1)",
    )
    refund_failed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Refund failure timestamp (v2.1.1)",
    )
    refund_error = Column(
        String(500),
        nullable=True,
        comment="Refund error (v2.1.1)",
    )
    refund_retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Refund retry count (v2.1.1)",
    )
    payout_transfer_failed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Manual payout transfer failure timestamp (v2.1.1)",
    )
    payout_transfer_error = Column(
        String(500),
        nullable=True,
        comment="Manual payout transfer error (v2.1.1)",
    )
    payout_transfer_retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Manual payout transfer retry count (v2.1.1)",
    )

    # Capture failure tracking (v2.1.1 failure handling)
    capture_failed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Capture failure timestamp (v2.1.1)",
    )
    capture_escalated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Capture escalation timestamp (v2.1.1)",
    )
    capture_retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Capture retry count (v2.1.1)",
    )
    capture_error = Column(
        String(500),
        nullable=True,
        comment="Capture error (v2.1.1)",
    )

    # LOCK mechanism fields (v2.1.1 anti-gaming)
    locked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When LOCK was activated (v2.1.1)",
    )
    locked_amount_cents = Column(
        Integer,
        nullable=True,
        comment="Amount held under LOCK in cents (v2.1.1)",
    )
    lock_resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When LOCK was resolved (v2.1.1)",
    )
    lock_resolution = Column(
        String(50),
        nullable=True,
        comment="LOCK resolution outcome (v2.1.1)",
    )

    # Reschedule tracking (v2.1.1)
    late_reschedule_used = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Late reschedule used in 12-24h window (v2.1.1)",
    )
    reschedule_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total reschedule count (v2.1.1)",
    )

    # Relationships
    student = relationship("User", foreign_keys=[student_id], backref="student_bookings")
    instructor = relationship("User", foreign_keys=[instructor_id], backref="instructor_bookings")
    instructor_service = relationship("InstructorService", backref="bookings")
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    no_show_reporter = relationship("User", foreign_keys=[no_show_reported_by])
    messages = relationship("Message", back_populates="booking", cascade="all, delete-orphan")
    payment_intent = relationship(
        "PaymentIntent", back_populates="booking", uselist=False, cascade="all, delete-orphan"
    )
    payment_events = relationship(
        "PaymentEvent", back_populates="booking", cascade="all, delete-orphan"
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
    rescheduled_to_booking_id = Column(String(26), ForeignKey("bookings.id"), nullable=True)
    rescheduled_to = relationship(
        "Booking",
        remote_side=[id],
        uselist=False,
        post_update=True,
        foreign_keys=[rescheduled_to_booking_id],
    )
    has_locked_funds = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="New booking has funds locked from reschedule (v2.1.1)",
    )

    # Lesson datetime of the IMMEDIATE previous booking when rescheduled.
    # Used for Part 4b: Fair Reschedule Loophole Fix - gaming detection.
    #
    # IMPORTANT: This is NOT traced back to the original booking in a chain.
    # It stores the lesson datetime of the booking the user rescheduled FROM.
    #
    # Policy:
    # - If rescheduled while >24h from PREVIOUS booking → legitimate, normal cancel policy
    # - If rescheduled while <24h from PREVIOUS booking → gaming attempt, credit-only policy
    original_lesson_datetime = Column(DateTime(timezone=True), nullable=True)

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
        CheckConstraint(
            "payment_status IS NULL OR payment_status IN ("
            "'scheduled','authorized','payment_method_required','manual_review','locked','settled'"
            ")",
            name="ck_bookings_payment_status",
        ),
        CheckConstraint(
            "no_show_type IS NULL OR no_show_type IN ('instructor', 'student')",
            name="ck_bookings_no_show_type",
        ),
        CheckConstraint(
            "lock_resolution IS NULL OR lock_resolution IN ("
            "'new_lesson_completed',"
            "'new_lesson_cancelled_ge12',"
            "'new_lesson_cancelled_lt12',"
            "'instructor_cancelled',"
            "'completed',"
            "'cancelled_by_student',"
            "'cancelled_by_instructor',"
            "'expired'"
            ")",
            name="ck_bookings_lock_resolution",
        ),
    ]

    if not IS_SQLITE:
        _table_constraints.append(
            CheckConstraint(
                "CASE "
                "WHEN end_time = '00:00:00' AND start_time <> '00:00:00' THEN TRUE "
                "ELSE start_time < end_time "
                "END",
                name="check_time_order",
            )
        )

    __table_args__ = tuple(_table_constraints)

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
            "no_show_reported_by": self.no_show_reported_by,
            "no_show_reported_at": self.no_show_reported_at.isoformat()
            if self.no_show_reported_at
            else None,
            "no_show_type": self.no_show_type,
            "no_show_disputed": self.no_show_disputed,
            "no_show_disputed_at": self.no_show_disputed_at.isoformat()
            if self.no_show_disputed_at
            else None,
            "no_show_dispute_reason": self.no_show_dispute_reason,
            "no_show_resolved_at": self.no_show_resolved_at.isoformat()
            if self.no_show_resolved_at
            else None,
            "no_show_resolution": self.no_show_resolution,
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
