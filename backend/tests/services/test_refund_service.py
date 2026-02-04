from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.exceptions import MCPTokenError, ValidationException
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent
from app.models.service_catalog import InstructorService
from app.schemas.admin_refund import RefundAmount, RefundAmountType, RefundReasonCode
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.refund_service import RefundService

try:  # pragma: no cover - support running from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


class DummyRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        return True


class FakeStripeService:
    def __init__(self, result: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result or {"status": "succeeded", "refund_id": "re_123"}

    def refund_payment(self, payment_intent_id: str, *, amount_cents: int, reason: str, idempotency_key: str):
        self.calls.append(
            {
                "payment_intent_id": payment_intent_id,
                "amount_cents": amount_cents,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return self.result


class FakeCreditService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def issue_credit(self, **kwargs):
        self.calls.append(kwargs)


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log(self, **kwargs):
        self.calls.append(kwargs)
        return "audit_123"


def _get_active_service_id(db, instructor_id: str) -> str:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise RuntimeError("Instructor profile not found for refund service test")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if not service:
        raise RuntimeError("Active service not found for refund service test")
    return service.id


def _create_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    status: BookingStatus,
    offset_index: int,
) -> Booking:
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test Lesson",
        hourly_rate=100,
        total_price=100,
        duration_minutes=60,
        status=status,
        offset_index=offset_index,
    )
    db.flush()
    return booking


def _set_booking_start(booking: Booking, start_at: datetime) -> None:
    booking.booking_start_utc = start_at
    booking.booking_end_utc = start_at + timedelta(minutes=int(booking.duration_minutes or 60))


def _attach_payment(
    db,
    booking: Booking,
    *,
    payment_status: str = PaymentStatus.AUTHORIZED.value,
    amount_cents: int = 10000,
    application_fee_cents: int = 1000,
) -> PaymentIntent:
    payment_intent_id = f"pi_{generate_ulid()}"
    booking.payment_intent_id = payment_intent_id
    booking.payment_status = payment_status
    payment_intent_status = "succeeded" if payment_status == PaymentStatus.SETTLED.value else "requires_capture"

    payment = PaymentIntent(
        booking_id=booking.id,
        stripe_payment_intent_id=payment_intent_id,
        amount=amount_cents,
        application_fee=application_fee_cents,
        status=payment_intent_status,
    )
    db.add(payment)
    db.flush()
    return payment


def _build_service(db):
    redis = DummyRedis()
    stripe_service = FakeStripeService()
    credit_service = FakeCreditService()
    audit_service = FakeAuditService()
    confirm_service = MCPConfirmTokenService(db)
    idempotency_service = MCPIdempotencyService(db, redis_client=redis)
    service = RefundService(
        db,
        confirm_service=confirm_service,
        idempotency_service=idempotency_service,
        stripe_service=stripe_service,
        credit_service=credit_service,
        audit_service=audit_service,
    )
    return service, stripe_service, credit_service, audit_service


def test_refund_preview_eligible_24h_before_card_refund(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=0,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.CANCEL_POLICY,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.eligible is True
    assert response.impact.refund_method == "card"
    assert response.impact.student_card_refund == 100.0
    assert response.impact.student_credit_issued == 0.0
    assert response.policy_basis.startswith(">=24 hours")


def test_refund_preview_12_to_24h_credit_only(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=1,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=18))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.eligible is True
    assert response.impact.refund_method == "credit"
    assert response.impact.student_card_refund == 0.0
    assert response.impact.student_credit_issued == 100.0


def test_refund_preview_under_12h_50_percent_credit(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=2,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=6))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.eligible is True
    assert response.impact.refund_method == "credit"
    assert response.impact.student_credit_issued == 50.0


def test_refund_preview_completed_lesson_ineligible(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.COMPLETED,
        offset_index=3,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.CANCEL_POLICY,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.eligible is False
    assert response.confirm_token is None
    assert response.idempotency_key is None


def test_refund_preview_duplicate_charge_always_card(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=4,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=2))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.DUPLICATE,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.impact.refund_method == "card"


def test_refund_preview_instructor_no_show_always_card(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=5,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=1))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.INSTRUCTOR_NO_SHOW,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.impact.refund_method == "card"


def test_refund_preview_returns_tokens_when_eligible(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=6,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note="note",
        actor_id="actor",
    )

    assert response.confirm_token
    assert response.idempotency_key
    assert response.token_expires_at is not None


