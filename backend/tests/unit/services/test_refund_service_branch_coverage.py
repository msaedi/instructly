from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.schemas.admin_refund import RefundAmount, RefundAmountType, RefundReasonCode
from app.services import refund_service as refund_mod
from app.services.refund_policy_engine import RefundPolicyResult
from app.services.refund_service import RefundService, _ensure_utc, _redact_stripe_id


def _service() -> RefundService:
    service = RefundService.__new__(RefundService)
    service.booking_repo = MagicMock()
    service.payment_repo = MagicMock()
    service.policy_engine = MagicMock()
    service.confirm_service = MagicMock()
    service.idempotency_service = MagicMock()
    service.stripe_service = MagicMock()
    service.credit_service = MagicMock()
    service.audit_service = MagicMock()
    return service


def _token_payload(
    *,
    policy_result: dict[str, object],
    idempotency_key: str = "idem-1",
    reason_code: RefundReasonCode = RefundReasonCode.GOODWILL,
) -> dict[str, object]:
    return {
        "booking_id": "booking-1",
        "reason_code": reason_code.value,
        "amount_cents": 2500,
        "amount_type": RefundAmountType.FULL.value,
        "policy_result": policy_result,
        "idempotency_key": idempotency_key,
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("pi_12345678", "pi_...5678"),
        ("plainvalue", "...alue"),
        ("abc", "abc"),
    ],
)
def test_redact_stripe_id_edge_cases(raw, expected):
    assert _redact_stripe_id(raw) == expected


def test_ensure_utc_handles_naive_and_aware_datetimes():
    naive = datetime(2030, 1, 1, 12, 0, 0)
    converted = _ensure_utc(naive)
    assert converted.tzinfo == timezone.utc

    aware = datetime(2030, 1, 1, 7, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    converted_aware = _ensure_utc(aware)
    assert converted_aware.tzinfo == timezone.utc
    assert converted_aware.hour == 12


def test_preview_refund_raises_for_missing_booking_and_payment():
    service = _service()
    service.booking_repo.get_booking_with_details.return_value = None

    with pytest.raises(NotFoundException) as exc_info:
        service.preview_refund(
            booking_id="missing-booking",
            reason_code=RefundReasonCode.GOODWILL,
            amount=RefundAmount(type=RefundAmountType.FULL),
            note=None,
            actor_id="actor-1",
        )
    assert exc_info.value.code == "BOOKING_NOT_FOUND"

    service.booking_repo.get_booking_with_details.return_value = SimpleNamespace(
        payment_status="authorized",
    )
    service.payment_repo.get_payment_by_booking_id.return_value = None

    with pytest.raises(NotFoundException) as exc_info:
        service.preview_refund(
            booking_id="booking-1",
            reason_code=RefundReasonCode.GOODWILL,
            amount=RefundAmount(type=RefundAmountType.FULL),
            note=None,
            actor_id="actor-1",
        )
    assert exc_info.value.code == "PAYMENT_NOT_FOUND"


def test_preview_refund_adds_credit_policy_warning_for_cancel_policy():
    service = _service()
    booking = SimpleNamespace(payment_status="authorized", auth_attempted_at=None)
    payment = SimpleNamespace(
        amount=10000,
        application_fee=1000,
        status="authorized",
        instructor_payout_cents=None,
    )
    policy = RefundPolicyResult(
        eligible=True,
        method="credit",
        policy_basis="12-24h credit-only",
        student_credit_cents=10000,
        instructor_payout_delta_cents=-9000,
    )
    service.booking_repo.get_booking_with_details.return_value = booking
    service.payment_repo.get_payment_by_booking_id.return_value = payment
    service.policy_engine.evaluate.return_value = policy
    service.confirm_service.generate_token.return_value = (
        "token-1",
        datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    response = service.preview_refund(
        booking_id="booking-1",
        reason_code=RefundReasonCode.CANCEL_POLICY,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note="policy test",
        actor_id="actor-1",
    )

    assert response.eligible is True
    assert any("credit-only" in warning.lower() for warning in response.warnings)


@pytest.mark.asyncio
async def test_execute_refund_guardrail_failures(monkeypatch):
    service = _service()

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(refund_mod.asyncio, "to_thread", _to_thread)

    # Invalid payload shape
    service.confirm_service.decode_token.return_value = {"payload": "bad"}
    with pytest.raises(ValidationException, match="Invalid confirm token payload"):
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )

    # Idempotency check failure surfaces upstream issue.
    payload = _token_payload(policy_result={"eligible": True})
    service.confirm_service.decode_token.return_value = {"payload": payload}
    service.confirm_service.validate_token.return_value = None
    service.idempotency_service.check_and_store = AsyncMock(side_effect=RuntimeError("redis-down"))
    with pytest.raises(RuntimeError, match="redis-down"):
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )

    # In-progress idempotency key should raise conflict.
    service.idempotency_service.check_and_store = AsyncMock(return_value=(True, None))
    with pytest.raises(ConflictException):
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )

    # Invalid policy payload
    bad_policy_payload = _token_payload(policy_result="bad-policy")
    service.confirm_service.decode_token.return_value = {"payload": bad_policy_payload}
    service.idempotency_service.check_and_store = AsyncMock(return_value=(False, None))
    with pytest.raises(ValidationException, match="Invalid policy payload"):
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )

    # Ineligible policy is rejected.
    ineligible_payload = _token_payload(
        policy_result={"eligible": False, "reason": "late", "method": "credit"},
    )
    service.confirm_service.decode_token.return_value = {"payload": ineligible_payload}
    with pytest.raises(ValidationException, match="Refund is no longer eligible"):
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )


