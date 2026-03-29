from __future__ import annotations

from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any, Optional, cast

import stripe

from ...core.exceptions import ServiceException
from ...models.user import User
from ...schemas.payment_schemas import (
    DashboardLinkResponse,
    InstantPayoutResponse,
    PayoutScheduleResponse,
)
from ..base import BaseService
from .helpers import ReferralBonusTransferResult

if TYPE_CHECKING:
    from ...repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


class StripeTransferMixin(BaseService):
    """Transfers, payouts, top-ups, and referral bonuses."""

    payment_repository: PaymentRepository

    if TYPE_CHECKING:

        def _call_with_retry(self, func: Any, *args: Any, **kwargs: Any) -> Any:
            ...

        def _require_connected_account_record(self, profile_id: str) -> Any:
            ...

        def _require_instructor_profile(self, user: User) -> Any:
            ...

    @BaseService.measure_operation("stripe_set_payout_schedule")
    def set_instructor_payout_schedule(
        self, *, user: User, monthly_anchor: int | None, interval: str
    ) -> PayoutScheduleResponse:
        """Update payout schedule for instructor connected account."""
        stripe_sdk = _stripe_service_module().stripe
        profile = self._require_instructor_profile(user)
        connected = self._require_connected_account_record(profile.id)
        schedule_settings: dict[str, object] = {"interval": interval}
        if monthly_anchor:
            schedule_settings["monthly_anchor"] = monthly_anchor
        account = stripe_sdk.Account.modify(
            connected.stripe_account_id,
            settings={"payouts": {"schedule": schedule_settings}},
        )
        account_id = (
            account.get("id") if isinstance(account, dict) else getattr(account, "id", None)
        )
        return PayoutScheduleResponse(
            ok=True,
            account_id=account_id,
            settings={"interval": interval, "monthly_anchor": monthly_anchor},
        )

    @BaseService.measure_operation("stripe_dashboard_link")
    def get_instructor_dashboard_link(self, *, user: User) -> DashboardLinkResponse:
        """Generate Stripe dashboard link for instructor."""
        stripe_sdk = _stripe_service_module().stripe
        profile = self._require_instructor_profile(user)
        connected = self._require_connected_account_record(profile.id)
        link = stripe_sdk.Account.create_login_link(connected.stripe_account_id)
        dashboard_url = link.get("url") if isinstance(link, dict) else getattr(link, "url", None)
        return DashboardLinkResponse(dashboard_url=dashboard_url or "", expires_in_minutes=5)

    @BaseService.measure_operation("stripe_request_instant_payout")
    def request_instructor_instant_payout(self, *, user: User) -> InstantPayoutResponse:
        """Request an instant payout for an instructor's full available balance."""
        facade_module = _stripe_service_module()
        profile = self._require_instructor_profile(user)
        connected = self._require_connected_account_record(profile.id)

        balance = facade_module.StripeBalance.retrieve(stripe_account=connected.stripe_account_id)
        available_amount = balance.available[0].amount if balance.available else 0
        if available_amount <= 0:
            raise ServiceException("No funds available for instant payout", code="no_funds")
        payout_key = f"payout_{connected.stripe_account_id}_{facade_module.uuid.uuid4()}"
        payout = self._call_with_retry(
            facade_module.stripe.Payout.create,
            amount=available_amount,
            currency="usd",
            stripe_account=connected.stripe_account_id,
            method="instant",
            idempotency_key=payout_key,
        )
        payout_id = (
            getattr(payout, "id", None) if not isinstance(payout, dict) else payout.get("id")
        )
        payout_status = (
            getattr(payout, "status", None)
            if not isinstance(payout, dict)
            else payout.get("status")
        )
        return InstantPayoutResponse(ok=True, payout_id=payout_id, status=payout_status)

    @BaseService.measure_operation("stripe_ensure_top_up_transfer")
    def ensure_top_up_transfer(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        destination_account_id: str,
        amount_cents: int,
    ) -> Optional[dict[str, Any]]:
        """Create a one-time top-up transfer when credits exceed platform share."""
        if amount_cents <= 0:
            return None

        try:
            existing_event = self.payment_repository.get_latest_payment_event(
                booking_id,
                "top_up_transfer_created",
            )
            if existing_event:
                data = existing_event.event_data or {}
                if data.get("payment_intent_id") == payment_intent_id and int(
                    data.get("amount_cents") or 0
                ) == int(amount_cents):
                    return None

            transfer = _stripe_service_module().StripeTransfer.create(
                amount=amount_cents,
                currency="usd",
                destination=destination_account_id,
                transfer_group=f"booking:{booking_id}",
                metadata={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                },
                idempotency_key=f"topup:{payment_intent_id}",
            )
            try:
                self.payment_repository.create_payment_event(
                    booking_id=booking_id,
                    event_type="top_up_transfer_created",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "transfer_id": getattr(transfer, "id", None),
                        "amount_cents": int(amount_cents),
                    },
                )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            self.logger.info(
                "Issued top-up transfer",
                extra={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                    "amount_cents": amount_cents,
                    "destination_account_id": destination_account_id,
                },
            )
            return cast(Optional[dict[str, Any]], transfer)
        except stripe.StripeError as exc:  # pragma: no cover - network path
            self.logger.error(
                "Stripe error creating top-up transfer for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise ServiceException("Failed to create top-up transfer") from exc

    @BaseService.measure_operation("stripe_create_manual_transfer")
    def create_manual_transfer(
        self,
        *,
        booking_id: str,
        destination_account_id: str,
        amount_cents: int,
        idempotency_key: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a manual transfer to a connected account."""
        if amount_cents <= 0:
            return {"skipped": True, "transfer_id": None}

        transfer_metadata = {"booking_id": booking_id}
        if metadata:
            transfer_metadata.update(metadata)

        try:
            transfer = _stripe_service_module().StripeTransfer.create(
                amount=amount_cents,
                currency="usd",
                destination=destination_account_id,
                transfer_group=f"booking:{booking_id}",
                metadata=transfer_metadata,
                idempotency_key=idempotency_key,
            )
            transfer_id = (
                transfer.get("id") if isinstance(transfer, dict) else getattr(transfer, "id", None)
            )
            return {"transfer": transfer, "transfer_id": transfer_id, "amount": amount_cents}
        except stripe.StripeError as exc:  # pragma: no cover - network path
            self.logger.error(
                "Stripe error creating transfer for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise ServiceException("Failed to create transfer") from exc
        except Exception as exc:
            self.logger.error(
                "Unexpected error creating transfer for booking %s: %s",
                booking_id,
                str(exc),
            )
            raise ServiceException("Failed to create transfer") from exc

    @BaseService.measure_operation("stripe_create_referral_bonus_transfer")
    def create_referral_bonus_transfer(
        self,
        *,
        payout_id: str,
        destination_account_id: str,
        amount_cents: int,
        referrer_user_id: str,
        referred_user_id: str,
        referral_type: str,
        was_founding_bonus: bool,
    ) -> ReferralBonusTransferResult:
        """Create a Stripe Transfer for instructor referral bonuses."""
        if amount_cents <= 0:
            return {
                "status": "skipped",
                "reason": "zero_amount",
                "transfer_id": None,
                "amount_cents": 0,
            }

        idempotency_key = f"instructor_referral_bonus_{payout_id}"
        if referral_type == "student":
            description = "Student referral bonus - $20"
        else:
            description = (
                "Instructor referral bonus - Founding $75"
                if was_founding_bonus
                else "Instructor referral bonus - Standard $50"
            )

        metadata = {
            "type": f"{referral_type}_referral_bonus",
            "payout_id": payout_id,
            "referrer_user_id": referrer_user_id,
            "referred_user_id": referred_user_id,
            "referral_type": referral_type,
            "was_founding_bonus": str(was_founding_bonus).lower(),
            "amount_dollars": str(amount_cents / 100),
        }
        try:
            transfer = _stripe_service_module().StripeTransfer.create(
                amount=amount_cents,
                currency="usd",
                destination=destination_account_id,
                description=description,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
            transfer_id = (
                transfer.get("id") if isinstance(transfer, dict) else getattr(transfer, "id", None)
            )
            if not transfer_id:
                raise ServiceException("Failed to create referral bonus transfer")
            self.logger.info(
                "Created referral bonus transfer",
                extra={
                    "payout_id": payout_id,
                    "transfer_id": transfer_id,
                    "amount_cents": amount_cents,
                    "destination_account_id": destination_account_id,
                },
            )
            return {
                "status": "success",
                "transfer_id": str(transfer_id),
                "amount_cents": amount_cents,
            }
        except stripe.StripeError as exc:  # pragma: no cover - network path
            self.logger.error(
                "Stripe error creating referral bonus transfer for payout %s: %s",
                payout_id,
                str(exc),
            )
            raise ServiceException("Failed to create referral bonus transfer") from exc
        except Exception as exc:
            self.logger.error(
                "Unexpected error creating referral bonus transfer for payout %s: %s",
                payout_id,
                str(exc),
            )
            raise ServiceException("Failed to create referral bonus transfer") from exc

    @BaseService.measure_operation("stripe_set_payout_schedule")
    def set_payout_schedule_for_account(
        self,
        *,
        instructor_profile_id: str,
        interval: str = "weekly",
        weekly_anchor: str = "tuesday",
    ) -> dict[str, Any]:
        """Set the payout schedule for a connected account (Express)."""
        try:
            account = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account:
                raise ServiceException("Connected account not found for instructor")

            updated = _stripe_service_module().stripe.Account.modify(
                account.stripe_account_id,
                settings={
                    "payouts": {
                        "schedule": {
                            "interval": interval,
                            "weekly_anchor": weekly_anchor,
                        }
                    }
                },
            )
            self.logger.info(
                "Updated payout schedule for %s: interval=%s, anchor=%s",
                account.stripe_account_id,
                interval,
                weekly_anchor,
            )
            try:
                settings_obj = getattr(updated, "settings", {})
            except Exception:
                settings_obj = {}
            return {"account_id": account.stripe_account_id, "settings": settings_obj}
        except stripe.StripeError as exc:
            self.logger.error("Stripe error setting payout schedule: %s", exc)
            raise ServiceException(f"Failed to set payout schedule: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error setting payout schedule: %s", exc)
            raise ServiceException(f"Failed to set payout schedule: {str(exc)}")

    @staticmethod
    def _top_up_from_pi_metadata(pi: Any) -> Optional[int]:
        """Compute top-up from PaymentIntent metadata when available."""
        metadata = getattr(pi, "metadata", None)
        if not metadata and hasattr(pi, "get"):
            metadata = pi.get("metadata")
        if not metadata:
            return None

        try:
            base_price_cents = int(str(metadata["base_price_cents"]))
            platform_fee_cents = int(str(metadata["platform_fee_cents"]))
            _ = int(str(metadata["student_fee_cents"]))
            applied_credit_cents = int(str(metadata["applied_credit_cents"]))
        except (KeyError, TypeError, ValueError):
            return None

        if applied_credit_cents < 0:
            return None

        amount_value: Optional[Any] = getattr(pi, "amount", None)
        if amount_value is None and hasattr(pi, "get"):
            amount_value = pi.get("amount")
        if amount_value is None:
            return None

        try:
            student_pay_cents = int(str(amount_value))
        except (TypeError, ValueError):
            return None

        target_instructor_payout = base_price_cents - platform_fee_cents
        top_up = target_instructor_payout - student_pay_cents
        return 0 if top_up <= 0 else top_up
