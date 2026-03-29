from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Optional

from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...repositories.payment_repository import PaymentRepository
from ..base import BaseService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ParsedPayoutEvent:
    event_type: str
    payout_id: Optional[str]
    amount: Any
    status: Any
    arrival_date: Optional[datetime]
    account_id: Optional[str]
    failure_code: Any
    failure_message: Any


class StripeWebhookPayoutsMixin(BaseService):
    """Stripe payout webhook processing and instructor payout notifications."""

    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository

    def _parse_payout_event(self, event: dict[str, Any]) -> _ParsedPayoutEvent:
        payout = event.get("data", {}).get("object", {})
        arrival_raw = payout.get("arrival_date")
        arrival_date: Optional[datetime] = None
        if isinstance(arrival_raw, datetime):
            arrival_date = (
                arrival_raw.replace(tzinfo=timezone.utc)
                if arrival_raw.tzinfo is None
                else arrival_raw
            )
        elif isinstance(arrival_raw, (int, float)):
            arrival_date = datetime.fromtimestamp(arrival_raw, tz=timezone.utc)
        elif isinstance(arrival_raw, str):
            try:
                parsed = datetime.fromisoformat(arrival_raw)
                arrival_date = (
                    parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
                )
            except ValueError:
                arrival_date = None
        return _ParsedPayoutEvent(
            event_type=event.get("type", ""),
            payout_id=payout.get("id"),
            amount=payout.get("amount"),
            status=payout.get("status"),
            arrival_date=arrival_date,
            account_id=payout.get("destination") or payout.get("stripe_account"),
            failure_code=payout.get("failure_code"),
            failure_message=payout.get("failure_message"),
        )

    def _record_payout_analytics(
        self,
        *,
        parsed: _ParsedPayoutEvent,
        status: Any,
        failure_code: Any = None,
        failure_message: Any = None,
    ) -> Optional[Any]:
        if not parsed.account_id or not parsed.payout_id:
            return None
        account = self.payment_repository.get_connected_account_by_stripe_id(parsed.account_id)
        if not account or not account.instructor_profile_id:
            return None
        self.payment_repository.record_payout_event(
            instructor_profile_id=account.instructor_profile_id,
            stripe_account_id=parsed.account_id,
            payout_id=parsed.payout_id,
            amount_cents=parsed.amount,
            status=status,
            arrival_date=parsed.arrival_date,
            failure_code=failure_code,
            failure_message=failure_message,
        )
        return account

    def _notify_paid_payout(self, *, account: Any, parsed: _ParsedPayoutEvent) -> None:
        if not account or not account.instructor_profile_id or parsed.amount is None:
            return
        profile = self.instructor_repository.get_by_id_join_user(account.instructor_profile_id)
        if not profile or not profile.user_id:
            return

        from app.services.notification_service import NotificationService

        notification_service = NotificationService(self.db)
        notification_service.send_payout_notification(
            instructor_id=profile.user_id,
            amount_cents=int(parsed.amount),
            payout_date=parsed.arrival_date or datetime.now(timezone.utc),
        )

    def _handle_payout_webhook(self, event: dict[str, Any]) -> bool:
        """Handle Stripe payout events for connected accounts."""
        try:
            parsed = self._parse_payout_event(event)
            if parsed.event_type == "payout.created":
                self.logger.info(
                    "Payout created: %s amount=%s status=%s arrival=%s",
                    parsed.payout_id,
                    parsed.amount,
                    parsed.status,
                    parsed.arrival_date,
                )
                try:
                    self._record_payout_analytics(parsed=parsed, status=parsed.status)
                except Exception as exc:
                    self.logger.warning("Failed to persist payout.created analytics: %s", exc)
                return True

            if parsed.event_type == "payout.paid":
                self.logger.info(
                    "Payout paid: %s amount=%s status=%s arrival=%s",
                    parsed.payout_id,
                    parsed.amount,
                    parsed.status,
                    parsed.arrival_date,
                )
                try:
                    account = self._record_payout_analytics(parsed=parsed, status=parsed.status)
                    try:
                        self._notify_paid_payout(account=account, parsed=parsed)
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to send payout notification for account %s: %s",
                            parsed.account_id,
                            exc,
                        )
                except Exception as exc:
                    self.logger.warning("Failed to persist payout.paid analytics: %s", exc)
                return True

            if parsed.event_type == "payout.failed":
                self.logger.error(
                    "Payout failed: %s amount=%s code=%s message=%s",
                    parsed.payout_id,
                    parsed.amount,
                    parsed.failure_code,
                    parsed.failure_message,
                )
                try:
                    self._record_payout_analytics(
                        parsed=parsed,
                        status="failed",
                        failure_code=parsed.failure_code,
                        failure_message=parsed.failure_message,
                    )
                except Exception as exc:
                    self.logger.warning("Failed to persist payout.failed analytics: %s", exc)
                return True

            return False
        except Exception as exc:
            self.logger.error("Error handling payout webhook: %s", exc)
            return False
