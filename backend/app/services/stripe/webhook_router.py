from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.exc import OperationalError
import stripe

from ...core.exceptions import ServiceException
from ...models.booking import BookingStatus, PaymentStatus
from ...models.payment import PaymentIntent
from ...repositories.booking_repository import BookingRepository
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...repositories.payment_repository import PaymentRepository
from ..base import BaseService
from .exceptions import WebhookPermanentError, WebhookRetryableError

if TYPE_CHECKING:
    from ..stripe_service import StripeServiceModuleProtocol

logger = logging.getLogger(__name__)


def _stripe_service_module() -> StripeServiceModuleProtocol:
    return cast("StripeServiceModuleProtocol", import_module("app.services.stripe_service"))


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

    @BaseService.measure_operation("stripe_handle_webhook_event")
    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Process an already-verified Stripe webhook event.

        Transient Stripe errors (APIConnectionError, RateLimitError, APIError) are
        re-raised as :class:`WebhookRetryableError` so the endpoint returns 503 and
        Stripe retries. Permanent errors (InvalidRequestError, CardError,
        AuthenticationError) become :class:`WebhookPermanentError` so the endpoint
        returns 200 and Stripe stops retrying.
        """
        try:
            event_type = event.get("type", "")
            self.logger.info("Processing webhook event: %s", event_type)

            if event_type.startswith("payment_intent."):
                success = self.handle_payment_intent_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("account."):
                success = self._handle_account_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("capability."):
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
            if event_type.startswith("customer."):
                success = self._handle_customer_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("payment_method."):
                success = self._handle_payment_method_webhook(event)
                return {"success": success, "event_type": event_type}
            if event_type.startswith("review.") or event_type.startswith("radar."):
                success = self._handle_fraud_webhook(event)
                return {"success": success, "event_type": event_type}

            self.logger.info("Unhandled webhook event type: %s", event_type)
            return {"success": True, "event_type": event_type, "handled": False}
        except (
            stripe.APIConnectionError,
            stripe.RateLimitError,
            stripe.APIError,
        ) as exc:
            self.logger.warning("Transient Stripe error while processing webhook: %s", exc)
            raise WebhookRetryableError(f"Transient Stripe error: {str(exc)}") from exc
        except (
            stripe.InvalidRequestError,
            stripe.CardError,
            stripe.AuthenticationError,
        ) as exc:
            self.logger.error("Permanent Stripe error while processing webhook: %s", exc)
            raise WebhookPermanentError(f"Permanent Stripe error: {str(exc)}") from exc
        except (WebhookRetryableError, WebhookPermanentError, OperationalError):
            # C2: inner handlers already classify retryable vs permanent; the
            # outer endpoint needs them verbatim to map to 503 vs 200. Wrapping
            # them in ServiceException here collapses both to the generic
            # Exception branch, which defeats H2.
            raise
        except Exception as exc:
            self.logger.error("Error processing webhook event: %s", exc)
            raise ServiceException(f"Failed to process webhook event: {str(exc)}")

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
        except (WebhookRetryableError, WebhookPermanentError, OperationalError):
            # C2: let typed exceptions bubble to the outer handler unchanged so
            # the endpoint's 503-vs-200 mapping still applies. OperationalError
            # specifically covers pgbouncer hiccups and lock contention — both
            # transient by nature.
            raise
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
        """Handle successful payment processing.

        Booking and transfer errors are allowed to propagate so the webhook endpoint
        can distinguish transient failures (retry via 503) from permanent ones.
        Only cache invalidation is non-critical and its errors are swallowed.
        """
        booking = self.booking_repository.get_by_id(payment_record.booking_id)
        if not booking:
            self.logger.warning(
                "Successful payment received for missing booking %s",
                payment_record.booking_id,
            )
            return

        if booking.status == BookingStatus.PENDING.value:
            booking.mark_confirmed()
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

    def _handle_account_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe Connect account events."""
        try:
            event_type = event.get("type", "")
            account_data = event.get("data", {}).get("object", {})
            if (
                event_type.startswith("account.external_account.")
                or event_type == "capability.updated"
            ):
                account_id = event.get("account", "unknown")
            else:
                account_id = account_data.get("id")

            if event_type == "account.updated":
                charges_enabled = account_data.get("charges_enabled", False)
                details_submitted = account_data.get("details_submitted", False)
                requirements = account_data.get("requirements") or {}
                disabled_reason = requirements.get("disabled_reason")
                should_complete = bool(
                    charges_enabled and details_submitted and not disabled_reason
                )
                # QF1: Stripe resends account.updated frequently (heartbeats on
                # every KYC re-check). Skip the write when state is unchanged to
                # avoid DB churn on every heartbeat; account_record may be None
                # (unknown account) in which case we fall through and attempt
                # the write so the repository-layer handles persistence/logging.
                current_record = self.payment_repository.get_connected_account_by_stripe_id(
                    account_id
                )
                if (
                    current_record is not None
                    and bool(current_record.onboarding_completed) == should_complete
                ):
                    self.logger.debug(
                        "Account %s onboarding unchanged (completed=%s); skipping write",
                        account_id,
                        should_complete,
                    )
                    return True
                self.payment_repository.update_onboarding_status(account_id, should_complete)
                if should_complete:
                    self.logger.info("Account %s onboarding completed", account_id)
                else:
                    self.logger.warning(
                        "Account %s onboarding marked incomplete "
                        "(charges_enabled=%s details_submitted=%s disabled_reason=%s)",
                        account_id,
                        charges_enabled,
                        details_submitted,
                        disabled_reason,
                    )
                return True
            if event_type == "account.external_account.created":
                self.logger.info(
                    "External account created for %s: %s",
                    account_id,
                    account_data.get("id"),
                )
                return True
            if event_type == "account.external_account.updated":
                self.logger.info(
                    "External account updated for %s: %s",
                    account_id,
                    account_data.get("id"),
                )
                return True
            if event_type == "account.external_account.deleted":
                self.logger.warning(
                    "External account deleted for %s: %s",
                    account_id,
                    account_data.get("id"),
                )
                return True
            if event_type == "capability.updated":
                self.logger.info(
                    "Capability updated for %s: capability=%s, status=%s",
                    account_id,
                    account_data.get("id"),
                    account_data.get("status"),
                )
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
            if event_type == "transfer.reversed":
                try:
                    amount = transfer_data.get("amount")
                    self.logger.info("Transfer %s reversed (amount=%s)", transfer_id, amount)
                except Exception:
                    _stripe_service_module().logger.warning(
                        "Failed to log reversed transfer amount for transfer %s",
                        transfer_id,
                        exc_info=True,
                    )
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
                    logger.warning(
                        "Failed to persist processing identity session for profile %s",
                        profile.id,
                        exc_info=True,
                    )
                return True

            if verification_status in {"requires_input", "canceled"}:
                try:
                    self.instructor_repository.update(
                        profile.id,
                        identity_verification_session_id=obj.get("id"),
                    )
                except Exception:
                    logger.warning(
                        "Failed to persist identity session state %s for profile %s",
                        verification_status,
                        profile.id,
                        exc_info=True,
                    )
                return True

            return True
        except Exception as exc:
            self.logger.error("Error handling identity webhook: %s", exc)
            return False

    def _handle_customer_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe customer lifecycle events for observability."""
        try:
            event_type = event.get("type", "")
            customer_data = event.get("data", {}).get("object", {})
            customer_id = customer_data.get("id")

            if event_type == "customer.created":
                self.logger.info(
                    "Customer created: %s, email=%s",
                    customer_id,
                    customer_data.get("email"),
                )
                return True
            if event_type == "customer.updated":
                self.logger.info("Customer updated: %s", customer_id)
                return True
            return False
        except Exception as exc:
            self.logger.error("Error handling customer webhook: %s", exc)
            return False

    def _handle_payment_method_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe payment method events for observability."""
        try:
            event_type = event.get("type", "")
            payment_method_data = event.get("data", {}).get("object", {})
            payment_method_id = payment_method_data.get("id")
            payment_method_type = payment_method_data.get("type")
            customer_id = payment_method_data.get("customer")

            if event_type == "payment_method.attached":
                self.logger.info(
                    "Payment method attached: %s, type=%s, customer=%s",
                    payment_method_id,
                    payment_method_type,
                    customer_id,
                )
                return True
            if event_type == "payment_method.detached":
                self.logger.info(
                    "Payment method detached: %s, type=%s",
                    payment_method_id,
                    payment_method_type,
                )
                return True
            return False
        except Exception as exc:
            self.logger.error("Error handling payment method webhook: %s", exc)
            return False

    def _handle_fraud_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe Radar fraud warnings and review events for observability."""
        try:
            event_type = event.get("type", "")
            obj = event.get("data", {}).get("object", {})
            obj_id = obj.get("id")

            if event_type == "radar.early_fraud_warning.created":
                self.logger.warning(
                    "Early fraud warning created: %s, charge=%s, fraud_type=%s",
                    obj_id,
                    obj.get("charge"),
                    obj.get("fraud_type"),
                )
                return True
            if event_type == "radar.early_fraud_warning.updated":
                self.logger.warning(
                    "Early fraud warning updated: %s, charge=%s",
                    obj_id,
                    obj.get("charge"),
                )
                return True
            if event_type == "review.opened":
                self.logger.warning(
                    "Payment review opened: %s, charge=%s, reason=%s",
                    obj_id,
                    obj.get("charge"),
                    obj.get("reason"),
                )
                return True
            if event_type == "review.closed":
                self.logger.info(
                    "Payment review closed: %s, charge=%s, reason=%s, closed_reason=%s",
                    obj_id,
                    obj.get("charge"),
                    obj.get("reason"),
                    obj.get("closed_reason"),
                )
                return True
            return False
        except Exception as exc:
            self.logger.error("Error handling fraud/review webhook: %s", exc)
            return False
