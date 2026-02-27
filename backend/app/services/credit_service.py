"""Credit reservation lifecycle service (v2.1.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.payment import PlatformCredit
from app.models.user import User
from app.repositories.factory import RepositoryFactory

from .base import BaseService

logger = logging.getLogger(__name__)


class CreditService(BaseService):
    """Manages platform credit reservation, release, forfeit, and issuance."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.credit_repository = RepositoryFactory.create_credit_repository(db)
        self.payment_repository = RepositoryFactory.create_payment_repository(db)

    @BaseService.measure_operation("credit_reserve_for_booking")
    def reserve_credits_for_booking(
        self,
        *,
        user_id: str,
        booking_id: str,
        max_amount_cents: int,
        use_transaction: bool = True,
    ) -> int:
        """Reserve available credits for a booking (FIFO)."""
        if max_amount_cents <= 0:
            return 0

        def _reserve() -> int:
            existing = self.credit_repository.get_reserved_credits_for_booking(
                booking_id=booking_id
            )
            if existing:
                return sum(
                    int(credit.reserved_amount_cents or credit.amount_cents or 0)
                    for credit in existing
                )

            available = self.credit_repository.get_available_credits(
                user_id=user_id,
                order_by="expires_at",
                for_update=True,
            )
            remaining = max_amount_cents
            total_reserved = 0
            reserved_ids: list[str] = []
            reserved_events: list[Dict[str, Any]] = []
            remainder_credit_id: Optional[str] = None
            now = datetime.now(timezone.utc)

            for credit in available:
                if remaining <= 0:
                    break

                original_credit_cents = int(credit.amount_cents or 0)
                reserve_amount = min(original_credit_cents, remaining)
                if reserve_amount <= 0:
                    continue

                # Split credit if only partially reserved.
                local_remainder_id: Optional[str] = None
                if original_credit_cents > reserve_amount:
                    remainder = self.payment_repository.create_platform_credit(
                        user_id=user_id,
                        amount_cents=original_credit_cents - reserve_amount,
                        reason=f"Remainder of {credit.id}",
                        source_type=getattr(credit, "source_type", "manual"),
                        source_booking_id=credit.source_booking_id,
                        expires_at=credit.expires_at,
                        original_expires_at=getattr(credit, "original_expires_at", None)
                        or credit.expires_at,
                        status="available",
                    )
                    remainder_credit_id = remainder.id
                    local_remainder_id = remainder.id
                    credit.amount_cents = reserve_amount

                credit.reserved_amount_cents = reserve_amount
                credit.reserved_for_booking_id = booking_id
                credit.reserved_at = now
                credit.status = "reserved"
                reserved_ids.append(credit.id)

                reserved_events.append(
                    {
                        "booking_id": booking_id,
                        "event_type": "credit_reserved",
                        "event_data": {
                            "credit_id": credit.id,
                            "reserved_cents": reserve_amount,
                            "original_credit_cents": original_credit_cents,
                            "remainder_credit_id": local_remainder_id,
                        },
                    }
                )

                total_reserved += reserve_amount
                remaining -= reserve_amount

            if reserved_events:
                self.payment_repository.bulk_create_payment_events(reserved_events)

            if total_reserved > 0:
                self.payment_repository.create_payment_event(
                    booking_id=booking_id,
                    event_type="credits_applied",
                    event_data={
                        "applied_cents": total_reserved,
                        "requested_cents": max_amount_cents,
                        "used_credit_ids": reserved_ids,
                        "remaining_to_charge_cents": max(max_amount_cents - total_reserved, 0),
                        "remainder_credit_id": remainder_credit_id,
                    },
                )

            return total_reserved

        if use_transaction:
            with self.transaction():
                return _reserve()
        return _reserve()

    @BaseService.measure_operation("credit_release_for_booking")
    def release_credits_for_booking(self, *, booking_id: str, use_transaction: bool = True) -> int:
        """Release reserved credits back to available balance."""

        def _release() -> int:
            reserved = self.credit_repository.get_reserved_credits_for_booking(
                booking_id=booking_id
            )
            if not reserved:
                return 0

            now = datetime.now(timezone.utc)
            total_released = 0
            for credit in reserved:
                released_amount = int(credit.reserved_amount_cents or credit.amount_cents or 0)
                if released_amount <= 0:
                    continue

                credit.reserved_amount_cents = 0
                credit.reserved_for_booking_id = None
                credit.reserved_at = None
                if credit.expires_at and credit.expires_at <= now:
                    credit.status = "expired"
                else:
                    credit.status = "available"
                total_released += released_amount

            if total_released > 0:
                self.payment_repository.create_payment_event(
                    booking_id=booking_id,
                    event_type="credits_released",
                    event_data={"released_cents": total_released},
                )

            return total_released

        if use_transaction:
            with self.transaction():
                return _release()
        return _release()

    @BaseService.measure_operation("credit_forfeit_for_booking")
    def forfeit_credits_for_booking(self, *, booking_id: str, use_transaction: bool = True) -> int:
        """Forfeit reserved credits (credits are spent or lost)."""

        def _forfeit() -> int:
            reserved = self.credit_repository.get_reserved_credits_for_booking(
                booking_id=booking_id
            )
            if not reserved:
                return 0

            now = datetime.now(timezone.utc)
            total_forfeited = 0
            for credit in reserved:
                forfeited_amount = int(credit.reserved_amount_cents or credit.amount_cents or 0)
                if forfeited_amount <= 0:
                    continue
                credit.reserved_amount_cents = 0
                credit.status = "forfeited"
                credit.forfeited_at = now
                credit.used_at = now
                credit.used_booking_id = booking_id
                total_forfeited += forfeited_amount

            if total_forfeited > 0:
                self.payment_repository.create_payment_event(
                    booking_id=booking_id,
                    event_type="credits_forfeited",
                    event_data={"forfeited_cents": total_forfeited},
                )

            return total_forfeited

        if use_transaction:
            with self.transaction():
                return _forfeit()
        return _forfeit()

    @BaseService.measure_operation("credit_issue")
    def issue_credit(
        self,
        *,
        user_id: str,
        amount_cents: int,
        source_type: str,
        reason: Optional[str] = None,
        source_booking_id: Optional[str] = None,
        expires_in_days: int = 365,
        use_transaction: bool = True,
    ) -> Optional[PlatformCredit]:
        """Issue a new platform credit with fresh expiration."""
        if amount_cents <= 0:
            return None

        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        def _issue() -> PlatformCredit:
            return self.payment_repository.create_platform_credit(
                user_id=user_id,
                amount_cents=amount_cents,
                reason=reason or source_type,
                source_type=source_type,
                source_booking_id=source_booking_id,
                expires_at=expires_at,
                status="available",
            )

        if use_transaction:
            with self.transaction():
                return _issue()
        return _issue()

    @BaseService.measure_operation("credit_freeze_for_booking")
    def freeze_credits_for_booking(
        self,
        *,
        booking_id: str,
        reason: str,
        use_transaction: bool = True,
    ) -> int:
        """Freeze credits issued from a booking (dispute handling)."""

        def _freeze() -> int:
            credits = self.credit_repository.get_credits_for_source_booking(
                booking_id=booking_id,
                statuses=["available", "reserved"],
            )
            if not credits:
                return 0
            now = datetime.now(timezone.utc)
            for credit in credits:
                credit.status = "frozen"
                credit.frozen_at = now
                credit.frozen_reason = reason
            return len(credits)

        if use_transaction:
            with self.transaction():
                return _freeze()
        return _freeze()

    @BaseService.measure_operation("credit_revoke_for_booking")
    def revoke_credits_for_booking(
        self,
        *,
        booking_id: str,
        reason: str,
        use_transaction: bool = True,
    ) -> int:
        """Revoke credits issued from a booking (dispute lost)."""

        def _revoke() -> int:
            credits = self.credit_repository.get_credits_for_source_booking(booking_id=booking_id)
            if not credits:
                return 0
            now = datetime.now(timezone.utc)
            revoked_count = 0
            for credit in credits:
                if getattr(credit, "status", None) == "revoked":
                    continue
                credit.status = "revoked"
                credit.revoked = True
                credit.revoked_at = now
                credit.revoked_reason = reason
                revoked_count += 1
            return revoked_count

        if use_transaction:
            with self.transaction():
                return _revoke()
        return _revoke()

    @BaseService.measure_operation("credit_unfreeze_for_booking")
    def unfreeze_credits_for_booking(
        self,
        *,
        booking_id: str,
        use_transaction: bool = True,
    ) -> int:
        """Unfreeze credits issued from a booking after dispute resolution."""

        def _unfreeze() -> int:
            credits = self.credit_repository.get_credits_for_source_booking(
                booking_id=booking_id,
                statuses=["frozen"],
            )
            if not credits:
                return 0
            now = datetime.now(timezone.utc)
            for credit in credits:
                credit.frozen_at = None
                credit.frozen_reason = None
                if credit.reserved_for_booking_id or (credit.reserved_amount_cents or 0) > 0:
                    credit.status = "reserved"
                elif credit.expires_at and credit.expires_at <= now:
                    credit.status = "expired"
                else:
                    credit.status = "available"
            return len(credits)

        if use_transaction:
            with self.transaction():
                return _unfreeze()
        return _unfreeze()

    @BaseService.measure_operation("credit_spent_for_booking")
    def get_spent_credits_for_booking(self, *, booking_id: str) -> int:
        """Return total spent credits issued from a booking."""
        try:
            credits = self.credit_repository.get_credits_for_source_booking(booking_id=booking_id)
        except Exception:
            return 0

        spent_total = 0
        for credit in credits:
            status = getattr(credit, "status", None)
            if getattr(credit, "used_at", None) is not None:
                spent_total += int(getattr(credit, "amount_cents", 0) or 0)
                continue
            if getattr(credit, "used_booking_id", None):
                spent_total += int(getattr(credit, "amount_cents", 0) or 0)
                continue
            if status in {"forfeited", "expired"}:
                spent_total += int(getattr(credit, "amount_cents", 0) or 0)
        return spent_total

    @BaseService.measure_operation("credit_negative_balance_apply")
    def apply_negative_balance(
        self,
        *,
        user_id: str,
        amount_cents: int,
        reason: str,
        use_transaction: bool = True,
    ) -> None:
        """Apply a negative credit balance to a user."""
        if amount_cents <= 0:
            return

        def _apply() -> None:
            user_repo = RepositoryFactory.create_base_repository(self.db, User)
            user = user_repo.get_by_id(user_id)
            if not user:
                return
            current = int(getattr(user, "credit_balance_cents", 0) or 0)
            user.credit_balance_cents = current - amount_cents
            if user.credit_balance_cents < 0:
                user.account_restricted = True
                user.account_restricted_at = datetime.now(timezone.utc)
                user.account_restricted_reason = reason

        if use_transaction:
            with self.transaction():
                _apply()
            return
        _apply()

    @BaseService.measure_operation("credit_negative_balance_clear")
    def clear_negative_balance(
        self,
        *,
        user_id: str,
        amount_cents: int,
        reason: str,
        use_transaction: bool = True,
    ) -> None:
        """Clear (or reduce) a negative balance after dispute resolution."""
        if amount_cents <= 0:
            return

        def _clear() -> None:
            user_repo = RepositoryFactory.create_base_repository(self.db, User)
            user = user_repo.get_by_id(user_id)
            if not user:
                return
            current = int(getattr(user, "credit_balance_cents", 0) or 0)
            user.credit_balance_cents = current + amount_cents
            if user.credit_balance_cents >= 0:
                user.account_restricted = False
                user.account_restricted_at = None
                if getattr(user, "account_restricted_reason", ""):
                    user.account_restricted_reason = None

        if use_transaction:
            with self.transaction():
                _clear()
            return
        _clear()

    @BaseService.measure_operation("credit_balance_available")
    def get_available_balance(self, *, user_id: str) -> int:
        """Return available credit balance in cents."""
        return self.credit_repository.get_total_available_credits(user_id=user_id)

    @BaseService.measure_operation("credit_balance_reserved")
    def get_reserved_balance(self, *, user_id: str) -> int:
        """Return reserved credit balance in cents."""
        return self.credit_repository.get_total_reserved_credits(user_id=user_id)

    @BaseService.measure_operation("credit_balance_summary")
    def get_credit_summary(self, *, user_id: str) -> Dict[str, int]:
        """Return available/reserved/total credit summary in cents."""
        available = self.get_available_balance(user_id=user_id)
        reserved = self.get_reserved_balance(user_id=user_id)
        return {
            "available_cents": available,
            "reserved_cents": reserved,
            "total_cents": available + reserved,
        }

    @BaseService.measure_operation("credit_card_charge_amount")
    def get_card_charge_amount(
        self,
        *,
        lesson_price_cents: int,
        student_fee_cents: int,
        reserved_credits_cents: int,
    ) -> int:
        """
        Calculate card charge amount.
        Card = student fee + (lesson price - reserved credits).
        Credits never cover the student fee.
        """
        lp_after_credits = max(0, int(lesson_price_cents) - int(reserved_credits_cents))
        return int(student_fee_cents) + lp_after_credits

    @BaseService.measure_operation("credit_expire_old")
    def expire_old_credits(self, *, use_transaction: bool = True) -> int:
        """Mark expired credits (skip reserved credits). Returns count expired."""

        def _expire() -> int:
            now = datetime.now(timezone.utc)
            expired = self.credit_repository.get_expired_available_credits(as_of=now)
            for credit in expired:
                credit.status = "expired"
            return len(expired)

        if use_transaction:
            with self.transaction():
                return _expire()
        return _expire()


__all__ = ["CreditService"]
