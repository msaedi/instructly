"""
Stripe Webhook Endpoints

Handles Stripe webhook events for payment processing, account updates,
and other marketplace-related events. Includes signature verification
and proper error handling.

Key Features:
- Webhook signature verification for security
- Payment intent status updates
- Connected account status changes
- Comprehensive logging and monitoring
- Idempotent event processing
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.payment_schemas import WebhookResponse
from ..services.config_service import ConfigService
from ..services.pricing_service import PricingService
from ..services.stripe_service import StripeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhooks"])


def get_stripe_service(db: Session = Depends(get_db)) -> StripeService:
    """Get StripeService instance."""
    config_service = ConfigService(db)
    pricing_service = PricingService(db)
    return StripeService(
        db,
        config_service=config_service,
        pricing_service=pricing_service,
    )


@router.post("/payment-events", response_model=WebhookResponse)
async def handle_payment_events(
    request: Request, stripe_service: StripeService = Depends(get_stripe_service)
) -> WebhookResponse:
    """
    Handle Stripe payment-related webhook events.

    Processes events like:
    - payment_intent.succeeded
    - payment_intent.payment_failed
    - payment_intent.canceled
    - payment_intent.requires_action

    Returns:
        Success confirmation message

    Raises:
        HTTPException: If webhook processing fails
    """
    try:
        # Get raw payload and signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")

        if not signature:
            logger.warning("Missing Stripe signature header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stripe-signature header"
            )

        # Verify webhook signature
        if not stripe_service.verify_webhook_signature(payload, signature):
            logger.warning("Invalid Stripe webhook signature")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature"
            )

        # Parse event data
        import json

        event = json.loads(payload.decode("utf-8"))
        event_type = event.get("type", "")

        logger.info(f"Processing Stripe webhook event: {event_type}")

        # Handle payment intent events
        if event_type.startswith("payment_intent."):
            success = stripe_service.handle_payment_intent_webhook(event)
            if success:
                logger.info(f"Successfully processed {event_type} event")
                return WebhookResponse(status="success", event_type=event_type)
            else:
                logger.warning(f"Failed to process {event_type} event")
                return WebhookResponse(status="ignored", event_type=event_type)

        # Handle account events (for connected accounts)
        elif event_type.startswith("account."):
            success = await _handle_account_events(event, stripe_service)
            if success:
                logger.info(f"Successfully processed {event_type} event")
                return WebhookResponse(status="success", event_type=event_type)
            else:
                logger.warning(f"Failed to process {event_type} event")
                return WebhookResponse(status="ignored", event_type=event_type)

        # Handle transfer events (for marketplace payments)
        elif event_type.startswith("transfer."):
            success = await _handle_transfer_events(event, stripe_service)
            if success:
                logger.info(f"Successfully processed {event_type} event")
                return WebhookResponse(status="success", event_type=event_type)
            else:
                logger.warning(f"Failed to process {event_type} event")
                return WebhookResponse(status="ignored", event_type=event_type)

        else:
            # Unhandled event type - log and ignore
            logger.info(f"Unhandled webhook event type: {event_type}")
            return WebhookResponse(status="ignored", event_type=event_type)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process webhook"
        )


@router.post("/account-events", response_model=WebhookResponse)
async def handle_account_events(
    request: Request, stripe_service: StripeService = Depends(get_stripe_service)
) -> WebhookResponse:
    """
    Handle Stripe Connect account-related webhook events.

    Processes events like:
    - account.updated (onboarding status changes)
    - account.application.deauthorized
    - capability.updated

    Returns:
        Success confirmation message

    Raises:
        HTTPException: If webhook processing fails
    """
    try:
        # Get raw payload and signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")

        if not signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stripe-signature header"
            )

        # Verify webhook signature
        if not stripe_service.verify_webhook_signature(payload, signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature"
            )

        # Parse event data
        import json

        event = json.loads(payload.decode("utf-8"))
        event_type = event.get("type", "")

        logger.info(f"Processing Stripe account webhook event: {event_type}")

        # Handle account-related events
        success = await _handle_account_events(event, stripe_service)

        if success:
            logger.info(f"Successfully processed {event_type} event")
            return WebhookResponse(status="success", event_type=event_type)
        else:
            logger.warning(f"Failed to process {event_type} event")
            return WebhookResponse(status="ignored", event_type=event_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Stripe account webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process webhook"
        )


async def _handle_account_events(event: Dict[str, Any], stripe_service: StripeService) -> bool:
    """
    Handle Stripe Connect account events.

    Args:
        event: Stripe webhook event
        stripe_service: StripeService instance

    Returns:
        True if event was handled successfully
    """
    try:
        event_type = event.get("type", "")
        account_data = event.get("data", {}).get("object", {})
        account_id = account_data.get("id")

        if not account_id:
            logger.warning(f"Missing account ID in {event_type} event")
            return False

        if event_type == "account.updated":
            # Check if onboarding status changed
            charges_enabled = account_data.get("charges_enabled", False)
            details_submitted = account_data.get("details_submitted", False)

            # Update onboarding status if completed
            if charges_enabled and details_submitted:
                logger.info(f"Account {account_id} onboarding completed")
                stripe_service.payment_repository.update_onboarding_status(account_id, True)

            return True

        elif event_type == "account.application.deauthorized":
            # Handle account deauthorization
            logger.warning(f"Account {account_id} was deauthorized")
            # Could implement logic to disable instructor or notify them
            return True

        elif event_type.startswith("capability."):
            # Handle capability updates (transfers, card_payments, etc.)
            logger.info(f"Capability updated for account {account_id}")
            return True

        else:
            logger.info(f"Unhandled account event type: {event_type}")
            return False

    except Exception as e:
        logger.error(f"Error handling account event: {str(e)}")
        return False


async def _handle_transfer_events(event: Dict[str, Any], stripe_service: StripeService) -> bool:
    """
    Handle Stripe transfer events for marketplace payments.

    Args:
        event: Stripe webhook event
        stripe_service: StripeService instance

    Returns:
        True if event was handled successfully
    """
    try:
        event_type = event.get("type", "")
        transfer_data = event.get("data", {}).get("object", {})
        transfer_id = transfer_data.get("id")

        if not transfer_id:
            logger.warning(f"Missing transfer ID in {event_type} event")
            return False

        if event_type == "transfer.created":
            logger.info(f"Transfer {transfer_id} created successfully")
            # Could implement logic to track transfer status
            return True

        elif event_type == "transfer.failed":
            logger.error(f"Transfer {transfer_id} failed")
            # Could implement logic to handle failed transfers
            # Maybe notify instructor or retry
            return True

        elif event_type == "transfer.paid":
            logger.info(f"Transfer {transfer_id} paid to connected account")
            return True

        else:
            logger.info(f"Unhandled transfer event type: {event_type}")
            return False

    except Exception as e:
        logger.error(f"Error handling transfer event: {str(e)}")
        return False


@router.get("/test", response_model=WebhookResponse)
async def test_webhook_endpoint() -> WebhookResponse:
    """
    Test endpoint to verify webhook endpoint is accessible.

    This endpoint can be used to test that the webhook route is working
    and accessible from Stripe's servers.

    Returns:
        Simple success message
    """
    logger.info("Webhook test endpoint accessed")
    return WebhookResponse(
        status="success",
        event_type="test",
        message="Stripe webhook endpoint is accessible at /webhooks/stripe",
    )
