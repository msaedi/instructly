from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any

from ...core.exceptions import ServiceException
from ...models.booking import PaymentStatus
from ...models.payment import PaymentIntent
from ...repositories.booking_repository import BookingRepository
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...repositories.payment_repository import PaymentRepository
from ..base import BaseService

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


class StripeWebhookRouterMixin(BaseService):
    """Stripe webhook signature verification, routing, and simple handlers."""

    booking_repository: BookingRepository
    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository
    cache_service: Any

    if TYPE_CHECKING:

        def _handle_charge_webhook(self, event: dict[str, Any]) -> bool:
            ...

        def _handle_payout_webhook(self, event: dict[str, Any]) -> bool:
            ...

        def _persist_verified_identity(self, **kwargs: Any) -> None:
            ...

        def _stripe_has_field(self, obj: Any, key: str) -> bool:
            ...

    @BaseService.measure_operation("stripe_verify_webhook_signature")
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature."""
        stripe_sdk = _stripe_service_module().stripe
        settings = _stripe_service_module().settings
        try:
            webhook_secret = settings.stripe_webhook_secret
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            try:
                secret_value = (
                    webhook_secret.get_secret_value()
                    if hasattr(webhook_secret, "get_secret_value")
                    else str(webhook_secret)
                )
                stripe_sdk.Webhook.construct_event(payload, signature, secret_value)
                return True
            except stripe_sdk.SignatureVerificationError:
                self.logger.warning("Invalid webhook signature")
                return False
        except Exception as exc:
            self.logger.error("Error verifying webhook signature: %s", exc)
            raise ServiceException(f"Failed to verify webhook signature: {str(exc)}")

    @BaseService.measure_operation("stripe_handle_webhook")
    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Process an already-verified Stripe webhook event."""
        try:
            event_type = event.get("type", "")
            self.logger.info("Processing webhook event: %s", event_type)

            if event_type.startswith("payment_intent."):
                success = self.handle_payment_intent_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("account."):
                success = self._handle_account_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("transfer."):
                success = self._handle_transfer_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("charge."):
                success = self._handle_charge_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("payout."):
                success = self._handle_payout_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("identity.verification_session."):
                success = self._handle_identity_webhook(event)
                return {"success": success, "event_type": event_type}

            self.logger.info("Unhandled webhook event type: %s", event_type)
            return {"success": True, "event_type": event_type, "handled": False}
        except Exception as exc:
            self.logger.error("Error processing webhook event: %s", exc)
            raise ServiceException(f"Failed to process webhook event: {str(exc)}")

    @BaseService.measure_operation("stripe_handle_webhook_with_verification")
    def handle_webhook(self, payload: str, signature: str) -> dict[str, Any]:
        """Verify and process a Stripe webhook event in one call."""
        stripe_sdk = _stripe_service_module().stripe
        settings = _stripe_service_module().settings
        try:
            webhook_secret = (
                settings.stripe_webhook_secret.get_secret_value()
                if settings.stripe_webhook_secret
                else None
            )
            if not webhook_secret:
                raise ServiceException("Webhook secret not configured")

            try:
                event = stripe_sdk.Webhook.construct_event(
                    payload.encode("utf-8") if isinstance(payload, str) else payload,
                    signature,
                    webhook_secret,
                )
            except stripe_sdk.SignatureVerificationError as exc:
                self.logger.warning("Invalid webhook signature: %s", exc)
                raise ServiceException("Invalid webhook signature")
            except Exception as exc:
                self.logger.error("Error constructing webhook event: %s", exc)
                raise ServiceException(f"Invalid webhook payload: {str(exc)}")

            return dict(self.handle_webhook_event(event))
        except ServiceException:
            raise
        except Exception as exc:
            self.logger.error("Unexpected error handling webhook: %s", exc)
            raise ServiceException(f"Failed to process webhook: {str(exc)}")

    @BaseService.measure_operation("stripe_handle_payment_intent_webhook")
    def handle_payment_intent_webhook(self, event: dict[str, Any]) -> bool:
        """Handle payment intent webhook events."""
        try:
            with self.transaction():
                payment_intent = event["data"]["object"]
                payment_intent_id = payment_intent["id"]
                new_status = payment_intent["status"]
                payment_record = self.payment_repository.update_payment_status(
                    payment_intent_id, new_status
                )

                if not payment_record:
                    self.logger.warning(
                        "Payment record not found for webhook event %s",
                        payment_intent_id,
                    )
                    return False

                self.logger.info("Updated payment %s status to %s", payment_intent_id, new_status)
                if new_status == "succeeded":
                    self._handle_successful_payment(payment_record)
                if new_status == "requires_capture":
                    self._advance_booking_on_capture(payment_record)
                return True
        except Exception as exc:
            self.logger.error("Error handling payment intent webhook: %s", exc)
            raise ServiceException(f"Failed to handle payment webhook: {str(exc)}")

    @BaseService.measure_operation("stripe_advance_booking_on_capture")
    def _advance_booking_on_capture(self, payment_record: PaymentIntent) -> None:
        """Advance booking to CONFIRMED when PI reaches requires_capture."""
        booking_id = payment_record.booking_id
        now = datetime.now(timezone.utc)
        with self.transaction():
            rows = self.booking_repository.atomic_confirm_if_pending(booking_id, now)
            if rows == 0:
                self.logger.info(
                    "Booking %s not in PENDING state (rows=%d), skipping capture advance",
                    booking_id,
                    rows,
                )
                return

            booking_payment = self.booking_repository.ensure_payment(booking_id)
            booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
            booking_payment.payment_intent_id = payment_record.stripe_payment_intent_id
            booking_payment.auth_attempted_at = now
            booking_payment.auth_failure_count = 0
            booking_payment.auth_last_error = None

        self.logger.info(
            "Booking %s confirmed via PaymentElement webhook (requires_capture)",
            booking_id,
        )

    def _handle_successful_payment(self, payment_record: PaymentIntent) -> None:
        """Handle successful payment processing."""
        try:
            booking = self.booking_repository.get_by_id(payment_record.booking_id)
            if not booking:
                self.logger.warning(
                    "Successful payment received for missing booking %s",
                    payment_record.booking_id,
                )
                return

            if booking.status == "PENDING":
                booking.status = "CONFIRMED"
                self.booking_repository.flush()

            from ..booking_service import BookingService

            booking_service = BookingService(self.db, cache_service=self.cache_service)
            try:
                booking_service.invalidate_booking_cache(booking)
            except Exception as cache_err:
                self.logger.warning("Failed to invalidate booking caches: %s", cache_err)

            self.logger.info(
                "Processed successful payment for booking %s",
                payment_record.booking_id,
            )
        except Exception as exc:
            self.logger.error("Error handling successful payment: %s", exc)

    def _handle_account_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe Connect account events."""
        try:
            event_type = event.get("type", "")
            account_data = event.get("data", {}).get("object", {})
            account_id = account_data.get("id")

            if event_type == "account.updated":
                charges_enabled = account_data.get("charges_enabled", False)
                details_submitted = account_data.get("details_submitted", False)
                if charges_enabled and details_submitted:
                    self.payment_repository.update_onboarding_status(account_id, True)
                    self.logger.info("Account %s onboarding completed", account_id)
                return True

            if event_type == "account.application.deauthorized":
                self.logger.warning("Account %s was deauthorized", account_id)
                return True

            return False
        except Exception as exc:
            self.logger.error("Error handling account webhook: %s", exc)
            return False

    def _handle_transfer_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe transfer events."""
        try:
            event_type = event.get("type", "")
            transfer_data = event.get("data", {}).get("object", {})
            transfer_id = transfer_data.get("id")

            if event_type == "transfer.created":
                self.logger.info("Transfer %s created", transfer_id)
                return True
            if event_type == "transfer.paid":
                self.logger.info("Transfer %s paid successfully", transfer_id)
                return True
            if event_type == "transfer.failed":
                self.logger.error("Transfer %s failed", transfer_id)
                return True
            if event_type == "transfer.reversed":
                try:
                    amount = transfer_data.get("amount")
                    self.logger.info("Transfer %s reversed (amount=%s)", transfer_id, amount)
                except Exception:
                    _stripe_service_module().logger.debug("Non-fatal error ignored", exc_info=True)
                return True
            return False
        except Exception as exc:
            self.logger.error("Error handling transfer webhook: %s", exc)
            return False

    def _handle_identity_webhook(self, event: dict[str, Any]) -> bool:
        """Persist Stripe Identity verification status changes."""
        try:
            obj = event.get("data", {}).get("object", {})
            verification_status = obj.get("status")
            metadata = obj.get("metadata") or {}
            user_id = metadata.get("user_id")
            if not user_id:
                return True

            profile = self.instructor_repository.get_by_user_id(user_id)
            if not profile:
                return True

            if verification_status == "verified":
                try:
                    has_verified_outputs = self._stripe_has_field(obj, "verified_outputs")
                    self._persist_verified_identity(
                        profile_id=profile.id,
                        user_id=user_id,
                        session=obj,
                        session_id=obj.get("id"),
                        refresh_session=not has_verified_outputs,
                        prefetched_session=obj if has_verified_outputs else None,
                    )
                except Exception as exc:
                    self.logger.error(
                        "Failed updating identity verification on profile %s: %s",
                        profile.id,
                        exc,
                    )
                    try:
                        self.instructor_repository.update(
                            profile.id,
                            identity_verified_at=datetime.now(timezone.utc),
                            identity_verification_session_id=obj.get("id"),
                        )
                    except Exception:
                        logger.warning(
                            "Non-fatal identity webhook fallback persistence failure",
                            exc_info=True,
                        )
                return True

            if verification_status == "processing":
                try:
                    self.instructor_repository.update(
                        profile.id,
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                return True

            if verification_status in {"requires_input", "canceled"}:
                try:
                    self.instructor_repository.update(
                        profile.id,
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
                return True

            return True
        except Exception as exc:
            self.logger.error("Error handling identity webhook: %s", exc)
            return False
