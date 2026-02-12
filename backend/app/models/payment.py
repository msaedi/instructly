"""
Payment models for Stripe integration.

This module defines the payment-related models for InstaInstru's
Stripe Connect integration, including customer records, connected accounts,
payment intents, payment methods, payment events, and platform credits.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.instructor import InstructorProfile
    from app.models.user import User


class StripeCustomer(Base):
    """Maps users to their Stripe customer IDs."""

    __tablename__ = "stripe_customers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="stripe_customer")

    def __repr__(self) -> str:
        return f"<StripeCustomer(user_id={self.user_id}, stripe_id={self.stripe_customer_id})>"


class StripeConnectedAccount(Base):
    """Instructor Stripe Connect accounts for receiving payments."""

    __tablename__ = "stripe_connected_accounts"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_profile_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("instructor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    stripe_account_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    instructor_profile: Mapped["InstructorProfile"] = relationship(
        "InstructorProfile", back_populates="stripe_connected_account"
    )

    def __repr__(self) -> str:
        return f"<StripeConnectedAccount(instructor_id={self.instructor_profile_id}, completed={self.onboarding_completed})>"


class PaymentIntent(Base):
    """Stripe payment intents for booking payments."""

    __tablename__ = "payment_intents"
    __table_args__ = (Index("ix_payment_intents_booking", "booking_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, comment="Amount in cents")
    application_fee: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Platform fee in cents"
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Earnings metadata (stored at payment creation for accurate display)
    base_price_cents: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Lesson price in cents (hourly_rate * duration)"
    )
    instructor_tier_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Instructor platform fee rate (e.g., 0.12 for 12%)"
    )
    instructor_payout_cents: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Amount transferred to instructor in cents"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="payment_intent")

    def __repr__(self) -> str:
        return f"<PaymentIntent(booking_id={self.booking_id}, amount={self.amount}, status={self.status})>"


class PaymentMethod(Base):
    """User payment methods (cards)."""

    __tablename__ = "payment_methods"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stripe_payment_method_id: Mapped[str] = mapped_column(String(255), nullable=False)
    last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payment_methods")

    def __repr__(self) -> str:
        return f"<PaymentMethod(user_id={self.user_id}, last4={self.last4}, default={self.is_default})>"


class PaymentEvent(Base):
    """Track all payment state changes for bookings."""

    __tablename__ = "payment_events"
    __table_args__ = (Index("ix_payment_events_booking", "booking_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Types: card_saved, auth_scheduled, auth_attempted, auth_succeeded, auth_failed, "
        "capture_scheduled, captured, capture_failed, payout_scheduled, paid_out",
    )
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="Store stripe IDs, amounts, error messages"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="payment_events")

    def __repr__(self) -> str:
        return f"<PaymentEvent(booking_id={self.booking_id}, type={self.event_type})>"


class PlatformCredit(Base):
    """Platform credits for 12-24 hour cancellations."""

    __tablename__ = "platform_credits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'available', 'reserved', 'applied', 'forfeited', 'expired', 'frozen', 'revoked')",
            name="ck_platform_credits_status",
        ),
        Index("ix_platform_credits_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Amount in cents to avoid float precision issues"
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="legacy",
        comment="Credit source type (v2.1.1)",
    )
    source_booking_id: Mapped[Optional[str]] = mapped_column(
        String(26),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Booking that generated this credit",
    )
    used_booking_id: Mapped[Optional[str]] = mapped_column(
        String(26),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Booking where credit was used",
    )
    reserved_amount_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Amount reserved for a booking (v2.1.1)",
    )
    reserved_for_booking_id: Mapped[Optional[str]] = mapped_column(
        String(26),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Booking holding a reservation on this credit (v2.1.1)",
    )
    reserved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credit was reserved (v2.1.1)",
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    original_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Original expiration timestamp (v2.1.1)",
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    forfeited_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credit was forfeited (v2.1.1)",
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether credit was revoked (v2.1.1)",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credit was revoked (v2.1.1)",
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Reason credit was revoked (v2.1.1)",
    )
    frozen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credit was frozen (v2.1.1)",
    )
    frozen_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Reason credit was frozen (v2.1.1)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="available",
        comment="Credit status: available, reserved, forfeited, expired, frozen, revoked (v2.1.1)",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="platform_credits")
    source_booking: Mapped[Optional["Booking"]] = relationship(
        "Booking", foreign_keys=[source_booking_id], back_populates="generated_credits"
    )
    used_booking: Mapped[Optional["Booking"]] = relationship(
        "Booking", foreign_keys=[used_booking_id], back_populates="used_credits"
    )
    reserved_for_booking: Mapped[Optional["Booking"]] = relationship(
        "Booking", foreign_keys=[reserved_for_booking_id], back_populates="reserved_credits"
    )

    @property
    def is_expired(self) -> bool:
        """Check if the credit has expired."""
        if getattr(self, "status", None) == "reserved":
            return False
        if getattr(self, "status", None) == "frozen":
            return False
        if getattr(self, "status", None) == "revoked":
            return False
        if getattr(self, "status", None) == "expired":
            return True
        if not self.expires_at:
            return False
        # Always compare using timezone-aware UTC now to avoid naive/aware mismatches
        expires_at = cast(datetime, self.expires_at)
        if expires_at.tzinfo is None:
            normalized = expires_at.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > normalized
        current = datetime.now(timezone.utc).astimezone(expires_at.tzinfo)
        return current > expires_at

    @property
    def is_available(self) -> bool:
        """Check if the credit is available for use."""
        return getattr(self, "status", None) == "available" and not self.is_expired

    def __repr__(self) -> str:
        return (
            f"<PlatformCredit(user_id={self.user_id}, amount={self.amount_cents}, "
            f"status={getattr(self, 'status', None)}, available={self.is_available})>"
        )


class InstructorPayoutEvent(Base):
    """Persist payout-related events per instructor for analytics/auditing."""

    __tablename__ = "instructor_payout_events"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_profile_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payout_id: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=True)
    arrival_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<InstructorPayoutEvent(instructor_profile_id={self.instructor_profile_id}, payout_id={self.payout_id})>"
