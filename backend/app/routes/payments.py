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

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, cast
from urllib.parse import ParseResult, parse_qsl, urlencode, urljoin, urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
import stripe

from ..api.dependencies.auth import get_current_active_user
from ..core.config import settings
from ..core.exceptions import ServiceException
from ..database import get_db
from ..idempotency.cache import get_cached, set_cached
from ..models.user import User
from ..monitoring.prometheus_metrics import prometheus_metrics
from ..ratelimit.dependency import rate_limit
from ..ratelimit.locks import acquire_lock, release_lock
from ..repositories.review_repository import ReviewTipRepository
from ..schemas.payment_schemas import (
    CheckoutResponse,
    CreateCheckoutRequest,
    CreditBalanceResponse,
    DashboardLinkResponse,
    DeleteResponse,
    EarningsResponse,
    IdentityRefreshResponse,
    IdentitySessionResponse,
    InstantPayoutResponse,
    InstructorInvoiceSummary,
    OnboardingResponse,
    OnboardingStatusResponse,
    PaymentMethodResponse,
    PayoutScheduleResponse,
    SavePaymentMethodRequest,
    TransactionHistoryItem,
    WebhookResponse,
)
from ..services.booking_service import BookingService
from ..services.cache_service import CacheService, get_cache_service
from ..services.config_service import ConfigService
from ..services.dependencies import get_booking_service
from ..services.payment_summary_service import build_student_payment_summary
from ..services.pricing_service import PricingService
from ..services.stripe_service import StripeService
from ..utils.strict import model_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])


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
    db: Session = Depends(get_db),
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
    try:
        # Validate instructor role
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            logger.error(f"No instructor profile found for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Instructor profile not found",
                    "code": "PAYMENTS_INSTRUCTOR_PROFILE_NOT_FOUND",
                },
            )

        callback_from: Optional[str] = None
        if return_to and return_to.startswith("/"):
            parsed_return = urlparse(return_to)
            redirect_path = (parsed_return.path or "").strip().lower()
            if redirect_path:
                segments = [segment for segment in redirect_path.split("/") if segment]
                if (
                    len(segments) >= 3
                    and segments[0] == "instructor"
                    and segments[1] == "onboarding"
                ):
                    callback_from = segments[2]
                elif len(segments) >= 2 and segments[0] == "instructor":
                    callback_from = segments[1]
                elif segments:
                    callback_from = segments[-1]

        if callback_from:
            sanitized = "".join(ch for ch in callback_from if ch.isalnum() or ch in {"-", "_"})
            callback_from = sanitized or None

        configured_frontend = (settings.frontend_url or "").strip()
        local_frontend = (settings.local_beta_frontend_origin or "").strip()
        request_host = (request.headers.get("host") or "").strip()

        def normalize_origin(raw: Optional[str]) -> Optional[str]:
            if not raw:
                return None
            parsed_raw: ParseResult = urlparse(raw)
            scheme = parsed_raw.scheme or request.url.scheme
            if parsed_raw.netloc:
                return f"{scheme}://{parsed_raw.netloc}".rstrip("/")
            if parsed_raw.path and raw.startswith(("http://", "https://")):
                return raw.rstrip("/")
            return None

        origin: Optional[str] = None
        origin_candidates: list[str] = []

        if configured_frontend:
            origin_candidates.append(configured_frontend)

        request_host_lower = request_host.lower()
        parsed_front = urlparse(configured_frontend) if configured_frontend else None
        configured_hostname = (parsed_front.hostname or "").lower() if parsed_front else ""

        if (
            request_host_lower.startswith("api.")
            and configured_hostname
            and request_host_lower.split(":", 1)[0].removeprefix("api.") == configured_hostname
        ):
            scheme = (
                parsed_front.scheme or request.url.scheme if parsed_front else request.url.scheme
            )
            parsed_netloc = parsed_front.netloc if parsed_front else ""
            netloc = parsed_netloc or configured_hostname
            origin_candidates.insert(0, f"{scheme}://{netloc}")

        if local_frontend and (
            "beta-local" in request_host_lower or "beta-local" in local_frontend.lower()
        ):
            origin_candidates.insert(0, local_frontend)

        if request_host:
            origin_candidates.append(f"{request.url.scheme}://{request_host}")

        origin_candidates.append(str(request.base_url))

        for candidate in origin_candidates:
            normalized = normalize_origin(candidate)
            if normalized:
                origin = normalized
                break

        if not origin:
            origin = str(request.base_url).rstrip("/")

        raw_path = (settings.connect_return_path or "/").strip() or "/"
        path_only, _, existing_query = raw_path.partition("?")
        base_query_pairs = (
            dict(parse_qsl(existing_query, keep_blank_values=True)) if existing_query else {}
        )
        if callback_from:
            base_query_pairs["from"] = callback_from

        return_query = urlencode(base_query_pairs, doseq=True)
        normalized_path = path_only.lstrip("/") or ""
        if return_query:
            normalized_path = (
                f"{normalized_path}?{return_query}" if normalized_path else f"?{return_query}"
            )

        refresh_query_pairs = dict(base_query_pairs)
        refresh_query_pairs["refresh"] = "1"
        refresh_query = urlencode(refresh_query_pairs, doseq=True)
        refresh_path = path_only.lstrip("/") or ""
        if refresh_query:
            refresh_path = (
                f"{refresh_path}?{refresh_query}" if refresh_path else f"?{refresh_query}"
            )

        return_url = urljoin(f"{origin}/", normalized_path)
        refresh_url = urljoin(f"{origin}/", refresh_path)

        # Check if account already exists
        existing_account = stripe_service.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )

        if existing_account:
            # Check onboarding status
            account_status = await run_in_threadpool(
                stripe_service.check_account_status, instructor_profile.id
            )

            if account_status["onboarding_completed"]:
                return OnboardingResponse(
                    account_id=existing_account.stripe_account_id,
                    onboarding_url="",  # No URL needed for completed onboarding
                    already_onboarded=True,
                )
            else:
                # Create new onboarding link for existing account
                onboarding_url = await run_in_threadpool(
                    stripe_service.create_account_link,
                    instructor_profile.id,
                    refresh_url,
                    return_url,
                )

                return OnboardingResponse(
                    account_id=existing_account.stripe_account_id,
                    onboarding_url=onboarding_url,
                    already_onboarded=False,
                )

        # Create new connected account
        connected_account = await run_in_threadpool(
            stripe_service.create_connected_account, instructor_profile.id, current_user.email
        )

        # Create onboarding link
        onboarding_url = await run_in_threadpool(
            stripe_service.create_account_link,
            instructor_profile.id,
            refresh_url,
            return_url,
        )

        logger.info(f"Started onboarding for instructor {instructor_profile.id}")

        return OnboardingResponse(
            account_id=connected_account.stripe_account_id,
            onboarding_url=onboarding_url,
            already_onboarded=False,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like from validate_instructor_role)
        raise
    except ServiceException as e:
        logger.error(f"Service error during onboarding: {str(e)}")
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error during onboarding: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to start onboarding process",
                "code": "PAYMENTS_ONBOARDING_FAILED",
            },
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found"
            )

        # Get account status
        status_data = await run_in_threadpool(
            stripe_service.check_account_status, instructor_profile.id
        )

        # Also reflect identity status from our DB to avoid blocking on Stripe calls
        try:
            profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
            if not getattr(profile, "identity_verified_at", None):
                status_data.setdefault("requirements_extra", []).append("identity_status:pending")
        except Exception:
            # If repo lookup fails, skip requirement hint
            pass

        return OnboardingStatusResponse(
            has_account=status_data.get("has_account", False),
            onboarding_completed=bool(status_data.get("onboarding_completed", False)),
            charges_enabled=bool(status_data.get("can_accept_payments", False)),
            payouts_enabled=bool(status_data.get("payouts_enabled", False)),
            details_submitted=bool(status_data.get("details_submitted", False)),
            requirements=status_data.get("requirements_extra", []),
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check onboarding status",
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
    dependencies=[Depends(rate_limit("financial"))],
)
async def refresh_identity_status(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> IdentityRefreshResponse:
    """Fetch latest Stripe Identity status and persist verification on success.

    This avoids blocking general status calls and lets the UI trigger a one-off refresh
    right after the modal/hosted flow returns.
    """
    try:
        validate_instructor_role(current_user)

        status_data = cast(
            Dict[str, Any],
            await run_in_threadpool(stripe_service.get_latest_identity_status, current_user.id),
        )
        status_value = status_data.get("status") or "unknown"

        if status_value == "verified":
            # Persist verification timestamp and session id
            try:
                profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
                if profile:
                    stripe_service.instructor_repository.update(
                        profile.id,
                        identity_verified_at=datetime.now(timezone.utc),
                        identity_verification_session_id=status_data.get("id"),
                    )
            except Exception as e:
                logger.error(
                    f"Failed to persist identity verification for user {current_user.id}: {e}"
                )
                # Still return verified=true since Stripe says verified
            response_payload = {"status": status_value, "verified": True}
            return IdentityRefreshResponse(
                **model_filter(IdentityRefreshResponse, response_payload)
            )

        response_payload = {"status": status_value, "verified": False}
        return IdentityRefreshResponse(**model_filter(IdentityRefreshResponse, response_payload))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing identity status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh identity status",
        )


