"""
Payment-related Pydantic schemas for InstaInstru platform.

Defines request and response models for Stripe payment integration,
including customer management, connected accounts, payment methods,
and payment processing.
"""

from datetime import date, datetime, time
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
    payment_method_id: Optional[str] = Field(
        default=None,
        description="Stripe payment method ID to use when a balance remains",
    )
    save_payment_method: bool = Field(
        default=False, description="Whether to save payment method for future use"
    )
    requested_credit_cents: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional wallet credit amount (in cents) the student wants to apply",
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
    booking_id: str = Field(..., description="Booking ID")
    service_name: str = Field(..., description="Service name")
    instructor_name: str = Field(..., description="Instructor name (first name + last initial)")
    booking_date: str = Field(..., description="Date of the booking")
    start_time: str = Field(..., description="Start time of the booking")
    end_time: str = Field(..., description="End time of the booking")
    duration_minutes: int = Field(..., description="Duration in minutes")
    hourly_rate: float = Field(..., description="Hourly rate charged")
    lesson_amount: float = Field(..., description="Lesson price before fees")
    service_fee: float = Field(..., description="Student service fee amount")
    credit_applied: float = Field(..., description="Credits applied to this transaction")
    tip_amount: float = Field(..., description="Tip amount recorded")
    tip_paid: float = Field(..., description="Tip amount successfully charged")
    tip_status: Optional[str] = Field(None, description="Status of the tip payment")
    total_paid: float = Field(..., description="Final amount charged including tips")
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


class InstructorInvoiceSummary(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Summary of an instructor invoice/payment."""

    booking_id: str = Field(..., description="Associated booking ID")
    lesson_date: date = Field(..., description="Date of the lesson")
    start_time: Optional[time] = Field(None, description="Lesson start time")
    service_name: Optional[str] = Field(None, description="Name of the service taught")
    student_name: Optional[str] = Field(None, description="Student name (privacy aware)")
    duration_minutes: Optional[int] = Field(None, description="Duration of the lesson in minutes")
    total_paid_cents: int = Field(..., description="Total amount paid by the student in cents")
    tip_cents: int = Field(..., description="Tip amount included with the payment in cents")
    instructor_share_cents: int = Field(
        ..., description="Net payout to the instructor after fees (in cents)"
    )
    status: str = Field(..., description="Invoice/payment status")
    created_at: datetime = Field(..., description="When the payment was completed")

    # Instructor-centric clarity fields
    lesson_price_cents: int = Field(
        ..., description="Base lesson price (instructor's rate × duration)"
    )
    platform_fee_cents: int = Field(
        ..., description="Platform fee deducted from instructor earnings"
    )
    platform_fee_rate: float = Field(
        ..., description="Platform fee rate applied (e.g., 0.1 for 10%)"
    )
    student_fee_cents: int = Field(
        ..., description="Booking protection fee added to student (not deducted from instructor)"
    )


class EarningsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for earnings data."""

    total_earned: Optional[int] = Field(None, description="Total earnings in cents")
    total_fees: Optional[int] = Field(None, description="Total fees in cents")
    booking_count: Optional[int] = Field(None, description="Number of bookings")
    average_earning: Optional[float] = Field(None, description="Average earning per booking")
    hours_invoiced: Optional[float] = Field(
        None, description="Total hours invoiced for completed lessons"
    )
    service_count: Optional[int] = Field(
        None, description="Number of completed services contributing to earnings"
    )
    invoices: List[InstructorInvoiceSummary] = Field(
        default_factory=list, description="Recent invoices contributing to earnings"
    )
    period_start: Optional[datetime] = Field(None, description="Start of period")
    period_end: Optional[datetime] = Field(None, description="End of period")

    # Instructor-centric aggregate fields
    total_lesson_value: Optional[int] = Field(
        None, description="Total value of all lessons (before any fees)"
    )
    total_platform_fees: Optional[int] = Field(
        None, description="Total platform fees deducted from instructor earnings"
    )
    total_tips: Optional[int] = Field(None, description="Total tips received")


# ========== Payout Response Models ==========


class PayoutSummary(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Individual payout record from Stripe."""

    id: str = Field(..., description="Payout ID (Stripe)")
    amount_cents: int = Field(..., description="Amount in cents")
    status: str = Field(
        ..., description="Payout status (pending, in_transit, paid, failed, canceled)"
    )
    arrival_date: Optional[datetime] = Field(None, description="Expected arrival date")
    failure_code: Optional[str] = Field(None, description="Failure code if payout failed")
    failure_message: Optional[str] = Field(None, description="Failure message if payout failed")
    created_at: datetime = Field(..., description="When the payout was created")


class PayoutHistoryResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for instructor payout history."""

    payouts: List[PayoutSummary] = Field(default_factory=list, description="List of payouts")
    total_paid_cents: int = Field(default=0, description="Total amount successfully paid out")
    total_pending_cents: int = Field(default=0, description="Total amount pending payout")
    payout_count: int = Field(default=0, description="Number of payouts")
