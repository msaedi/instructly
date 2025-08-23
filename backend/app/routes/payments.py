"""
Payment API Routes for InstaInstru Platform

Handles Stripe Connect integration including:
- Instructor onboarding and account management
- Student payment method management
- Payment processing for bookings
- Webhook event handling

Key Features:
- Role-based access control (instructor vs student routes)
- Comprehensive error handling
- Audit logging for all payment operations
- Stripe API integration through StripeService
"""

import logging
from typing import Any, Dict, List

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..api.dependencies.auth import get_current_active_user
from ..core.config import settings
from ..core.enums import RoleName
from ..core.exceptions import ServiceException, ValidationException
from ..database import get_db
from ..models.user import User
from ..monitoring.prometheus_metrics import prometheus_metrics
from ..schemas.payment_schemas import (
    CheckoutResponse,
    CreateCheckoutRequest,
    CreditBalanceResponse,
    CustomerResponse,
    DashboardLinkResponse,
    DeleteResponse,
    EarningsResponse,
    OnboardingResponse,
    OnboardingStatusResponse,
    PaymentErrorResponse,
    PaymentIntentResponse,
    PaymentMethodResponse,
    SavePaymentMethodRequest,
    TransactionHistoryItem,
    WebhookResponse,
)
from ..services.base import BaseService
from ..services.stripe_service import StripeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])


def get_stripe_service(db: Session = Depends(get_db)) -> StripeService:
    """Get StripeService instance with dependency injection."""
    return StripeService(db)


def validate_instructor_role(user: User) -> None:
    """Validate that user has instructor role."""
    if not user.is_instructor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint requires instructor role")


def validate_student_role(user: User) -> None:
    """Validate that user has student role."""
    if not user.is_student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint requires student role")


# ========== Instructor Routes ==========


@router.post("/connect/onboard", response_model=OnboardingResponse)
async def start_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> OnboardingResponse:
    """
    Start Stripe Connect onboarding for an instructor.

    Creates a Stripe Express account and generates an onboarding link.
    If the instructor already has an account, returns existing details.

    Returns:
        OnboardingResponse with account ID and onboarding URL

    Raises:
        HTTPException: If onboarding setup fails
    """
    try:
        # Validate instructor role
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            logger.error(f"No instructor profile found for user {current_user.id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

        # Check if account already exists
        existing_account = stripe_service.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )

        if existing_account:
            # Check onboarding status
            account_status = await run_in_threadpool(stripe_service.check_account_status, instructor_profile.id)

            if account_status["onboarding_completed"]:
                return OnboardingResponse(
                    account_id=existing_account.stripe_account_id,
                    onboarding_url="",  # No URL needed for completed onboarding
                    already_onboarded=True,
                )
            else:
                # Create new onboarding link for existing account
                onboarding_url = stripe_service.create_account_link(
                    instructor_profile.id,
                    refresh_url=f"{settings.frontend_url}/dashboard/instructor?stripe_onboarding_return=true",
                    return_url=f"{settings.frontend_url}/dashboard/instructor?stripe_onboarding_return=true",
                )

                return OnboardingResponse(
                    account_id=existing_account.stripe_account_id,
                    onboarding_url=onboarding_url,
                    already_onboarded=False,
                )

        # Create new connected account
        connected_account = stripe_service.create_connected_account(instructor_profile.id, current_user.email)

        # Create onboarding link
        onboarding_url = stripe_service.create_account_link(
            instructor_profile.id,
            refresh_url=f"{settings.frontend_url}/dashboard/instructor?stripe_onboarding_return=true",
            return_url=f"{settings.frontend_url}/dashboard/instructor?stripe_onboarding_return=true",
        )

        logger.info(f"Started onboarding for instructor {instructor_profile.id}")

        return OnboardingResponse(
            account_id=connected_account.stripe_account_id, onboarding_url=onboarding_url, already_onboarded=False
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like from validate_instructor_role)
        raise
    except ServiceException as e:
        logger.error(f"Service error during onboarding: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during onboarding: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to start onboarding process"
        )