@pytest.mark.asyncio
async def test_execute_refund_missing_booking_or_payment(monkeypatch):
    service = _service()

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(refund_mod.asyncio, "to_thread", _to_thread)

    payload = _token_payload(
        policy_result={"eligible": True, "method": "card", "student_card_refund_cents": 2500},
    )
    service.confirm_service.decode_token.return_value = {"payload": payload}
    service.confirm_service.validate_token.return_value = None
    service.idempotency_service.check_and_store = AsyncMock(return_value=(False, None))

    service.booking_repo.get_booking_with_details.return_value = None
    with pytest.raises(NotFoundException) as exc_info:
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )
    assert exc_info.value.code == "BOOKING_NOT_FOUND"

    service.booking_repo.get_booking_with_details.return_value = SimpleNamespace(
        id="booking-1",
        student_id="student-1",
    )
    service.payment_repo.get_payment_by_booking_id.return_value = None
    with pytest.raises(NotFoundException) as exc_info:
        await service.execute_refund(
            confirm_token="token",
            idempotency_key="idem-1",
            actor_id="actor-1",
        )
    assert exc_info.value.code == "PAYMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_execute_refund_card_and_credit_failures_return_failed_response(monkeypatch):
    service = _service()

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(refund_mod.asyncio, "to_thread", _to_thread)

    booking = SimpleNamespace(id="booking-1", student_id="student-1")
    payment = SimpleNamespace(
        stripe_payment_intent_id="pi_12345678",
        amount=10000,
        application_fee=1000,
        status="authorized",
    )
    service.confirm_service.validate_token.return_value = None
    service.booking_repo.get_booking_with_details.return_value = booking
    service.payment_repo.get_payment_by_booking_id.return_value = payment
    service.idempotency_service.check_and_store = AsyncMock(return_value=(False, None))
    service.idempotency_service.store_result = AsyncMock()

    card_payload = _token_payload(
        policy_result={
            "eligible": True,
            "method": "card",
            "policy_basis": "full card",
            "student_card_refund_cents": 2500,
        }
    )
    service.confirm_service.decode_token.return_value = {"payload": card_payload}
    service.stripe_service.refund_payment.side_effect = RuntimeError("stripe-down")
    response = await service.execute_refund(
        confirm_token="token",
        idempotency_key="idem-1",
        actor_id="actor-1",
    )
    assert response.result == "failed"
    assert response.error == "payment_provider_error"
    assert response.refund is None

    credit_payload = _token_payload(
        policy_result={
            "eligible": True,
            "method": "credit",
            "policy_basis": "credit-only",
            "student_credit_cents": 2500,
        }
    )
    service.confirm_service.decode_token.return_value = {"payload": credit_payload}
    service.credit_service.issue_credit.side_effect = RuntimeError("credit-down")
    response = await service.execute_refund(
        confirm_token="token",
        idempotency_key="idem-1",
        actor_id="actor-1",
    )
    assert response.result == "failed"
    assert response.error == "credit_issue_failed"
    assert response.refund is None


def test_resolve_requested_amount_validations():
    service = _service()
    payment = SimpleNamespace(amount=1000)

    with pytest.raises(ValidationException, match="requires amount"):
        service._resolve_requested_amount_cents(
            RefundAmount(type=RefundAmountType.PARTIAL, value=None),
            payment,
        )

    with pytest.raises(ValidationException, match="must be positive"):
        service._resolve_requested_amount_cents(
            RefundAmount(type=RefundAmountType.PARTIAL, value=0),
            payment,
        )

    with pytest.raises(ValidationException, match="cannot exceed"):
        service._resolve_requested_amount_cents(
            RefundAmount(type=RefundAmountType.PARTIAL, value=20),
            payment,
        )


def test_apply_payment_updates_swallow_errors():
    service = _service()
    service.payment_repo.update_payment_status.side_effect = RuntimeError("db-failure")

    # Should not raise; this is a best-effort update.
    service._apply_payment_updates(payment=SimpleNamespace(stripe_payment_intent_id="pi_1"))


def test_refund_service_init_constructs_default_stripe_service():
    db = MagicMock()

    with patch(
        "app.services.refund_service.RepositoryFactory.create_booking_repository",
        return_value=MagicMock(),
    ), patch(
        "app.services.refund_service.RepositoryFactory.create_payment_repository",
        return_value=MagicMock(),
    ), patch(
        "app.services.refund_service.ConfigService"
    ) as config_cls, patch(
        "app.services.refund_service.PricingService"
    ) as pricing_cls, patch(
        "app.services.refund_service.StripeService"
    ) as stripe_cls, patch(
        "app.services.refund_service.MCPConfirmTokenService"
    ), patch(
        "app.services.refund_service.MCPIdempotencyService"
    ), patch(
        "app.services.refund_service.CreditService"
    ), patch(
        "app.services.refund_service.AuditService"
    ):
        _ = RefundService(db)

    stripe_cls.assert_called_once_with(
        db,
        config_service=config_cls.return_value,
        pricing_service=pricing_cls.return_value,
    )
