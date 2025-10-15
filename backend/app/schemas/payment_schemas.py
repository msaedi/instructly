"""
Payment-related Pydantic schemas for InstaInstru platform.

Defines request and response models for Stripe payment integration,
including customer management, connected accounts, payment methods,
and payment processing.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel

# ========== Request Models ==========


class SavePaymentMethodRequest(StrictRequestModel):
    """Request to save a payment method for a user."""

    payment_method_id: str = Field(..., description="Stripe payment method ID")
    set_as_default: bool = Field(
        default=False, description="Whether to set as default payment method"
    )


class CreateCheckoutRequest(StrictRequestModel):
    """Request to create a checkout/payment for a booking."""

    booking_id: str = Field(..., description="Booking ID to process payment for")
    payment_method_id: str = Field(..., description="Stripe payment method ID to use")
    save_payment_method: bool = Field(
        default=False, description="Whether to save payment method for future use"
    )
    applied_credit_cents: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional wallet credit amount (in cents) the student chose to apply",
    )


# ========== Response Models ==========


class PaymentMethodResponse(StrictModel):
    """Response model for payment method information."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Payment method ID")
    last4: str = Field(..., description="Last 4 digits of card")
    brand: str = Field(..., description="Card brand (visa, mastercard, etc.)")
    is_default: bool = Field(..., description="Whether this is the default payment method")
    created_at: datetime = Field(..., description="When the payment method was added")


class OnboardingResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for starting instructor onboarding."""

    account_id: str = Field(..., description="Stripe connected account ID")
    onboarding_url: str = Field(..., description="URL for onboarding flow")
    already_onboarded: bool = Field(..., description="Whether onboarding was already completed")


class OnboardingStatusResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for onboarding status check."""

    has_account: bool = Field(..., description="Whether instructor has a connected account")
    onboarding_completed: bool = Field(..., description="Whether onboarding is complete")
    charges_enabled: bool = Field(..., description="Whether account can accept payments")
    payouts_enabled: bool = Field(default=False, description="Whether account can receive payouts")
    details_submitted: bool = Field(
        default=False, description="Whether required details are submitted"
    )
    requirements: List[str] = Field(default_factory=list, description="Outstanding requirements")


class DashboardLinkResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for Stripe Express dashboard link."""

    dashboard_url: str = Field(..., description="URL to Stripe Express dashboard")
    expires_in_minutes: int = Field(default=5, description="Minutes until link expires")


class IdentitySessionResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for initiating a Stripe Identity verification session."""

    verification_session_id: str = Field(..., description="Stripe verification session identifier")
    client_secret: str = Field(..., description="Client secret for the verification session")


class IdentityRefreshResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for refreshing Stripe Identity verification status."""

    status: str = Field(..., description="Latest verification status from Stripe")
    verified: bool = Field(..., description="Whether the user is now verified")


class PayoutScheduleResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for payout schedule updates."""

    ok: bool = Field(..., description="Whether the schedule update succeeded")
    account_id: Optional[str] = Field(None, description="Stripe connected account identifier")
    settings: Optional[Dict[str, Any]] = Field(
        None, description="Stripe payout schedule settings that were applied"
    )


class InstantPayoutResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for instant payout attempts."""

    ok: bool = Field(..., description="Whether the instant payout request succeeded")
    payout_id: Optional[str] = Field(
        None, description="Stripe payout identifier if one was created"
    )
    status: Optional[str] = Field(
        None, description="Stripe status of the payout (e.g., pending, paid)"
    )


class CheckoutResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for checkout/payment creation."""

    success: bool = Field(..., description="Whether payment was successful")
    payment_intent_id: str = Field(..., description="Stripe payment intent ID")
    status: str = Field(..., description="Payment status")
    amount: int = Field(..., description="Payment amount in cents")
    application_fee: int = Field(..., description="Platform fee in cents")
    client_secret: Optional[str] = Field(
        None, description="Client secret for frontend confirmation"
    )
    requires_action: bool = Field(
        default=False, description="Whether payment requires additional action"
    )