@router.post(
    "/connect/payout-schedule",
    response_model=PayoutScheduleResponse,
    dependencies=[Depends(rate_limit("financial"))],
)
async def set_payout_schedule(
    interval: str = "weekly",
    weekly_anchor: str = "tuesday",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PayoutScheduleResponse:
    """
    Set payout schedule for the current instructor's connected account.

    Default: weekly on Tuesday. Valid anchors: monday..sunday.
    """
    try:
        validate_instructor_role(current_user)

        # Get instructor profile
        instructor_profile = stripe_service.instructor_repository.get_by_user_id(current_user.id)
        if not instructor_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found"
            )

        result = cast(
            Dict[str, Any],
            await run_in_threadpool(
                stripe_service.set_payout_schedule_for_account,
                instructor_profile.id,
                interval,
                weekly_anchor,
            ),
        )
        response_payload = {
            "ok": True,
            "account_id": result.get("account_id"),
            "settings": result.get("settings"),
        }
        return PayoutScheduleResponse(**model_filter(PayoutScheduleResponse, response_payload))
    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Error setting payout schedule: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error setting payout schedule: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set payout schedule",
        )


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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found"
            )

        # Get connected account
        connected_account = (
            stripe_service.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile.id
            )
        )

        if not connected_account or not connected_account.onboarding_completed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Onboarding must be completed before accessing dashboard",
            )

        # Create dashboard link
        login_link = await run_in_threadpool(
            stripe.Account.create_login_link, connected_account.stripe_account_id
        )

        logger.info(f"Created dashboard link for instructor {instructor_profile.id}")

        return DashboardLinkResponse(
            dashboard_url=login_link.url,
            expires_in_minutes=5,  # Stripe login links expire after 5 minutes
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except stripe.StripeError as e:
        logger.error(f"Stripe error creating dashboard link: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create dashboard link"
        )
    except ServiceException as e:
        logger.error(f"Service error creating dashboard link: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating dashboard link: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create dashboard link",
        )


@router.post("/connect/instant-payout", response_model=InstantPayoutResponse)
async def request_instant_payout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> InstantPayoutResponse:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found"
            )

        connected = stripe_service.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if not connected or not connected.onboarding_completed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Onboarding incomplete"
            )

        # Create a payout with method='instant' on the connected account
        # Note: Requires Stripe account eligibility and sufficient balance
        payout = cast(
            stripe.Payout,
            await run_in_threadpool(
                stripe.Payout.create,
                amount=0,  # 0 means Stripe will pay out the maximum available (supported in test mode)
                currency=settings.stripe_currency or "usd",
                method="instant",
                stripe_account=connected.stripe_account_id,
            ),
        )

        prometheus_metrics.inc_instant_payout_request("success")
        response_payload = {
            "ok": True,
            "payout_id": payout.id,
            "status": payout.status,
        }
        return InstantPayoutResponse(**model_filter(InstantPayoutResponse, response_payload))
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Instant payout failed"
        )


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
        _customer = stripe_service.get_or_create_customer(current_user.id)

        # Save payment method
        payment_method = stripe_service.save_payment_method(
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
        success = stripe_service.delete_payment_method(method_id, current_user.id)

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
    db: Session = Depends(get_db),
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
    raw_key = f"POST:/api/payments/checkout:user:{current_user.id}:booking:{payload.booking_id}"
    cached = await get_cached(raw_key)
    if cached:
        # Return cached success response
        return CheckoutResponse(**model_filter(CheckoutResponse, cast(Dict[str, Any], cached)))

    try:
        # Validate student role
        validate_student_role(current_user)

        # Get booking and verify ownership
        booking = stripe_service.booking_repository.get_by_id(payload.booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.student_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only pay for your own bookings",
            )

        # Check booking status - should be confirmed and not yet paid
        if booking.status not in ["CONFIRMED", "PENDING"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot process payment for booking with status: {booking.status}",
            )

        # Check if booking already has a successful payment
        existing_payment = stripe_service.payment_repository.get_payment_by_booking_id(booking.id)
        if existing_payment and existing_payment.status == "succeeded":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Booking has already been paid"
            )

        # Save payment method if requested
        if payload.save_payment_method:
            if not payload.payment_method_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Payment method is required when saving for future use",
                )
            stripe_service.save_payment_method(
                user_id=current_user.id,
                payment_method_id=payload.payment_method_id,
                set_as_default=False,
            )

        # Process payment
        payment_result = await run_in_threadpool(
            stripe_service.process_booking_payment,
            payload.booking_id,
            payload.payment_method_id,
            payload.requested_credit_cents,
        )

        # Update booking status if payment succeeded
        if payment_result["success"] and payment_result["status"] == "succeeded":
            booking.status = "CONFIRMED"
            stripe_service.db.flush()
            try:
                booking_service.invalidate_booking_cache(booking)
            except Exception as cache_err:
                logger.warning(f"Failed to invalidate booking cache: {cache_err}")

        logger.info(f"Processed payment for booking {payload.booking_id}")

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

        response_data = {
            "success": payment_result["success"],
            "payment_intent_id": payment_result["payment_intent_id"],
            "status": payment_result["status"],
            "amount": payment_result["amount"],
            "application_fee": payment_result["application_fee"],
            "client_secret": client_secret,
            "requires_action": payment_result["status"]
            in ["requires_action", "requires_confirmation"],
        }
        response_payload = CheckoutResponse(**model_filter(CheckoutResponse, response_data))
        # Cache result for idempotency (success path)
        try:
            if payment_result["success"]:
                await set_cached(raw_key, response_payload.model_dump(), ttl_s=86400)
        except Exception:
            pass
        return response_payload

    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error creating checkout: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found"
            )

        # Get earnings data (using instructor user ID for now)
        earnings = stripe_service.get_instructor_earnings(current_user.id)

        payment_repo = stripe_service.payment_repository
        pricing_config, _ = stripe_service.config_service.get_pricing_config()
        tip_repo = ReviewTipRepository(db)
        instructor_payments = payment_repo.get_instructor_payment_history(
            instructor_id=current_user.id,
            limit=100,
        )

        def _money_to_cents(value: Optional[Any]) -> int:
            if value is None:
                return 0
            try:
                return int((Decimal(value) * Decimal("100")).quantize(Decimal("1")))
            except Exception:
                return 0

        invoices: List[InstructorInvoiceSummary] = []
        total_minutes = 0

        for payment in instructor_payments:
            booking = payment.booking
            if not booking:
                continue

            minutes = int(getattr(booking, "duration_minutes", 0) or 0)
            total_minutes += minutes

            student = getattr(booking, "student", None)
            student_name = None
            if student:
                last_initial = (student.last_name or "").strip()[:1]
                student_name = (
                    f"{student.first_name} {last_initial}." if last_initial else student.first_name
                )

            try:
                summary = build_student_payment_summary(
                    booking=booking,
                    pricing_config=pricing_config,
                    payment_repo=payment_repo,
                    review_tip_repo=tip_repo,
                )
            except Exception as exc:
                logger.error(
                    "Failed to build instructor invoice summary for booking %s: %s",
                    getattr(booking, "id", "unknown"),
                    exc,
                )
                summary = None

            total_paid_cents = int(payment.amount or 0)
            tip_cents = _money_to_cents(summary.tip_paid if summary else None)

            invoices.append(
                InstructorInvoiceSummary(
                    booking_id=booking.id,
                    lesson_date=booking.booking_date,
                    start_time=booking.start_time,
                    service_name=booking.service_name,
                    student_name=student_name,
                    duration_minutes=minutes or None,
                    total_paid_cents=total_paid_cents,
                    tip_cents=tip_cents,
                    instructor_share_cents=max(
                        0,
                        int(payment.amount or 0) - int(payment.application_fee or 0),
                    ),
                    status="paid" if payment.status == "succeeded" else payment.status,
                    created_at=payment.created_at,
                )
            )

        hours_invoiced = total_minutes / 60.0 if total_minutes else 0.0

        response_payload = {
            "total_earned": earnings.get("total_earned"),
            "total_fees": earnings.get("total_fees"),
            "booking_count": earnings.get("booking_count"),
            "average_earning": earnings.get("average_earning"),
            "hours_invoiced": hours_invoiced,
            "service_count": len(instructor_payments),
            "period_start": earnings.get("period_start"),
            "period_end": earnings.get("period_end"),
            "invoices": invoices,
        }

        return EarningsResponse(**model_filter(EarningsResponse, response_payload))

    except HTTPException:
        raise
    except ServiceException as e:
        logger.error(f"Service error getting earnings: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting earnings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get earnings data"
        )