def test_refund_preview_no_tokens_when_ineligible(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.COMPLETED,
        offset_index=7,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.CANCEL_POLICY,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.confirm_token is None
    assert response.idempotency_key is None


@pytest.mark.asyncio
async def test_refund_execute_invalid_token_fails(db):
    service, _, _, _ = _build_service(db)

    with pytest.raises(MCPTokenError):
        await service.execute_refund(
            confirm_token="bad_token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_refund_execute_expired_token_fails(db):
    service, _, _, _ = _build_service(db)
    confirm_service = MCPConfirmTokenService(db)
    payload = {
        "booking_id": "01BOOK",
        "reason_code": RefundReasonCode.GOODWILL.value,
        "amount_cents": 1000,
        "amount_type": RefundAmountType.FULL.value,
        "policy_result": {"eligible": True},
        "idempotency_key": "idem",
    }
    payload_hash = confirm_service._hash_payload(payload)
    expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    signature = confirm_service._sign(payload_hash, "actor", expires_at)
    token_payload = {
        "payload_hash": payload_hash,
        "actor_id": "actor",
        "expires_at": expires_at.isoformat(),
        "signature": signature,
        "payload": payload,
    }
    token = confirm_service._b64encode(token_payload)

    with pytest.raises(MCPTokenError):
        await service.execute_refund(
            confirm_token=token,
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_refund_execute_idempotency_mismatch_fails(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=8,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    preview = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    with pytest.raises(ValidationException, match="Idempotency key mismatch"):
        await service.execute_refund(
            confirm_token=preview.confirm_token or "",
            idempotency_key="wrong",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_refund_execute_success_card_refund(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=9,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    payment = _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, stripe_service, _, _ = _build_service(db)
    preview = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    response = await service.execute_refund(
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="actor",
    )

    assert response.result == "success"
    assert response.refund is not None
    assert response.refund.method == "card"
    assert response.updated_booking is not None
    assert response.updated_booking.status == BookingStatus.CANCELLED.value
    assert response.updated_payment is not None
    assert response.updated_payment.status == "refunded"
    assert stripe_service.calls[0]["payment_intent_id"] == payment.stripe_payment_intent_id


@pytest.mark.asyncio
async def test_refund_execute_success_credit_issuance(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=10,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=18))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, credit_service, _ = _build_service(db)
    preview = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    response = await service.execute_refund(
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="actor",
    )

    assert response.result == "success"
    assert response.refund is not None
    assert response.refund.method == "credit"
    assert credit_service.calls
    assert credit_service.calls[0]["amount_cents"] == 10000


@pytest.mark.asyncio
async def test_refund_execute_idempotent_on_retry(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=11,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    preview = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    response1 = await service.execute_refund(
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="actor",
    )
    response2 = await service.execute_refund(
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="actor",
    )

    assert response1.model_dump() == response2.model_dump()


def test_refund_impact_includes_instructor_clawback(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=12,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.SETTLED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert response.impact.instructor_payout_delta == -90.0


def test_refund_impact_partial_amount(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=13,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.PARTIAL, value=40.0),
        note=None,
        actor_id="actor",
    )

    assert response.impact.student_card_refund == 40.0
    assert response.impact.instructor_payout_delta == -36.0


def test_refund_preview_warns_on_settled_payout(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=14,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.SETTLED.value)
    db.commit()

    service, _, _, _ = _build_service(db)
    response = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert any("payout" in warning.lower() for warning in response.warnings)


def test_refund_preview_creates_audit_entry(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=15,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, audit_service = _build_service(db)
    service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    assert audit_service.calls
    assert audit_service.calls[0]["action"] == "REFUND_PREVIEW"


@pytest.mark.asyncio
async def test_refund_execute_creates_audit_entry(
    db, test_student, test_instructor_with_availability
):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        status=BookingStatus.CONFIRMED,
        offset_index=16,
    )
    _set_booking_start(booking, datetime.now(timezone.utc) + timedelta(hours=30))
    _attach_payment(db, booking, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _, _, audit_service = _build_service(db)
    preview = service.preview_refund(
        booking_id=booking.id,
        reason_code=RefundReasonCode.GOODWILL,
        amount=RefundAmount(type=RefundAmountType.FULL),
        note=None,
        actor_id="actor",
    )

    await service.execute_refund(
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="actor",
    )

    actions = [call["action"] for call in audit_service.calls]
    assert "REFUND_EXECUTE" in actions