class CustomerResponse(StrictModel):
    """Response for customer creation/retrieval."""

    model_config = ConfigDict(from_attributes=True)

    customer_id: str = Field(..., description="Stripe customer ID")
    user_id: str = Field(..., description="Internal user ID")
    created_at: datetime = Field(..., description="When customer was created")


class PaymentIntentResponse(StrictModel):
    """Response for payment intent operations."""

    payment_intent_id: str = Field(..., description="Stripe payment intent ID")
    booking_id: str = Field(..., description="Associated booking ID")
    amount: int = Field(..., description="Payment amount in cents")
    application_fee: int = Field(..., description="Platform fee in cents")
    status: str = Field(..., description="Payment intent status")
    created_at: datetime = Field(..., description="When payment intent was created")

    model_config = ConfigDict(from_attributes=True)


# ========== Analytics Response Models ==========


class PlatformRevenueResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for platform revenue statistics."""

    total_amount: int = Field(..., description="Total payment amount in cents")
    total_fees: int = Field(..., description="Total platform fees in cents")
    payment_count: int = Field(..., description="Number of successful payments")
    average_transaction: float = Field(..., description="Average transaction amount")


class InstructorEarningsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for instructor earnings statistics."""

    total_earned: int = Field(..., description="Total instructor earnings in cents (after fees)")
    total_fees: int = Field(..., description="Total platform fees deducted")
    booking_count: int = Field(..., description="Number of completed bookings")
    average_earning: float = Field(..., description="Average earning per booking")


# ========== Webhook Response Models ==========


class WebhookResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for webhook processing."""

    status: str = Field(..., description="Processing status (success, ignored, error)")
    event_type: str = Field(..., description="Stripe event type")
    message: Optional[str] = Field(None, description="Additional information")


# ========== Transaction History Response Models ==========


class TransactionHistoryItem(BaseModel):
    """Individual transaction in payment history."""

    id: str = Field(..., description="Payment intent ID")
    service_name: str = Field(..., description="Service name")
    instructor_name: str = Field(..., description="Instructor name (first name + last initial)")
    booking_date: str = Field(..., description="Date of the booking")
    start_time: str = Field(..., description="Start time of the booking")
    end_time: str = Field(..., description="End time of the booking")
    duration_minutes: int = Field(..., description="Duration in minutes")
    hourly_rate: float = Field(..., description="Hourly rate charged")
    total_price: float = Field(..., description="Total price before fees")
    platform_fee: float = Field(..., description="Platform fee charged")
    credit_applied: float = Field(..., description="Credits applied to this transaction")
    final_amount: float = Field(..., description="Final amount charged")
    status: str = Field(..., description="Payment status")
    created_at: str = Field(..., description="When the payment was created")


class CreditBalanceResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for credit balance inquiry."""

    available: float = Field(..., description="Available credit balance")
    expires_at: Optional[str] = Field(None, description="Credit expiration date")
    pending: float = Field(..., description="Pending credits")


# ========== Error Response Models ==========


class PaymentErrorResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Error response for payment operations."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    payment_intent_id: Optional[str] = Field(
        None, description="Associated payment intent ID if applicable"
    )


# ========== Generic Response Models ==========


class DeleteResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for delete operations."""

    success: bool = Field(..., description="Whether deletion was successful")


class EarningsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for earnings data."""

    total_earned: Optional[int] = Field(None, description="Total earnings in cents")
    total_fees: Optional[int] = Field(None, description="Total fees in cents")
    booking_count: Optional[int] = Field(None, description="Number of bookings")
    average_earning: Optional[float] = Field(None, description="Average earning per booking")
    period_start: Optional[datetime] = Field(None, description="Start of period")
    period_end: Optional[datetime] = Field(None, description="End of period")