@router.get("/connect/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> OnboardingStatusResponse:
    """
    Get the onboarding status for an instructor's Stripe account.

    Returns:
        OnboardingStatusResponse with account status details

    Raises:
        HTTPException: If status check fails
    """
    try:
        # Validate instructor role
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

        # Get account status
        status_data = await run_in_threadpool(stripe_service.check_account_status, instructor_profile.id)

        return OnboardingStatusResponse(
            has_account=status_data["has_account"],
            onboarding_completed=status_data["onboarding_completed"],
            charges_enabled=status_data.get("can_accept_payments", False),
            payouts_enabled=status_data.get("can_accept_payments", False),  # Simplified for now
            details_submitted=status_data.get("details_submitted", False),
            requirements=[],  # Could be populated from Stripe account requirements
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ServiceException as e:
        logger.error(f"Service error checking onboarding status: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error checking onboarding status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to check onboarding status"
        )


class PayoutScheduleResponse(BaseModel):
    ok: bool
    account_id: str | None = None
    settings: Dict[str, Any] | None = None


@router.post("/connect/payout-schedule", response_model=PayoutScheduleResponse)
async def set_payout_schedule(
    interval: str = "weekly",
    weekly_anchor: str = "tuesday",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
):
    """
    Set payout schedule for the current instructor's connected account.

    Default: weekly on Tuesday. Valid anchors: monday..sunday.
    """
    try:
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

        result = await run_in_threadpool(
            stripe_service.set_payout_schedule_for_account,
            instructor_profile.id,
            interval,
            weekly_anchor,
        )
        return PayoutScheduleResponse(ok=True, account_id=result.get("account_id"), settings=result.get("settings"))
    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Error setting payout schedule: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error setting payout schedule: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to set payout schedule")


@router.get("/connect/dashboard", response_model=DashboardLinkResponse)
async def get_dashboard_link(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> DashboardLinkResponse:
    """
    Get a link to the Stripe Express dashboard for an instructor.

    Returns:
        DashboardLinkResponse with dashboard URL

    Raises:
        HTTPException: If dashboard link creation fails
    """
    try:
        # Validate instructor role
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

        # Get connected account
        connected_account = stripe_service.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )

        if not connected_account or not connected_account.onboarding_completed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Onboarding must be completed before accessing dashboard",
            )

        # Create dashboard link
        login_link = await run_in_threadpool(stripe.Account.create_login_link, connected_account.stripe_account_id)

        logger.info(f"Created dashboard link for instructor {instructor_profile.id}")

        return DashboardLinkResponse(
            dashboard_url=login_link.url, expires_in_minutes=5  # Stripe login links expire after 5 minutes
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except stripe.StripeError as e:
        logger.error(f"Stripe error creating dashboard link: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create dashboard link")
    except ServiceException as e:
        logger.error(f"Service error creating dashboard link: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating dashboard link: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create dashboard link")


class InstantPayoutResponse(BaseModel):
    ok: bool
    payout_id: str | None = None
    status: str | None = None


@router.post("/connect/instant-payout", response_model=InstantPayoutResponse)
async def request_instant_payout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
):
    """
    Trigger an instant payout for an instructor's connected account.

    Uses Stripe's instant payout capability (account eligibility required). This does NOT aggregate platform funds; it
    triggers Stripe to pay out the instructor's available balance instantly. We record a metric for adoption.
    """
    try:
        validate_instructor_role(current_user)

        # Resolve connected account
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

        connected = stripe_service.payment_repository.get_connected_account_by_instructor_id(instructor_profile.id)
        if not connected or not connected.onboarding_completed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Onboarding incomplete")

        # Create a payout with method='instant' on the connected account
        # Note: Requires Stripe account eligibility and sufficient balance
        payout = await run_in_threadpool(
            stripe.Payout.create,
            amount=0,  # 0 means Stripe will pay out the maximum available (supported in test mode)
            currency=settings.stripe_currency or "usd",
            method="instant",
            stripe_account=connected.stripe_account_id,
        )

        prometheus_metrics.inc_instant_payout_request("success")
        return InstantPayoutResponse(ok=True, payout_id=payout.id, status=payout.status)
    except HTTPException:
        prometheus_metrics.inc_instant_payout_request("error")
        raise
    except stripe.StripeError as e:
        logger.error(f"Stripe error requesting instant payout: {str(e)}")
        prometheus_metrics.inc_instant_payout_request("error")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instant payout failed")
    except Exception as e:
        logger.error(f"Unexpected error requesting instant payout: {str(e)}")
        prometheus_metrics.inc_instant_payout_request("error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Instant payout failed")


# ========== Student Routes ==========


@router.post("/methods", response_model=PaymentMethodResponse)
async def save_payment_method(
    request: SavePaymentMethodRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PaymentMethodResponse:
    """
    Save a payment method for a student.

    Args:
        request: Payment method details

    Returns:
        PaymentMethodResponse with saved payment method details

    Raises:
        HTTPException: If payment method saving fails
    """
    try:
        # Validate student role
        validate_student_role(current_user)

        # Ensure user has a Stripe customer
        customer = stripe_service.get_or_create_customer(current_user.id)

        # Save payment method
        payment_method = stripe_service.save_payment_method(
            user_id=current_user.id, payment_method_id=request.payment_method_id, set_as_default=request.set_as_default
        )

        logger.info(f"Saved payment method for user {current_user.id}")

        return PaymentMethodResponse(
            id=payment_method.stripe_payment_method_id,
            last4=payment_method.last4 or "",
            brand=payment_method.brand or "",
            is_default=payment_method.is_default,
            created_at=payment_method.created_at,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ServiceException as e:
        logger.error(f"Service error saving payment method: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error saving payment method: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save payment method")


@router.get("/methods", response_model=List[PaymentMethodResponse])
async def list_payment_methods(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> List[PaymentMethodResponse]:
    """
    List all payment methods for a student.

    Returns:
        List of PaymentMethodResponse objects

    Raises:
        HTTPException: If payment method listing fails
    """
    try:
        # Validate student role
        validate_student_role(current_user)

        # Get payment methods
        payment_methods = stripe_service.get_user_payment_methods(current_user.id)

        return [
            PaymentMethodResponse(
                id=pm.stripe_payment_method_id,
                last4=pm.last4 or "",
                brand=pm.brand or "",
                is_default=pm.is_default,
                created_at=pm.created_at,
            )
            for pm in payment_methods
        ]

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ServiceException as e:
        logger.error(f"Service error listing payment methods: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error listing payment methods: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list payment methods")


@router.delete("/methods/{method_id}", response_model=DeleteResponse)
async def delete_payment_method(
    method_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> DeleteResponse:
    """
    Delete a payment method for a student.

    Args:
        method_id: Payment method ID to delete

    Returns:
        Success confirmation

    Raises:
        HTTPException: If payment method deletion fails
    """
    try:
        # Validate student role
        validate_student_role(current_user)

        # Delete payment method
        success = stripe_service.delete_payment_method(method_id, current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found or not owned by user"
            )

        logger.info(f"Deleted payment method {method_id} for user {current_user.id}")

        return DeleteResponse(success=True)

    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error deleting payment method: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting payment method: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete payment method")


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CreateCheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> CheckoutResponse:
    """
    Create a checkout/payment for a booking.

    Args:
        request: Checkout details including booking and payment method

    Returns:
        CheckoutResponse with payment details

    Raises:
        HTTPException: If checkout creation fails
    """
    try:
        # Validate student role
        validate_student_role(current_user)

        # Get booking and verify ownership
        booking = stripe_service.booking_repository.get_by_id(request.booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.student_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only pay for your own bookings")

        # Check booking status - should be confirmed and not yet paid
        if booking.status not in ["CONFIRMED", "PENDING"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot process payment for booking with status: {booking.status}",
            )

        # Check if booking already has a successful payment
        existing_payment = stripe_service.payment_repository.get_payment_by_booking_id(booking.id)
        if existing_payment and existing_payment.status == "succeeded":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking has already been paid")

        # Save payment method if requested
        if request.save_payment_method:
            stripe_service.save_payment_method(
                user_id=current_user.id, payment_method_id=request.payment_method_id, set_as_default=False
            )

        # Process payment
        payment_result = await run_in_threadpool(
            stripe_service.process_booking_payment,
            request.booking_id,
            request.payment_method_id,
        )

        # Update booking status if payment succeeded
        if payment_result["success"] and payment_result["status"] == "succeeded":
            booking.status = "CONFIRMED"
            stripe_service.db.flush()

        logger.info(f"Processed payment for booking {request.booking_id}")

        # If the Stripe service indicates 3DS is required, surface client_secret
        client_secret = (
            payment_result.get("client_secret")
            if payment_result.get("status")
            in [
                "requires_action",
                "requires_confirmation",
            ]
            else None
        )

        return CheckoutResponse(
            success=payment_result["success"],
            payment_intent_id=payment_result["payment_intent_id"],
            status=payment_result["status"],
            amount=payment_result["amount"],
            application_fee=payment_result["application_fee"],
            client_secret=client_secret,
            requires_action=payment_result["status"] in ["requires_action", "requires_confirmation"],
        )

    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error creating checkout: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating checkout: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process payment")


# ========== Analytics Routes (Admin/Instructor) ==========


@router.get("/earnings", response_model=EarningsResponse)
async def get_instructor_earnings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> EarningsResponse:
    """
    Get earnings statistics for an instructor.

    Returns:
        Instructor earnings data

    Raises:
        HTTPException: If earnings calculation fails
    """
    try:
        # Validate instructor role
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

        # Get earnings data (using instructor user ID for now)
        earnings = stripe_service.get_instructor_earnings(current_user.id)

        return EarningsResponse(
            total_earned=earnings.get("total_earned"),
            total_fees=earnings.get("total_fees"),
            booking_count=earnings.get("booking_count"),
            average_earning=earnings.get("average_earning"),
            period_start=earnings.get("period_start"),
            period_end=earnings.get("period_end"),
        )

    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error getting earnings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting earnings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get earnings data")


# ========== Transaction History Route ==========


@router.get("/transactions", response_model=List[TransactionHistoryItem])
async def get_transaction_history(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
) -> List[TransactionHistoryItem]:
    """
    Get user's transaction history

    Returns list of completed payments with booking details
    """
    try:
        stripe_service = StripeService(db)

        # Get payment intents for this user
        transactions = stripe_service.payment_repository.get_user_payment_history(
            user_id=current_user.id, limit=limit, offset=offset
        )

        # Format response with booking details
        result = []
        for payment in transactions:
            try:
                booking = payment.booking
                if not booking:
                    logger.warning(f"Payment {payment.id} has no associated booking")
                    continue

                # Get instructor service and related data
                instructor_service = booking.instructor_service
                if not instructor_service:
                    logger.warning(f"Booking {booking.id} has no instructor service")
                    continue

                # Get the catalog entry (the actual service details)
                catalog_entry = instructor_service.catalog_entry
                instructor_profile = instructor_service.instructor_profile
                instructor = instructor_profile.user if instructor_profile else None

                # Determine credits applied from payment events
                credit_applied_cents = 0
                try:
                    events = stripe_service.payment_repository.get_payment_events_for_booking(booking.id)
                    # Prefer explicit credits_applied event
                    for ev in events:
                        if ev.event_type == "credits_applied":
                            data = ev.event_data or {}
                            credit_applied_cents = int(data.get("applied_cents", 0) or 0)
                    # Fallback: full credit authorization event
                    if credit_applied_cents == 0:
                        for ev in events:
                            if ev.event_type == "auth_succeeded_credits_only":
                                data = ev.event_data or {}
                                credit_applied_cents = int(
                                    data.get("credits_applied_cents", data.get("original_amount_cents", 0)) or 0
                                )
                except Exception:
                    credit_applied_cents = 0

                # Build transaction history item
                # Final charged amount: payment.amount (cents) is what the student was charged
                # total_price = lesson price (from booking)
                # platform_fee = application_fee (from payment record)
                # credit_applied = credits applied prior to charge
                result.append(
                    TransactionHistoryItem(
                        id=payment.id,
                        service_name=catalog_entry.name if catalog_entry else "Service",
                        instructor_name=f"{instructor.first_name} {instructor.last_name[0]}."
                        if instructor and instructor.last_name
                        else "Instructor",
                        booking_date=booking.booking_date.isoformat(),
                        start_time=booking.start_time.isoformat(),
                        end_time=booking.end_time.isoformat(),
                        duration_minutes=booking.duration_minutes,
                        hourly_rate=float(booking.hourly_rate),
                        total_price=round(float(booking.total_price), 2),
                        platform_fee=round((payment.application_fee or 0) / 100, 2),
                        credit_applied=credit_applied_cents / 100,
                        final_amount=round((payment.amount or 0) / 100, 2),
                        status=payment.status,
                        created_at=payment.created_at.isoformat(),
                    )
                )
            except Exception as e:
                logger.error(f"Error formatting transaction {payment.id}: {str(e)}")
                continue

        return result

    except Exception as e:
        logger.error(f"Error getting transaction history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get transaction history"
        )


# ========== Credit Balance Route ==========


@router.get("/credits", response_model=CreditBalanceResponse)
async def get_credit_balance(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
) -> CreditBalanceResponse:
    """
    Get user's credit balance

    Returns available credits and expiration
    """
    try:
        stripe_service = StripeService(db)
        payment_repo = stripe_service.payment_repository

        # Total available credits in cents
        total_cents = payment_repo.get_total_available_credits(current_user.id)

        # Earliest expiration among available credits (if any)
        earliest_exp: str | None = None
        try:
            credits = payment_repo.get_available_credits(current_user.id)
            expiries = [c.expires_at for c in credits if getattr(c, "expires_at", None) is not None]
            if expiries:
                earliest_exp = min(expiries).isoformat()
        except Exception:
            earliest_exp = None

        return CreditBalanceResponse(
            available=float(total_cents) / 100.0,
            expires_at=earliest_exp,
            pending=0.0,
        )

    except Exception as e:
        logger.error(f"Error getting credit balance: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get credit balance")


# ========== Webhook Route (No Authentication) ==========


@router.post("/webhooks/stripe", response_model=WebhookResponse)
async def handle_stripe_webhook(request: Request, db: Session = Depends(get_db)) -> WebhookResponse:
    """
    Handle Stripe webhook events from both platform and connected accounts.

    Works with both local development (single secret) and deployed environments (multiple secrets).
    Tries each configured webhook secret until one successfully verifies the signature.

    Returns:
        Success confirmation (always returns 200 to prevent Stripe retries)

    Note:
        This endpoint has no authentication as it uses webhook signature verification
    """
    try:
        # Get raw body and signature
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")

        if not sig_header:
            logger.warning("Webhook received without signature")
            raise HTTPException(status_code=400, detail="No signature")

        # Get list of secrets to try
        webhook_secrets = settings.webhook_secrets
        if not webhook_secrets:
            logger.error("No webhook secrets configured")
            raise HTTPException(status_code=500, detail="Webhook configuration error")

        # Try each configured secret until one works
        event = None
        last_error = None
        secret_type = None

        for i, secret in enumerate(webhook_secrets):
            try:
                event = stripe.Webhook.construct_event(payload, sig_header, secret)
                # Determine which secret worked for logging
                if i == 0 and settings.stripe_webhook_secret:
                    secret_type = "local/CLI"
                elif (
                    settings.stripe_webhook_secret_platform
                    and secret == settings.stripe_webhook_secret_platform.get_secret_value()
                ):
                    secret_type = "platform"
                elif (
                    settings.stripe_webhook_secret_connect
                    and secret == settings.stripe_webhook_secret_connect.get_secret_value()
                ):
                    secret_type = "connect"
                else:
                    secret_type = f"secret #{i+1}"

                logger.info(f"Webhook verified with {secret_type} secret for event: {event['type']}")
                break  # Success! Stop trying other secrets
            except stripe.error.SignatureVerificationError as e:
                last_error = e
                continue  # Try next secret

        if not event:
            logger.error(f"Webhook signature verification failed with all {len(webhook_secrets)} configured secrets")
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Log account context for debugging
        if "account" in event:
            logger.info(f"Event from connected account: {event['account']}")
        else:
            logger.info("Event from platform account")

        # Process the verified event
        stripe_service = StripeService(db)
        result = stripe_service.handle_webhook_event(event)  # Pass parsed event directly

        logger.info(f"Webhook processed successfully: {event['type']}")
        return WebhookResponse(
            status="success",
            event_type=event.get("type", "unknown"),
            message=f"Event processed with {secret_type} secret",
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like missing signature)
        raise
    except Exception as e:
        logger.error(f"Unexpected webhook error: {str(e)}")
        # Return 200 to prevent Stripe retries for non-recoverable errors
        return WebhookResponse(
            status="error", event_type="unknown", message="Error logged - returning 200 to prevent retries"
        )