# ========== Transaction History Route ==========


@router.get("/transactions", response_model=List[TransactionHistoryItem])
async def get_transaction_history(
    current_user: User = Depends(get_current_active_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[TransactionHistoryItem]:
    """
    Get user's transaction history

    Returns list of completed payments with booking details
    """
    try:
        # Get payment intents for this user
        payment_repo = stripe_service.payment_repository
        fetch_limit = max(limit + offset + 10, limit)
        transactions = payment_repo.get_user_payment_history(
            user_id=current_user.id,
            limit=fetch_limit,
            offset=0,
        )

        tip_repo = ReviewTipRepository(db)
        pricing_config, _ = stripe_service.config_service.get_pricing_config()

        result: List[TransactionHistoryItem] = []
        seen_bookings: set[str] = set()

        for payment in transactions:
            booking = payment.booking
            if not booking or booking.id in seen_bookings:
                continue

            seen_bookings.add(booking.id)

            try:
                summary = build_student_payment_summary(
                    booking=booking,
                    pricing_config=pricing_config,
                    payment_repo=payment_repo,
                    review_tip_repo=tip_repo,
                )
            except Exception as exc:
                logger.error("Failed to build payment summary for booking %s: %s", booking.id, exc)
                continue

            instructor = booking.instructor
            instructor_name = "Instructor"
            if instructor and instructor.last_name:
                instructor_name = f"{instructor.first_name} {instructor.last_name[0]}."
            elif instructor and instructor.first_name:
                instructor_name = instructor.first_name

            result.append(
                TransactionHistoryItem(
                    id=payment.id,
                    booking_id=booking.id,
                    service_name=booking.service_name,
                    instructor_name=instructor_name,
                    booking_date=booking.booking_date.isoformat(),
                    start_time=booking.start_time.isoformat(),
                    end_time=booking.end_time.isoformat(),
                    duration_minutes=booking.duration_minutes,
                    hourly_rate=float(booking.hourly_rate),
                    lesson_amount=summary.lesson_amount,
                    service_fee=summary.service_fee,
                    credit_applied=summary.credit_applied,
                    tip_amount=summary.tip_amount,
                    tip_paid=summary.tip_paid,
                    tip_status=summary.tip_status,
                    total_paid=summary.total_paid,
                    status=payment.status,
                    created_at=payment.created_at.isoformat(),
                )
            )

            if len(result) >= offset + limit:
                break

        return result[offset : offset + limit]

    except Exception as e:
        logger.error(f"Error getting transaction history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get transaction history",
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
    try:
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

        response_payload = {
            "available": float(total_cents) / 100.0,
            "expires_at": earliest_exp,
            "pending": 0.0,
        }

        return CreditBalanceResponse(**model_filter(CreditBalanceResponse, response_payload))

    except Exception as e:
        logger.error(f"Error getting credit balance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get credit balance"
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
        _result = stripe_service.handle_webhook_event(event)  # Pass parsed event directly

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
