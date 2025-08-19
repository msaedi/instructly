"""
Payment models for Stripe integration.

This module defines the payment-related models for InstaInstru's
Stripe Connect integration, including customer records, connected accounts,
payment intents, and payment methods.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import ulid
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.instructor import InstructorProfile
    from app.models.user import User


class StripeCustomer(Base):
    """Maps users to their Stripe customer IDs."""

    __tablename__ = "stripe_customers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_customer_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="stripe_customer")

    def __repr__(self) -> str:
        return f"<StripeCustomer(user_id={self.user_id}, stripe_id={self.stripe_customer_id})>"


class StripeConnectedAccount(Base):
    """Instructor Stripe Connect accounts for receiving payments."""

    __tablename__ = "stripe_connected_accounts"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_profile_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    stripe_account_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    instructor_profile: Mapped["InstructorProfile"] = relationship(
        "InstructorProfile", back_populates="stripe_connected_account"
    )

    def __repr__(self) -> str:
        return f"<StripeConnectedAccount(instructor_id={self.instructor_profile_id}, completed={self.onboarding_completed})>"


class PaymentIntent(Base):
    """Stripe payment intents for booking payments."""

    __tablename__ = "payment_intents"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    booking_id: Mapped[str] = mapped_column(String(26), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, comment="Amount in cents")
    application_fee: Mapped[int] = mapped_column(Integer, nullable=False, comment="Platform fee in cents")
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="payment_intent")

    def __repr__(self) -> str:
        return f"<PaymentIntent(booking_id={self.booking_id}, amount={self.amount}, status={self.status})>"


class PaymentMethod(Base):
    """User payment methods (cards)."""

    __tablename__ = "payment_methods"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_payment_method_id: Mapped[str] = mapped_column(String(255), nullable=False)
    last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payment_methods")

    def __repr__(self) -> str:
        return f"<PaymentMethod(user_id={self.user_id}, last4={self.last4}, default={self.is_default})>"
