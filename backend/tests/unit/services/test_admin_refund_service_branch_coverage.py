from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.admin_refunds import AdminRefundReason
import app.services.admin_refund_service as admin_refund_module
from app.services.admin_refund_service import AdminRefundService


class _DummyPaymentDetail:
    def __init__(
        self,
        *,
        payment_intent_id: str | None = "pi_1",
        payment_status: str = "captured",
        settlement_outcome: str | None = None,
        instructor_payout_amount: int = 0,
        credits_reserved_cents: int = 250,
    ) -> None:
        self.payment_intent_id = payment_intent_id
        self.payment_status = payment_status
        self.settlement_outcome = settlement_outcome
        self.instructor_payout_amount = instructor_payout_amount
        self.credits_reserved_cents = credits_reserved_cents


class _DummyBooking:
    def __init__(
        self,
        *,
        booking_id: str = "booking_1",
        payment_intent_id: str | None = "pi_1",
        total_price: object | None = "12.50",
        cancelled_at: datetime | None = None,
    ) -> None:
        self.id = booking_id
        self.total_price = total_price
        self.status = "CONFIRMED"
        self.cancelled_at = cancelled_at
        self.instructor_id = "inst_1"
        self.refunded_to_card_amount = 0
        self.student_credit_amount = 0
        self.payment_detail = _DummyPaymentDetail(payment_intent_id=payment_intent_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "payment_status": self.payment_detail.payment_status,
            "status": self.status,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "refunded_to_card_amount": self.refunded_to_card_amount,
        }


def _make_service() -> AdminRefundService:
    service = AdminRefundService.__new__(AdminRefundService)
    service.db = MagicMock()
    service.logger = MagicMock()
    service.booking_repo = MagicMock()
    service.payment_repo = MagicMock()
    service.audit_repo = MagicMock()
    return service


def test_resolve_full_refund_cents_prefers_payment_record_amount() -> None:
    service = _make_service()
    booking = _DummyBooking(payment_intent_id="pi_exists", total_price="99.99")
    service.payment_repo.get_payment_by_intent_id.return_value = SimpleNamespace(amount=4312)

    result = service.resolve_full_refund_cents(booking)

    assert result == 4312


def test_resolve_full_refund_cents_returns_zero_without_payment_or_total_price() -> None:
    service = _make_service()
    booking = _DummyBooking(payment_intent_id="pi_missing", total_price=None)
    service.payment_repo.get_payment_by_intent_id.return_value = None

    result = service.resolve_full_refund_cents(booking)

    assert result == 0


def test_apply_refund_updates_returns_none_when_booking_disappears() -> None:
    service = _make_service()
    service.booking_repo.get_booking_with_details.return_value = None

    result = service.apply_refund_updates(
        booking_id="booking_missing",
        reason=AdminRefundReason.OTHER,
        note=None,
        amount_cents=100,
        stripe_reason="requested_by_customer",
        refund_id="re_1",
        actor=SimpleNamespace(id="admin_1"),
    )

    assert result is None


def test_apply_refund_updates_handles_non_fatal_credit_and_audit_errors(monkeypatch) -> None:
    service = _make_service()
    booking = _DummyBooking()
    service.booking_repo.get_booking_with_details.return_value = booking
    service.booking_repo.ensure_payment.return_value = booking.payment_detail
    actor = SimpleNamespace(id="admin_2")

    monkeypatch.setattr(admin_refund_module, "AUDIT_ENABLED", True)

    with patch("app.services.credit_service.CreditService") as credit_cls:
        with patch.object(admin_refund_module, "AuditService") as audit_service_cls:
            with patch.object(admin_refund_module, "logger") as logger_mock:
                credit_cls.return_value.release_credits_for_booking.side_effect = RuntimeError(
                    "credits unavailable"
                )
                audit_service_cls.return_value.log_changes.side_effect = RuntimeError(
                    "audit unavailable"
                )

                result = service.apply_refund_updates(
                    booking_id=booking.id,
                    reason=AdminRefundReason.DISPUTE,
                    note="manual correction",
                    amount_cents=1250,
                    stripe_reason="requested_by_customer",
                    refund_id="re_2",
                    actor=actor,
                )

    assert result is booking
    assert booking.payment_detail.payment_status == "settled"
    assert booking.status == "CANCELLED"
    assert booking.refunded_to_card_amount == 1250
    assert booking.payment_detail.credits_reserved_cents == 250
    service.audit_repo.write.assert_called_once()
    logger_mock.warning.assert_called_once()
    logger_mock.debug.assert_called_once()


def test_apply_refund_updates_skips_audit_when_disabled(monkeypatch) -> None:
    service = _make_service()
    booking = _DummyBooking(cancelled_at=datetime.now(timezone.utc))
    service.booking_repo.get_booking_with_details.return_value = booking
    service.booking_repo.ensure_payment.return_value = booking.payment_detail

    monkeypatch.setattr(admin_refund_module, "AUDIT_ENABLED", False)

    result = service.apply_refund_updates(
        booking_id=booking.id,
        reason=AdminRefundReason.OTHER,
        note=None,
        amount_cents=2000,
        stripe_reason="requested_by_customer",
        refund_id="re_3",
        actor=SimpleNamespace(id="admin_3"),
    )

    assert result is booking
    service.audit_repo.write.assert_not_called()
