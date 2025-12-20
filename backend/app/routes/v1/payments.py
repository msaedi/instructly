# backend/app/routes/v1/payments.py
"""
Payment API Routes - API v1

Versioned payment endpoints under /api/v1/payments.
Handles Stripe Connect integration including:
- Instructor onboarding and account management
- Student payment method management
- Payment processing for bookings
- Webhook event handling

Endpoints:
    POST /connect/onboard                → Start instructor Stripe onboarding
    GET /connect/status                  → Get onboarding status
    POST /connect/payout-schedule        → Set payout schedule
    GET /connect/dashboard               → Get Stripe dashboard link
    POST /connect/instant-payout         → Request instant payout
    POST /identity/session               → Create Stripe Identity session
    POST /identity/refresh               → Refresh identity status
    POST /methods                        → Save payment method
    GET /methods                         → List payment methods
    DELETE /methods/{method_id}          → Delete payment method
    POST /checkout                       → Create checkout
    GET /earnings                        → Get instructor earnings
    GET /transactions                    → Get transaction history
    GET /credits                         → Get credit balance
    POST /webhooks/stripe                → Handle Stripe webhooks
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
import stripe

from ...api.dependencies.auth import get_current_active_user
from ...core.config import settings
from ...core.exceptions import ServiceException
from ...database import get_db
from ...idempotency.cache import get_cached, set_cached
from ...models.user import User
from ...monitoring.prometheus_metrics import prometheus_metrics
from ...ratelimit.dependency import rate_limit
from ...ratelimit.locks import acquire_lock, release_lock
from ...schemas.payment_schemas import (
    CheckoutResponse,
    CreateCheckoutRequest,
    CreditBalanceResponse,
    DashboardLinkResponse,
    DeleteResponse,
    EarningsResponse,
    IdentityRefreshResponse,
    IdentitySessionResponse,
    InstantPayoutResponse,
    OnboardingResponse,
    OnboardingStatusResponse,
    PaymentMethodResponse,
    PayoutHistoryResponse,
    PayoutScheduleResponse,
    SavePaymentMethodRequest,
    TransactionHistoryItem,
    WebhookResponse,
)
from ...services.booking_service import BookingService
from ...services.cache_service import CacheService, get_cache_service
from ...services.config_service import ConfigService
from ...services.dependencies import get_booking_service
from ...services.pricing_service import PricingService
from ...services.stripe_service import StripeService
from ...utils.strict import model_filter

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["payments-v1"])


def get_stripe_service(
    db: Session = Depends(get_db),
    cache_service: Optional[CacheService] = Depends(get_cache_service),
) -> StripeService:
    """Get StripeService instance with dependency injection."""
    config_service = ConfigService(db)
    pricing_service = PricingService(db)
    return StripeService(
        db,
        config_service=config_service,
        pricing_service=pricing_service,
        cache_service=cache_service,
    )


def validate_instructor_role(user: User) -> None:
    """Validate that user has instructor role."""
    if not user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "This endpoint requires instructor role",
                "code": "PAYMENTS_INSTRUCTOR_ONLY",
            },
        )


def validate_student_role(user: User) -> None:
    """Validate that user has student role."""
    if not user.is_student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "This endpoint requires student role",
                "code": "PAYMENTS_STUDENT_ONLY",
            },
        )


# ========== Instructor Routes ==========


@router.post(
    "/connect/onboard",
    response_model=OnboardingResponse,
    dependencies=[Depends(rate_limit("financial"))],
)
async def start_onboarding(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    return_to: str | None = None,
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
    validate_instructor_role(current_user)
    return await asyncio.to_thread(
        stripe_service.start_instructor_onboarding,
        user=current_user,
        request_host=request.headers.get("host", ""),
        request_scheme=request.url.scheme,
        return_to=return_to,
    )


@router.get("/connect/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
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
    validate_instructor_role(current_user)
    return await asyncio.to_thread(
        stripe_service.get_instructor_onboarding_status,
        user=current_user,
    )


# ========== Stripe Identity ==========


@router.post(
    "/identity/session",
    response_model=IdentitySessionResponse,
    dependencies=[Depends(rate_limit("financial"))],
)
async def create_identity_session(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> IdentitySessionResponse:
    """Create a Stripe Identity verification session for the current user."""
    try:
        validate_instructor_role(current_user)

        # Use frontend URL with a return flag back to onboarding
        from app.core.config import settings

        # Redirect back to onboarding status page in the new Phoenix structure
        configured_frontend = (settings.frontend_url or "").strip()
        request_host = (request.headers.get("host") or "").strip()
        origin: Optional[str] = None

        if configured_frontend:
            parsed = urlparse(configured_frontend)
            configured_host = (parsed.netloc or "").lower()
            if request_host and configured_host and configured_host == request_host.lower():
                scheme = parsed.scheme or request.url.scheme
                origin = f"{scheme}://{configured_host}".rstrip("/")

        if not origin:
            if request_host:
                origin = f"{request.url.scheme}://{request_host}".rstrip("/")
            elif configured_frontend:
                origin = configured_frontend.rstrip("/")
            else:
                origin = str(request.base_url).rstrip("/")

        path = settings.identity_return_path.lstrip("/")
        return_url = urljoin(f"{origin}/", path)
        result = cast(
            Dict[str, Any],
            await run_in_threadpool(
                stripe_service.create_identity_verification_session,
                user_id=current_user.id,
                return_url=return_url,
            ),
        )
        cleaned = model_filter(IdentitySessionResponse, result)
        return IdentitySessionResponse(**cleaned)
    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error creating identity session: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating identity session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create identity session",
        )


@router.post(
    "/identity/refresh",
    response_model=IdentityRefreshResponse,
    dependencies=[
        Depends(rate_limit("read"))
    ],  # Use "read" bucket (60/min, burst=10) - status check, not financial
)
async def refresh_identity_status(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> IdentityRefreshResponse:
    """Fetch latest Stripe Identity status and persist verification on success.

    This avoids blocking general status calls and lets the UI trigger a one-off refresh
    right after the modal/hosted flow returns.
    """
    validate_instructor_role(current_user)
    return await asyncio.to_thread(
        stripe_service.refresh_instructor_identity,
        user=current_user,
    )


@router.post(
    "/connect/payout-schedule",
    response_model=PayoutScheduleResponse,
    dependencies=[Depends(rate_limit("financial"))],
)
async def set_payout_schedule(
    interval: str = "weekly",
    weekly_anchor: str = "tuesday",
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PayoutScheduleResponse:
    """
    Set payout schedule for the current instructor's connected account.

    Default: weekly on Tuesday. Valid anchors: monday..sunday.
    """
    validate_instructor_role(current_user)
    monthly_anchor = 1 if interval == "monthly" else None
    return await asyncio.to_thread(
        stripe_service.set_instructor_payout_schedule,
        user=current_user,
        monthly_anchor=monthly_anchor,
        interval=interval,
    )


@router.get("/connect/dashboard", response_model=DashboardLinkResponse)
async def get_dashboard_link(
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
    validate_instructor_role(current_user)
    return await asyncio.to_thread(stripe_service.get_instructor_dashboard_link, user=current_user)


@router.post("/connect/instant-payout", response_model=InstantPayoutResponse)
async def request_instant_payout(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> InstantPayoutResponse:
    """
    Trigger an instant payout for an instructor's connected account.

    Uses Stripe's instant payout capability (account eligibility required). This does NOT aggregate platform funds; it
    triggers Stripe to pay out the instructor's available balance instantly. We record a metric for adoption.
    """
    validate_instructor_role(current_user)
    prometheus_metrics.inc_instant_payout_request("attempt")
    try:
        return await asyncio.to_thread(
            stripe_service.request_instructor_instant_payout,
            user=current_user,
            amount_cents=0,
        )
    except HTTPException:
        prometheus_metrics.inc_instant_payout_request("error")
        raise
    except Exception:
        prometheus_metrics.inc_instant_payout_request("error")
        raise


# ========== Student Routes ==========


@router.post("/methods", response_model=PaymentMethodResponse)
async def save_payment_method(
    payload: SavePaymentMethodRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PaymentMethodResponse:
    """
    Save a payment method for a student.

    Args:
        payload: Payment method details

    Returns:
        PaymentMethodResponse with saved payment method details

    Raises:
        HTTPException: If payment method saving fails
    """
    try:
        # Validate student role
        validate_student_role(current_user)

        # Ensure user has a Stripe customer
        _customer = await asyncio.to_thread(stripe_service.get_or_create_customer, current_user.id)

        # Save payment method
        payment_method = await asyncio.to_thread(
            stripe_service.save_payment_method,
            user_id=current_user.id,
            payment_method_id=payload.payment_method_id,
            set_as_default=payload.set_as_default,
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save payment method",
        )


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
        payment_methods = await asyncio.to_thread(
            stripe_service.get_user_payment_methods, current_user.id
        )

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list payment methods",
        )


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
        success = await asyncio.to_thread(
            stripe_service.delete_payment_method, method_id, current_user.id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment method not found or not owned by user",
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete payment method",
        )


@router.post(
    "/checkout", response_model=CheckoutResponse, dependencies=[Depends(rate_limit("financial"))]
)
async def create_checkout(
    payload: CreateCheckoutRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    booking_service: BookingService = Depends(get_booking_service),
) -> CheckoutResponse:
    """
    Create a checkout/payment for a booking.

    Args:
        payload: Checkout details including booking and payment method

    Returns:
        CheckoutResponse with payment details

    Raises:
        HTTPException: If checkout creation fails
    """
    # Concurrency lock: one in-flight per user/route
    lock_key = f"{current_user.id}:checkout"
    if not await acquire_lock(lock_key, ttl_s=30):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Operation in progress"
        )

    # Idempotency: raw key from method+route+user+body hash
    raw_key = f"POST:/api/v1/payments/checkout:user:{current_user.id}:booking:{payload.booking_id}"
    cached = await get_cached(raw_key)
    if cached:
        # Return cached success response
        return CheckoutResponse(**model_filter(CheckoutResponse, cast(Dict[str, Any], cached)))

    try:
        response_payload = await asyncio.to_thread(
            stripe_service.create_booking_checkout,
            current_user=current_user,
            payload=payload,
            booking_service=booking_service,
        )
        # Cache result for idempotency (success path)
        try:
            if response_payload.success:
                await set_cached(raw_key, response_payload.model_dump(), ttl_s=86400)
        except Exception:
            pass
        return response_payload

    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error creating checkout: {str(e)}")
        status_code = status.HTTP_400_BAD_REQUEST
        if getattr(e, "code", None) == "not_found":
            status_code = status.HTTP_404_NOT_FOUND
        elif getattr(e, "code", None) == "forbidden":
            status_code = status.HTTP_403_FORBIDDEN

        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating checkout: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process payment"
        )
    finally:
        await release_lock(lock_key)


# ========== Analytics Routes (Admin/Instructor) ==========


@router.get("/earnings", response_model=EarningsResponse)
async def get_instructor_earnings(
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
    validate_instructor_role(current_user)
    return await asyncio.to_thread(
        stripe_service.get_instructor_earnings_summary,
        user=current_user,
    )


@router.get("/payouts", response_model=PayoutHistoryResponse)
async def get_instructor_payouts(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    limit: int = 50,
) -> PayoutHistoryResponse:
    """
    Get payout history for an instructor.

    Returns Stripe payout events recorded for the instructor's connected account.

    Returns:
        PayoutHistoryResponse with list of payouts and totals

    Raises:
        HTTPException: If fetching payouts fails
    """
    validate_instructor_role(current_user)
    return await asyncio.to_thread(
        stripe_service.get_instructor_payout_history,
        user=current_user,
        limit=limit,
    )


# ========== Transaction History Route ==========


@router.get("/transactions", response_model=List[TransactionHistoryItem])
async def get_transaction_history(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    limit: int = 20,
    offset: int = 0,
) -> List[TransactionHistoryItem]:
    """
    Get user's transaction history

    Returns list of completed payments with booking details
    """
    return await asyncio.to_thread(
        stripe_service.get_user_transaction_history,
        user=current_user,
        limit=limit,
        offset=offset,
    )


# ========== Credit Balance Route ==========


@router.get("/credits", response_model=CreditBalanceResponse)
async def get_credit_balance(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> CreditBalanceResponse:
    """
    Get user's credit balance

    Returns available credits and expiration
    """
    return await asyncio.to_thread(
        stripe_service.get_user_credit_balance,
        user=current_user,
    )


# ========== Webhook Route (No Authentication) ==========


@router.post("/webhooks/stripe", response_model=WebhookResponse)
async def handle_stripe_webhook(
    request: Request,
    stripe_service: StripeService = Depends(get_stripe_service),
) -> WebhookResponse:
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
        _last_error = None
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

                logger.info(
                    f"Webhook verified with {secret_type} secret for event: {event['type']}"
                )
                break  # Success! Stop trying other secrets
            except stripe.error.SignatureVerificationError as e:
                _last_error = e
                continue  # Try next secret

        if not event:
            logger.error(
                f"Webhook signature verification failed with all {len(webhook_secrets)} configured secrets"
            )
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Log account context for debugging
        if "account" in event:
            logger.info(f"Event from connected account: {event['account']}")
        else:
            logger.info("Event from platform account")

        # Process the verified event
        _result = await asyncio.to_thread(
            stripe_service.handle_webhook_event, event
        )  # Pass parsed event directly

        logger.info(f"Webhook processed successfully: {event['type']}")
        response_payload = {
            "status": "success",
            "event_type": event.get("type", "unknown"),
            "message": f"Event processed with {secret_type} secret",
        }
        return WebhookResponse(**model_filter(WebhookResponse, response_payload))

    except HTTPException:
        # Re-raise HTTP exceptions (like missing signature)
        raise
    except Exception as e:
        logger.error(f"Unexpected webhook error: {str(e)}")
        # Return 200 to prevent Stripe retries for non-recoverable errors
        response_payload = {
            "status": "error",
            "event_type": "unknown",
            "message": "Error logged - returning 200 to prevent retries",
        }
        return WebhookResponse(**model_filter(WebhookResponse, response_payload))


__all__ = ["router"]
