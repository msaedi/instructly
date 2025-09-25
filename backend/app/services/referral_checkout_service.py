"""Referral checkout validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.repositories.payment_repository import PaymentRepository
from app.services.base import BaseService
from app.services.wallet_service import WalletService


@dataclass
class OrderState:
    """Minimal checkout context required for referral credits."""

    order_id: str
    user_id: str
    subtotal_cents: int
    has_promo: bool


class ReferralCheckoutError(Exception):
    """Raised when referral checkout validation fails."""

    def __init__(self, reason: str, status_code: int = status.HTTP_409_CONFLICT):
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class ReferralCheckoutService(BaseService):
    """Validate referral credit application at checkout."""

    def __init__(self, db: Session, wallet_service: WalletService):
        super().__init__(db)
        self.payment_repository: PaymentRepository = RepositoryFactory.create_payment_repository(db)
        self.booking_repository: BookingRepository = RepositoryFactory.create_booking_repository(db)
        self.wallet_service = wallet_service

    @BaseService.measure_operation("referrals.checkout.state")
    def get_order_state(self, *, order_id: str, user_id: str) -> OrderState:
        """Return checkout state for the provided order identifier."""

        booking = self._resolve_booking(order_id)
        if not booking:
            raise ReferralCheckoutError("order_not_found", status.HTTP_404_NOT_FOUND)

        owner_id = str(user_id)
        if booking.student_id != owner_id:
            raise ReferralCheckoutError("order_not_owned", status.HTTP_403_FORBIDDEN)

        subtotal_cents = self._decimal_to_cents(booking.total_price)
        has_promo = self._booking_has_promo(booking)

        return OrderState(
            order_id=str(order_id),
            user_id=owner_id,
            subtotal_cents=subtotal_cents,
            has_promo=has_promo,
        )

    @BaseService.measure_operation("referrals.checkout.apply")
    def apply_student_credit(self, *, user_id: str, order_id: str) -> int:
        """Apply referral student credits at checkout."""

        state = self.get_order_state(order_id=order_id, user_id=user_id)

        if state.has_promo:
            raise ReferralCheckoutError("promo_conflict")

        if state.subtotal_cents < settings.referrals_min_basket_cents:
            raise ReferralCheckoutError("below_min_basket")

        txn = self.wallet_service.consume_student_credit(
            user_id=user_id,
            order_id=str(order_id),
            amount_cents=settings.referrals_student_amount_cents,
        )
        if not txn:
            raise ReferralCheckoutError("no_unlocked_credit")

        return int(txn.amount_cents)

    def _resolve_booking(self, order_id: str) -> Optional[Booking]:
        order_id_str = str(order_id)

        payment = self.payment_repository.get_payment_by_intent_id(order_id_str)
        if payment and payment.booking:
            return payment.booking

        payment = self.payment_repository.get_payment_by_booking_id(order_id_str)
        if payment and payment.booking:
            return payment.booking

        return self.booking_repository.get_by_id(order_id_str)

    @staticmethod
    def _booking_has_promo(booking: Booking) -> bool:
        if getattr(booking, "used_credits", None):
            return True
        if getattr(booking, "generated_credits", None):
            return True
        promo_attr = getattr(booking, "promo_code", None)
        if promo_attr:
            return True
        return False

    @staticmethod
    def _decimal_to_cents(amount: Decimal | float | int) -> int:
        if isinstance(amount, Decimal):
            quantized = amount.quantize(Decimal("0.01"))
            return int(quantized * 100)
        if isinstance(amount, (int, float)):
            return int(Decimal(str(amount)).quantize(Decimal("0.01")) * 100)
        raise ValueError("Unsupported amount type for subtotal conversion")


__all__ = ["ReferralCheckoutService", "ReferralCheckoutError", "OrderState"]
