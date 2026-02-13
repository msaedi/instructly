from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import selectinload
import ulid

from app.core.exceptions import (
    ConflictException,
    MCPTokenError,
    NotFoundException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_payment import BookingPayment
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent
from app.models.service_catalog import InstructorService
from app.schemas.admin_booking_actions import (
    NotificationRecipient,
    NotificationType,
    RefundPreference,
)
from app.services.booking_admin_service import BookingAdminService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService

try:  # pragma: no cover
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
    def __init__(self) -> None:
        self.refunds: list[dict] = []
        self.cancellations: list[str] = []

    def refund_payment(self, payment_intent_id: str, *, amount_cents: int, reason: str, idempotency_key: str):
        self.refunds.append(
            {
                "payment_intent_id": payment_intent_id,
                "amount_cents": amount_cents,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return {"status": "succeeded", "refund_id": "re_123", "amount_refunded": amount_cents}

    def cancel_payment_intent(self, payment_intent_id: str, idempotency_key: str):
        self.cancellations.append(payment_intent_id)
        return {"status": "canceled"}

    def capture_booking_payment_intent(self, *, booking_id: str, payment_intent_id: str, idempotency_key: str):
        return {"payment_intent": {"id": payment_intent_id}, "amount_received": 10000}


class FakeCreditService:
    def release_credits_for_booking(self, *, booking_id: str, use_transaction: bool = True):
        return 0

    def forfeit_credits_for_booking(self, *, booking_id: str, use_transaction: bool = True):
        return 0


class FakeNotificationService:
    def _send_student_cancellation_confirmation(self, booking):
        return True

    def _send_instructor_cancellation_confirmation(self, booking):
        return True

    def _send_student_booking_confirmation(self, booking):
        return True

    def _send_instructor_booking_notification(self, booking):
        return True

    def _send_student_reminder(self, booking, *, reminder_type: str = "24h"):
        return True

    def _send_instructor_reminder(self, booking, *, reminder_type: str = "24h"):
        return True

    def _send_student_completion_notification(self, booking):
        return True

    def _send_instructor_completion_notification(self, booking):
        return True


class FakeAuditService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log(self, **kwargs):
        self.calls.append(kwargs)
        return "audit_123"


class FakeSystemMessageService:
    def create_booking_cancelled_message(self, **kwargs):
        return None

    def create_booking_completed_message(self, **kwargs):
        return None


def _get_active_service_id(db, instructor_id: str) -> str:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise RuntimeError("Instructor profile not found for booking admin service test")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if not service:
        raise RuntimeError("Active service not found for booking admin service test")
    return service.id


def _create_booking(db, *, student_id: str, instructor_id: str, instructor_service_id: str) -> str:
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
        status=BookingStatus.CONFIRMED,
        offset_index=0,
    )
    booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(hours=30)
    booking.booking_end_utc = booking.booking_start_utc + timedelta(minutes=60)
    db.flush()
    return booking.id


def _attach_payment(db, booking_id: str, *, payment_status: str = PaymentStatus.SETTLED.value) -> None:
    payment_intent_id = f"pi_{generate_ulid()}"
    payment = PaymentIntent(
        booking_id=booking_id,
        stripe_payment_intent_id=payment_intent_id,
        amount=10000,
        application_fee=1000,
        status="succeeded" if payment_status == PaymentStatus.SETTLED.value else "requires_capture",
    )
    db.add(payment)
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking_id).first()
    if not bp:
        bp = BookingPayment(id=str(ulid.ULID()), booking_id=booking_id)
        db.add(bp)
    bp.payment_intent_id = payment_intent_id
    bp.payment_status = payment_status
    db.flush()


def _build_service(
    db,
    *,
    stripe: FakeStripeService | None = None,
    credit: FakeCreditService | None = None,
    notification: FakeNotificationService | None = None,
    audit: FakeAuditService | None = None,
    confirm: MCPConfirmTokenService | None = None,
    idempotency: MCPIdempotencyService | None = None,
    system_messages: FakeSystemMessageService | None = None,
    booking_service=None,
):
    redis = DummyRedis()
    stripe = stripe or FakeStripeService()
    credit = credit or FakeCreditService()
    notification = notification or FakeNotificationService()
    audit = audit or FakeAuditService()
    confirm = confirm or MCPConfirmTokenService(db)
    idempotency = idempotency or MCPIdempotencyService(db, redis_client=redis)
    system_messages = system_messages or FakeSystemMessageService()
    service = BookingAdminService(
        db,
        stripe_service=stripe,
        credit_service=credit,
        notification_service=notification,
        audit_service=audit,
        confirm_service=confirm,
        idempotency_service=idempotency,
        system_message_service=system_messages,
        booking_service=booking_service,
    )
    return service, stripe


def test_force_cancel_preview_full_card_override(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    response = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="INSTRUCTOR_NO_SHOW",
        note="note",
        refund_preference=RefundPreference.POLICY_BASED,
        actor_id="actor",
    )

    assert response.eligible is True
    assert response.refund_method == "card"
    assert response.confirm_token


@pytest.mark.asyncio
async def test_force_cancel_execute_full_refund(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.SETTLED.value)
    db.commit()

    service, stripe = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="INSTRUCTOR_NO_SHOW",
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
        actor_id="actor",
    )

    response = await service.execute_force_cancel(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )

    assert response.success is True
    assert response.new_status == BookingStatus.CANCELLED.value
    assert stripe.refunds


def test_force_cancel_preview_ineligible_when_not_confirmed(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        booking_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test Lesson",
        hourly_rate=100,
        total_price=100,
        duration_minutes=60,
        status=BookingStatus.CANCELLED,
        offset_index=0,
    )
    db.flush()

    service, _ = _build_service(db)
    response = service.preview_force_cancel(
        booking_id=booking.id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    assert response.eligible is False


def test_force_cancel_preview_requires_start_time_for_policy_based(db, test_student, test_instructor_with_availability):
    service, _ = _build_service(db)
    fake_booking = SimpleNamespace(
        id="bk1",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        booking_start_utc=None,
        booking_end_utc=None,
        total_price=100,
        hourly_rate=100,
        duration_minutes=60,
    )
    service.booking_repo.get_booking_with_details = lambda _bid: fake_booking
    service.payment_repo.get_payment_by_intent_id = lambda _pid: SimpleNamespace(
        amount=10000, application_fee=1000, instructor_payout_cents=9000
    )

    response = service.preview_force_cancel(
        booking_id="bk1",
        reason_code="TECHNICAL_ISSUE",
        note="note",
        refund_preference=RefundPreference.POLICY_BASED,
        actor_id="actor",
    )

    assert response.eligible is False
    assert response.ineligible_reason == "Booking start time unavailable for policy evaluation"


def test_force_cancel_preview_no_refund_warns(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    response = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    assert response.eligible is True
    assert response.refund_method == "none"
    assert response.warnings == ["No refund will be issued"]
    assert response.will_refund is False


def test_force_cancel_preview_ineligible_when_no_payment(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.total_price = 0
    db.commit()

    service, _ = _build_service(db)
    response = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
        actor_id="actor",
    )

    assert response.eligible is False
    assert response.ineligible_reason == "Booking has no payment to refund"


def test_cancel_refund_policy_thresholds():
    service = BookingAdminService.__new__(BookingAdminService)
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(booking_start_utc=now + timedelta(hours=26))
    refund = BookingAdminService._evaluate_cancel_refund(
        service,
        booking,
        reason_code="TECHNICAL_ISSUE",
        refund_preference=RefundPreference.POLICY_BASED,
        full_amount_cents=10000,
        lesson_price_cents=8000,
    )
    assert refund == ("card", 10000)

    booking.booking_start_utc = now + timedelta(hours=13)
    refund = BookingAdminService._evaluate_cancel_refund(
        service,
        booking,
        reason_code="TECHNICAL_ISSUE",
        refund_preference=RefundPreference.POLICY_BASED,
        full_amount_cents=10000,
        lesson_price_cents=8000,
    )
    assert refund == ("credit", 8000)

    booking.booking_start_utc = now + timedelta(hours=6)
    refund = BookingAdminService._evaluate_cancel_refund(
        service,
        booking,
        reason_code="TECHNICAL_ISSUE",
        refund_preference=RefundPreference.POLICY_BASED,
        full_amount_cents=10000,
        lesson_price_cents=8000,
    )
    assert refund == ("credit", 4000)


def test_compute_impacts_card_and_credit_paths():
    service = BookingAdminService.__new__(BookingAdminService)
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(booking_start_utc=now + timedelta(hours=6))
    payment = SimpleNamespace(amount=10000, application_fee=1000, instructor_payout_cents=9000)

    impacts = BookingAdminService._compute_impacts(
        service,
        booking,
        payment,
        refund_method="card",
        refund_amount_cents=5000,
    )
    assert impacts["platform_fee_impact"] == Decimal("5.00")
    assert impacts["instructor_payout_impact"] == Decimal("-45.00")

    impacts_credit = BookingAdminService._compute_impacts(
        service,
        booking,
        payment,
        refund_method="credit",
        refund_amount_cents=4000,
    )
    assert impacts_credit["platform_fee_impact"] == Decimal("0.00")
    assert impacts_credit["instructor_payout_impact"] == Decimal("-45.00")

    booking.booking_start_utc = now + timedelta(hours=13)
    impacts_credit = BookingAdminService._compute_impacts(
        service,
        booking,
        payment,
        refund_method="credit",
        refund_amount_cents=4000,
    )
    assert impacts_credit["instructor_payout_impact"] == Decimal("-90.00")


@pytest.mark.asyncio
async def test_execute_force_cancel_idempotency_mismatch(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    with pytest.raises(ValidationException) as exc:
        await service.execute_force_cancel(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key="wrong",
            actor_id="actor",
        )
    assert exc.value.code == "IDEMPOTENCY_MISMATCH"


@pytest.mark.asyncio
async def test_execute_force_cancel_booking_mismatch(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    with pytest.raises(ValidationException) as exc:
        await service.execute_force_cancel(
            booking_id="01OTHERBOOKING0000000000000",
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )
    assert exc.value.code == "BOOKING_MISMATCH"


@pytest.mark.asyncio
async def test_execute_force_cancel_cached_idempotency_response(db, test_student, test_instructor_with_availability):
    class CachedIdempotency:
        async def check_and_store(self, *_args, **_kwargs):
            return True, {
                "success": True,
                "error": None,
                "booking_id": "bk1",
                "previous_status": "CONFIRMED",
                "new_status": "cancelled",
                "refund_issued": False,
                "refund_id": None,
                "refund_amount": None,
                "refund_method": None,
                "notifications_sent": [],
                "audit_id": "audit",
            }

        async def store_result(self, *_args, **_kwargs):
            return None

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    confirm = MCPConfirmTokenService(db)
    service, _ = _build_service(db, idempotency=CachedIdempotency(), confirm=confirm)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    response = await service.execute_force_cancel(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )
    assert response.success is True
    assert response.booking_id == "bk1"


@pytest.mark.asyncio
async def test_execute_force_cancel_idempotency_in_progress(db, test_student, test_instructor_with_availability):
    class PendingIdempotency:
        async def check_and_store(self, *_args, **_kwargs):
            return True, None

        async def store_result(self, *_args, **_kwargs):
            return None

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db, idempotency=PendingIdempotency())
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    with pytest.raises(ConflictException):
        await service.execute_force_cancel(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_cancel_policy_based_uses_booking_service(db, test_student, test_instructor_with_availability):
    class BookingServiceStub:
        def __init__(self):
            self.calls = []

        def cancel_booking(self, *, booking_id: str, user, reason: str):
            self.calls.append((booking_id, reason))
            booking = db.query(Booking).filter(Booking.id == booking_id).first()
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = datetime.now(timezone.utc)
            db.flush()

    class NotificationFailing(FakeNotificationService):
        def _send_student_cancellation_confirmation(self, booking):
            raise AssertionError("Should not send cancellation emails for policy-based path")

    booking_service = BookingServiceStub()
    notification = NotificationFailing()

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(hours=48)
    booking.booking_end_utc = booking.booking_start_utc + timedelta(hours=1)
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db, booking_service=booking_service, notification=notification)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="TECHNICAL_ISSUE",
        note="note",
        refund_preference=RefundPreference.POLICY_BASED,
        actor_id="actor",
    )

    response = await service.execute_force_cancel(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )

    assert response.success is True
    assert booking_service.calls == [(booking_id, "TECHNICAL_ISSUE")]


@pytest.mark.asyncio
async def test_execute_force_cancel_no_refund_error_path(db, test_student, test_instructor_with_availability, monkeypatch):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(service, "_cancel_without_refund", _boom)

    response = await service.execute_force_cancel(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )

    assert response.success is False
    assert response.error == "cancel_no_refund_failed"


@pytest.mark.asyncio
async def test_execute_force_cancel_full_refund_error_path(db, test_student, test_instructor_with_availability, monkeypatch):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.SETTLED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="INSTRUCTOR_NO_SHOW",
        note="note",
        refund_preference=RefundPreference.FULL_CARD,
        actor_id="actor",
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(service, "_cancel_with_full_refund", _boom)

    response = await service.execute_force_cancel(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )

    assert response.success is False
    assert response.error == "cancel_refund_failed"


def test_cancel_without_refund_capture_failure_does_not_set_settled(db, test_student, test_instructor_with_availability):
    class StripeCaptureFail(FakeStripeService):
        def capture_booking_payment_intent(self, *args, **kwargs):
            raise RuntimeError("boom")

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()
    db.expire_all()

    stripe = StripeCaptureFail()
    service, _ = _build_service(db, stripe=stripe)
    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    service._cancel_without_refund(booking, reason_code="ADMIN_DISCRETION")
    db.commit()
    db.expire_all()

    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    assert booking.status == BookingStatus.CANCELLED
    assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value


def test_cancel_with_full_refund_without_payment_intent(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    bp_upd = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if not bp_upd:
        bp_upd = BookingPayment(id=str(ulid.ULID()), booking_id=booking.id)
        db.add(bp_upd)
    bp_upd.payment_intent_id = None
    bp_upd.payment_status = PaymentStatus.AUTHORIZED.value
    booking.total_price = 100
    db.commit()

    db.expire_all()
    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    service, _ = _build_service(db)
    refund_id, refund_issued = service._cancel_with_full_refund(
        booking,
        reason_code="ADMIN_DISCRETION",
        idempotency_key="idem",
    )

    assert refund_id is None
    assert refund_issued is False
    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    assert booking.status == BookingStatus.CANCELLED
    assert booking.payment_detail.payment_status == PaymentStatus.AUTHORIZED.value


def test_preview_force_complete_warnings_and_ineligible(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )

    service, _ = _build_service(db)
    fake_booking = SimpleNamespace(
        id=booking_id,
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status="failed",
            payment_intent_id="pi_123",
        ),
        booking_start_utc=datetime.now(timezone.utc),
        booking_end_utc=datetime.now(timezone.utc) - timedelta(hours=1),
        duration_minutes=60,
        total_price=100,
        hourly_rate=100,
    )
    service.booking_repo.get_booking_with_details = lambda _bid: fake_booking
    service.payment_repo.get_payment_by_intent_id = lambda _pid: SimpleNamespace(
        amount=10000, application_fee=1000, instructor_payout_cents=9000
    )

    response = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    assert response.eligible is False
    assert response.ineligible_reason == "Booking payment not in a capture-ready state"

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    from app.models.booking_payment import BookingPayment as BP
    bp = db.query(BP).filter(BP.booking_id == booking.id).first()
    if bp:
        bp.payment_status = PaymentStatus.AUTHORIZED.value
    else:
        db.add(BP(booking_id=booking.id, payment_status=PaymentStatus.AUTHORIZED.value))
    db.flush()
    booking.booking_end_utc = datetime.now(timezone.utc) + timedelta(hours=4)
    db.commit()
    db.expire_all()

    service2, _ = _build_service(db)
    response = service2.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    assert any("future" in warning for warning in response.warnings)

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.booking_end_utc = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    db.expire_all()

    response = service2.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    assert any("over 7 days" in warning for warning in response.warnings)


@pytest.mark.asyncio
async def test_execute_force_complete_capture_amount_fallback(db, test_student, test_instructor_with_availability, monkeypatch):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.booking_end_utc = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    db.expire_all()

    def _fake_capture(_booking_id, _source):
        return {"success": True, "amount_received": "bad"}

    monkeypatch.setattr("app.tasks.payment_tasks._process_capture_for_booking", _fake_capture)

    service, _ = _build_service(db)
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    response = await service.execute_force_complete(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )

    assert response.success is True
    assert response.capture_amount is not None
    assert response.new_status == BookingStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_execute_force_complete_capture_exception(db, test_student, test_instructor_with_availability, monkeypatch):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()
    db.expire_all()

    def _boom(_booking_id, _source):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.tasks.payment_tasks._process_capture_for_booking", _boom)

    service, _ = _build_service(db)
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    response = await service.execute_force_complete(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )
    assert response.success is True


def test_resend_notification_validation_and_send(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.status = BookingStatus.CANCELLED
    db.commit()

    service, _ = _build_service(db)
    with pytest.raises(ValidationException):
        service.resend_notification(
            booking_id=booking_id,
            notification_type=NotificationType.LESSON_COMPLETED,
            recipient=NotificationRecipient.STUDENT,
            note="note",
            actor_id="actor",
        )

    response = service.resend_notification(
        booking_id=booking_id,
        notification_type=NotificationType.CANCELLATION_NOTICE,
        recipient=NotificationRecipient.BOTH,
        note="note",
        actor_id="actor",
    )
    assert response.success is True
    assert {item.recipient for item in response.notifications_sent} == {"student", "instructor"}


def test_resend_notification_handles_errors(db, test_student, test_instructor_with_availability):
    class NotificationFail(FakeNotificationService):
        def _send_student_booking_confirmation(self, booking):
            raise RuntimeError("boom")

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    db.commit()

    notification = NotificationFail()
    service, _ = _build_service(db, notification=notification)
    response = service.resend_notification(
        booking_id=booking_id,
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        recipient=NotificationRecipient.STUDENT,
        note="note",
        actor_id="actor",
    )
    assert response.success is False
    assert response.error


def test_add_note_sets_created_by_id(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    db.commit()

    service, _ = _build_service(db)
    response = service.add_note(
        booking_id=booking_id,
        note="note",
        visibility="internal",
        category="general",
        actor_id=test_student.id,
        actor_type="user",
    )

    assert response.success is True
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    note = next(note for note in booking.admin_notes if note.id == response.note_id)
    assert note.created_by_id == test_student.id

    response = service.add_note(
        booking_id=booking_id,
        note="note2",
        visibility="internal",
        category="general",
        actor_id="svc",
        actor_type="service",
    )
    db.expire_all()
    note_ids = [note.id for note in db.query(Booking).filter(Booking.id == booking_id).first().admin_notes]
    assert response.note_id in note_ids


def test_get_booking_admin_service_dependency(db):
    from app.api.dependencies.services import get_booking_admin_service

    service = get_booking_admin_service(db)
    assert isinstance(service, BookingAdminService)


def test_booking_admin_service_init_default_stripe(db, monkeypatch):
    class StripeStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class ConfigStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class PricingStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class CreditStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class NotificationStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class AuditStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class SystemMessageStub:
        def __init__(self, *_args, **_kwargs):
            pass

    class BookingServiceStub:
        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr("app.services.booking_admin_service.StripeService", StripeStub)
    monkeypatch.setattr("app.services.booking_admin_service.ConfigService", ConfigStub)
    monkeypatch.setattr("app.services.booking_admin_service.PricingService", PricingStub)
    monkeypatch.setattr("app.services.booking_admin_service.CreditService", CreditStub)
    monkeypatch.setattr("app.services.booking_admin_service.NotificationService", NotificationStub)
    monkeypatch.setattr("app.services.booking_admin_service.AuditService", AuditStub)
    monkeypatch.setattr("app.services.booking_admin_service.SystemMessageService", SystemMessageStub)
    monkeypatch.setattr("app.services.booking_admin_service.BookingService", BookingServiceStub)

    service = BookingAdminService(db)
    assert service.stripe_service is not None


@pytest.mark.asyncio
async def test_execute_force_cancel_invalid_token_raises(db):
    service, _ = _build_service(db)
    with pytest.raises(MCPTokenError):
        await service.execute_force_cancel(
            booking_id="bk1",
            confirm_token="bad-token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_invalid_token_raises(db):
    service, _ = _build_service(db)
    with pytest.raises(MCPTokenError):
        await service.execute_force_complete(
            booking_id="bk1",
            confirm_token="bad-token",
            idempotency_key="idem",
            actor_id="actor",
        )


def test_booking_admin_helper_methods_resolve_amounts_and_status():
    service = BookingAdminService.__new__(BookingAdminService)
    assert service._status_value(BookingStatus.CONFIRMED) == "CONFIRMED"
    assert service._status_value("completed") == "COMPLETED"
    assert service._status_value(None) == ""

    booking = SimpleNamespace(
        total_price="bad",
        hourly_rate="bad",
        duration_minutes="bad",
    )
    amounts = service._resolve_amounts(booking, None)
    assert amounts["full_amount_cents"] == 0
    assert amounts["lesson_price_cents"] == 0


def test_booking_admin_datetime_and_decimal_helpers():
    from app.services import booking_admin_service as admin_module

    naive = datetime(2026, 2, 3, 12, 0, 0)
    assert admin_module._ensure_utc(naive).tzinfo == timezone.utc
    assert admin_module._cents_to_decimal(None) == Decimal("0.00")


def test_booking_admin_resolve_payment_handles_repo_errors():
    class PaymentRepo:
        def get_payment_by_intent_id(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def get_payment_by_booking_id(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    service = BookingAdminService.__new__(BookingAdminService)
    service.payment_repo = PaymentRepo()
    booking = SimpleNamespace(payment_detail=SimpleNamespace(payment_intent_id="pi_123"), id="bk1")
    assert service._resolve_payment(booking) is None

    booking.payment_detail = SimpleNamespace(payment_intent_id=None)
    assert service._resolve_payment(booking) is None


def test_booking_admin_compute_impacts_no_refund():
    service = BookingAdminService.__new__(BookingAdminService)
    booking = SimpleNamespace(booking_start_utc=None)
    impacts = service._compute_impacts(booking, None, refund_method=None, refund_amount_cents=None)
    assert impacts["platform_fee_impact"] == Decimal("0.00")
    assert impacts["instructor_payout_impact"] == Decimal("0.00")


def test_booking_admin_compute_impacts_credit_no_start_and_other():
    service = BookingAdminService.__new__(BookingAdminService)
    booking = SimpleNamespace(booking_start_utc=None)
    payment = SimpleNamespace(amount=10000, application_fee=1000, instructor_payout_cents=9000)

    impacts = BookingAdminService._compute_impacts(
        service,
        booking,
        payment,
        refund_method="credit",
        refund_amount_cents=4000,
    )
    assert impacts["instructor_payout_impact"] == Decimal("-45.00")

    impacts_other = BookingAdminService._compute_impacts(
        service,
        booking,
        payment,
        refund_method="other",
        refund_amount_cents=1000,
    )
    assert impacts_other["platform_fee_impact"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_execute_force_cancel_success_no_refund(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )
    response = await service.execute_force_cancel(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )

    assert response.success is True
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    assert booking.status == BookingStatus.CANCELLED
    assert booking.payment_detail.payment_status == PaymentStatus.SETTLED.value


def test_force_cancel_preview_not_found(db):
    service, _ = _build_service(db)
    with pytest.raises(NotFoundException):
        service.preview_force_cancel(
            booking_id="01INVALIDBOOKING000000000000",
            reason_code="ADMIN_DISCRETION",
            note="note",
            refund_preference=RefundPreference.NO_REFUND,
            actor_id="actor",
        )


def test_force_cancel_preview_ineligible_not_confirmed(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        booking_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test Lesson",
        hourly_rate=100,
        total_price=100,
        duration_minutes=60,
        status=BookingStatus.PENDING,
        offset_index=0,
    )
    db.flush()

    service, _ = _build_service(db)
    response = service.preview_force_cancel(
        booking_id=booking.id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )
    assert response.eligible is False
    assert response.ineligible_reason == "Booking not in confirmed status"


@pytest.mark.asyncio
async def test_execute_force_cancel_invalid_payload(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": "bad"}

        def validate_token(self, *_args, **_kwargs):
            return True

    service, _ = _build_service(db, confirm=ConfirmStub())
    with pytest.raises(ValidationException):
        await service.execute_force_cancel(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_cancel_validate_token_error(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem"}}

        def validate_token(self, *_args, **_kwargs):
            raise MCPTokenError("actor_mismatch")

    service, _ = _build_service(db, confirm=ConfirmStub())
    with pytest.raises(MCPTokenError):
        await service.execute_force_cancel(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_cancel_booking_not_found(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem", "refund_preference": "NO_REFUND", "reason_code": "ADMIN_DISCRETION"}}

        def validate_token(self, *_args, **_kwargs):
            return True

    class IdemStub:
        async def check_and_store(self, *_args, **_kwargs):
            return False, None

        async def store_result(self, *_args, **_kwargs):
            return None

    service, _ = _build_service(db, confirm=ConfirmStub(), idempotency=IdemStub())
    service.booking_repo.get_booking_with_details = lambda _bid: None
    with pytest.raises(NotFoundException):
        await service.execute_force_cancel(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_cancel_already_cancelled(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem", "refund_preference": "NO_REFUND", "reason_code": "ADMIN_DISCRETION"}}

        def validate_token(self, *_args, **_kwargs):
            return True

    class IdemStub:
        async def check_and_store(self, *_args, **_kwargs):
            return False, None

        async def store_result(self, *_args, **_kwargs):
            return None

    booking = SimpleNamespace(id="bk1", status=BookingStatus.CANCELLED)
    service, _ = _build_service(db, confirm=ConfirmStub(), idempotency=IdemStub())
    service.booking_repo.get_booking_with_details = lambda _bid: booking
    with pytest.raises(ValidationException):
        await service.execute_force_cancel(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_cancel_policy_based_failure(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {
                "payload": {
                    "booking_id": "bk1",
                    "idempotency_key": "idem",
                    "refund_preference": "POLICY_BASED",
                    "reason_code": "TECHNICAL_ISSUE",
                    "refund_method": "card",
                }
            }

        def validate_token(self, *_args, **_kwargs):
            return True

    class IdemStub:
        async def check_and_store(self, *_args, **_kwargs):
            return False, None

        async def store_result(self, *_args, **_kwargs):
            return None

    class BookingServiceFail:
        def cancel_booking(self, **_kwargs):
            raise RuntimeError("boom")

    booking = SimpleNamespace(id="bk1", status=BookingStatus.CONFIRMED, student=SimpleNamespace(id="student"))
    service, _ = _build_service(
        db,
        confirm=ConfirmStub(),
        idempotency=IdemStub(),
        booking_service=BookingServiceFail(),
    )
    service.booking_repo.get_booking_with_details = lambda _bid: booking

    with pytest.raises(RuntimeError):
        await service.execute_force_cancel(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


def test_force_complete_preview_not_found(db):
    service, _ = _build_service(db)
    with pytest.raises(NotFoundException):
        service.preview_force_complete(
            booking_id="01INVALIDBOOKING000000000000",
            reason_code="ADMIN_VERIFIED",
            note="note",
            actor_id="actor",
        )


def test_force_complete_preview_ineligible_not_confirmed(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
        booking_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test Lesson",
        hourly_rate=100,
        total_price=100,
        duration_minutes=60,
        status=BookingStatus.CANCELLED,
        offset_index=0,
    )
    db.flush()

    service, _ = _build_service(db)
    response = service.preview_force_complete(
        booking_id=booking.id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    assert response.eligible is False
    assert response.ineligible_reason == "Booking not in confirmed status"


def test_force_complete_preview_uses_start_plus_duration(db):
    service, _ = _build_service(db)
    fake_booking = SimpleNamespace(
        id="bk1",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        booking_start_utc=datetime.now(timezone.utc) - timedelta(hours=2),
        booking_end_utc=None,
        duration_minutes=60,
        total_price=100,
        hourly_rate=100,
    )
    service.booking_repo.get_booking_with_details = lambda _bid: fake_booking
    service.payment_repo.get_payment_by_intent_id = lambda _pid: SimpleNamespace(
        amount=10000, application_fee=1000, instructor_payout_cents=9000
    )
    response = service.preview_force_complete(
        booking_id="bk1",
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    assert response.hours_since_scheduled is not None


@pytest.mark.asyncio
async def test_execute_force_complete_invalid_payload(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": "bad"}

        def validate_token(self, *_args, **_kwargs):
            return True

    service, _ = _build_service(db, confirm=ConfirmStub())
    with pytest.raises(ValidationException):
        await service.execute_force_complete(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_validate_token_error(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem"}}

        def validate_token(self, *_args, **_kwargs):
            raise MCPTokenError("actor_mismatch")

    service, _ = _build_service(db, confirm=ConfirmStub())
    with pytest.raises(MCPTokenError):
        await service.execute_force_complete(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_idempotency_check_failure(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem"}}

        def validate_token(self, *_args, **_kwargs):
            return True

    class IdemFail:
        async def check_and_store(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        async def store_result(self, *_args, **_kwargs):
            return None

    service, _ = _build_service(db, confirm=ConfirmStub(), idempotency=IdemFail())
    with pytest.raises(RuntimeError):
        await service.execute_force_complete(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_booking_not_found(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem"}}

        def validate_token(self, *_args, **_kwargs):
            return True

    class IdemStub:
        async def check_and_store(self, *_args, **_kwargs):
            return False, None

        async def store_result(self, *_args, **_kwargs):
            return None

    service, _ = _build_service(db, confirm=ConfirmStub(), idempotency=IdemStub())
    service.booking_repo.get_booking_with_details = lambda _bid: None
    with pytest.raises(NotFoundException):
        await service.execute_force_complete(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_missing_inside_transaction(db):
    class ConfirmStub:
        def decode_token(self, _token):
            return {"payload": {"booking_id": "bk1", "idempotency_key": "idem"}}

        def validate_token(self, *_args, **_kwargs):
            return True

    class IdemStub:
        async def check_and_store(self, *_args, **_kwargs):
            return False, None

        async def store_result(self, *_args, **_kwargs):
            return None

    booking = SimpleNamespace(
        id="bk1",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
        ),
        booking_end_utc=None,
    )

    service, _ = _build_service(db, confirm=ConfirmStub(), idempotency=IdemStub())
    calls = {"count": 0}

    def _get_booking(_bid):
        calls["count"] += 1
        if calls["count"] == 1:
            return booking
        return None

    service.booking_repo.get_booking_with_details = _get_booking
    with pytest.raises(NotFoundException):
        await service.execute_force_complete(
            booking_id="bk1",
            confirm_token="token",
            idempotency_key="idem",
            actor_id="actor",
        )


def test_resend_notification_booking_not_found(db):
    service, _ = _build_service(db)
    with pytest.raises(NotFoundException):
        service.resend_notification(
            booking_id="01INVALIDBOOKING000000000000",
            notification_type=NotificationType.BOOKING_CONFIRMATION,
            recipient=NotificationRecipient.STUDENT,
            note="note",
            actor_id="actor",
        )


def test_resend_notification_booking_confirmation_both(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    db.commit()

    service, _ = _build_service(db)
    response = service.resend_notification(
        booking_id=booking_id,
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        recipient=NotificationRecipient.BOTH,
        note="note",
        actor_id="actor",
    )
    assert {item.recipient for item in response.notifications_sent} == {"student", "instructor"}


def test_resend_notification_lesson_completed_both(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.status = BookingStatus.COMPLETED
    db.commit()

    service, _ = _build_service(db)
    response = service.resend_notification(
        booking_id=booking_id,
        notification_type=NotificationType.LESSON_COMPLETED,
        recipient=NotificationRecipient.BOTH,
        note="note",
        actor_id="actor",
    )
    assert {item.recipient for item in response.notifications_sent} == {"student", "instructor"}


def test_add_note_not_found(db):
    service, _ = _build_service(db)
    with pytest.raises(NotFoundException):
        service.add_note(
            booking_id="01INVALIDBOOKING000000000000",
            note="note",
            visibility="internal",
            category="general",
            actor_id="actor",
            actor_type="user",
        )


def test_cancel_with_full_refund_cancels_payment_intent(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()
    db.expire_all()

    service, stripe = _build_service(db)
    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    refund_id, refund_issued = service._cancel_with_full_refund(
        booking,
        reason_code="ADMIN_DISCRETION",
        idempotency_key="idem",
    )
    assert refund_issued is True
    assert refund_id is None
    assert stripe.cancellations


def test_cancel_with_full_refund_missing_booking_in_transaction(db):
    class RepoStub:
        def __init__(self):
            self.calls = 0

        def get_booking_with_details(self, _bid):
            self.calls += 1
            return None

    service, _ = _build_service(db)
    booking = SimpleNamespace(
        id="bk1",
        payment_detail=SimpleNamespace(
            payment_intent_id=None,
            payment_status=PaymentStatus.AUTHORIZED.value,
        ),
        booking_start_utc=datetime.now(timezone.utc),
        total_price=0,
        hourly_rate=0,
        duration_minutes=0,
    )
    service.booking_repo = RepoStub()
    with pytest.raises(NotFoundException):
        service._cancel_with_full_refund(booking, reason_code="ADMIN_DISCRETION", idempotency_key="idem")


def test_cancel_without_refund_missing_booking_in_transaction(db):
    class RepoStub:
        def get_booking_with_details(self, _bid):
            return None

    service, _ = _build_service(db)
    booking = SimpleNamespace(
        id="bk1",
        payment_detail=SimpleNamespace(
            payment_intent_id=None,
            payment_status=PaymentStatus.AUTHORIZED.value,
        ),
    )
    service.booking_repo = RepoStub()
    with pytest.raises(NotFoundException):
        service._cancel_without_refund(booking, reason_code="ADMIN_DISCRETION")


def test_valid_states_for_notification_default(db):
    service, _ = _build_service(db)
    assert service._valid_states_for_notification("unknown") == set()
@pytest.mark.asyncio
async def test_execute_force_cancel_policy_based_missing_student(db, test_student, test_instructor_with_availability, monkeypatch):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="TECHNICAL_ISSUE",
        note="note",
        refund_preference=RefundPreference.POLICY_BASED,
        actor_id="actor",
    )

    fake_booking = SimpleNamespace(
        id=booking_id,
        status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.AUTHORIZED.value,
        student=None,
    )
    monkeypatch.setattr(service.booking_repo, "get_booking_with_details", lambda _bid: fake_booking)

    with pytest.raises(ValidationException):
        await service.execute_force_cancel(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_cancel_idempotency_check_failure(db, test_student, test_instructor_with_availability):
    class IdemFail:
        async def check_and_store(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        async def store_result(self, *_args, **_kwargs):
            return None

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db, idempotency=IdemFail())
    preview = service.preview_force_cancel(
        booking_id=booking_id,
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference=RefundPreference.NO_REFUND,
        actor_id="actor",
    )

    with pytest.raises(RuntimeError):
        await service.execute_force_cancel(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_idempotency_mismatch(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )

    with pytest.raises(ValidationException):
        await service.execute_force_complete(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key="wrong",
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_booking_mismatch(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )

    with pytest.raises(ValidationException):
        await service.execute_force_complete(
            booking_id="01OTHERBOOKING0000000000000",
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_cached_idempotency_response(db, test_student, test_instructor_with_availability):
    class CachedIdempotency:
        async def check_and_store(self, *_args, **_kwargs):
            return True, {
                "success": True,
                "error": None,
                "booking_id": "bk1",
                "previous_status": "CONFIRMED",
                "new_status": "completed",
                "payment_captured": True,
                "capture_amount": "100.00",
                "instructor_payout_scheduled": True,
                "payout_amount": "90.00",
                "audit_id": "audit",
            }

        async def store_result(self, *_args, **_kwargs):
            return None

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db, idempotency=CachedIdempotency())
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    response = await service.execute_force_complete(
        booking_id=booking_id,
        confirm_token=preview.confirm_token,
        idempotency_key=preview.idempotency_key,
        actor_id="actor",
    )
    assert response.booking_id == "bk1"


@pytest.mark.asyncio
async def test_execute_force_complete_idempotency_in_progress(db, test_student, test_instructor_with_availability):
    class PendingIdempotency:
        async def check_and_store(self, *_args, **_kwargs):
            return True, None

        async def store_result(self, *_args, **_kwargs):
            return None

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db, idempotency=PendingIdempotency())
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    with pytest.raises(ConflictException):
        await service.execute_force_complete(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )


@pytest.mark.asyncio
async def test_execute_force_complete_requires_confirmed_status(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    service, _ = _build_service(db)
    preview = service.preview_force_complete(
        booking_id=booking_id,
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    booking.status = BookingStatus.CANCELLED
    db.commit()

    with pytest.raises(ValidationException):
        await service.execute_force_complete(
            booking_id=booking_id,
            confirm_token=preview.confirm_token,
            idempotency_key=preview.idempotency_key,
            actor_id="actor",
        )


def test_preview_force_complete_missing_times_warns(db, test_student, test_instructor_with_availability):
    service, _ = _build_service(db)
    fake_booking = SimpleNamespace(
        id="bk1",
        status=BookingStatus.CONFIRMED,
        payment_detail=SimpleNamespace(
            payment_status=PaymentStatus.AUTHORIZED.value,
            payment_intent_id="pi_123",
        ),
        booking_start_utc=None,
        booking_end_utc=None,
        duration_minutes=None,
        total_price=100,
        hourly_rate=100,
    )
    service.booking_repo.get_booking_with_details = lambda _bid: fake_booking
    service.payment_repo.get_payment_by_intent_id = lambda _pid: SimpleNamespace(
        amount=10000, application_fee=1000, instructor_payout_cents=9000
    )

    response = service.preview_force_complete(
        booking_id="bk1",
        reason_code="ADMIN_VERIFIED",
        note="note",
        actor_id="actor",
    )
    assert any("Lesson time not available" in warning for warning in response.warnings)


def test_resend_notification_reminder_types(db, test_student, test_instructor_with_availability):
    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    db.commit()

    service, _ = _build_service(db)
    response = service.resend_notification(
        booking_id=booking_id,
        notification_type=NotificationType.LESSON_REMINDER_1H,
        recipient=NotificationRecipient.BOTH,
        note="note",
        actor_id="actor",
    )
    assert response.success is True
    assert {item.recipient for item in response.notifications_sent} == {"student", "instructor"}


def test_send_admin_cancellation_notifications_handles_exception(db, test_student, test_instructor_with_availability):
    class NotificationFail(FakeNotificationService):
        def _send_student_cancellation_confirmation(self, booking):
            return True

        def _send_instructor_cancellation_confirmation(self, booking):
            raise RuntimeError("boom")

    service, _ = _build_service(db, notification=NotificationFail())
    booking = SimpleNamespace(
        student_id="student",
        instructor_id="instructor",
        booking_date=date.today(),
        start_time=time(9, 0),
        id="bk1",
    )
    service._send_admin_cancellation_notifications(booking)


def test_log_cancellation_message_handles_exception(db, test_student, test_instructor_with_availability):
    class SystemMessageFail(FakeSystemMessageService):
        def create_booking_cancelled_message(self, **kwargs):
            raise RuntimeError("boom")

    service, _ = _build_service(db, system_messages=SystemMessageFail())
    booking = SimpleNamespace(
        student_id="student",
        instructor_id="instructor",
        booking_date=date.today(),
        start_time=time(9, 0),
        id="bk1",
    )
    service._log_cancellation_message(booking)


def test_post_complete_actions_handles_exceptions(db):
    class StudentCreditFail:
        def __init__(self, *_args, **_kwargs):
            pass

        def maybe_issue_milestone_credit(self, **_kwargs):
            raise RuntimeError("boom")

    class ReferralFail:
        def __init__(self, *_args, **_kwargs):
            pass

        def on_instructor_lesson_completed(self, **_kwargs):
            raise RuntimeError("boom")

    class SystemMessageFail(FakeSystemMessageService):
        def create_booking_completed_message(self, **kwargs):
            raise RuntimeError("boom")

    service, _ = _build_service(db, system_messages=SystemMessageFail())
    booking = SimpleNamespace(
        student_id="student",
        instructor_id="instructor",
        booking_id="bk1",
        id="bk1",
        booking_date=date.today(),
        completed_at=datetime.now(timezone.utc),
        instructor_service=SimpleNamespace(name="Guitar"),
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.services.student_credit_service.StudentCreditService", StudentCreditFail)
    monkeypatch.setattr("app.services.referral_service.ReferralService", ReferralFail)

    try:
        service._post_complete_actions(booking)
    finally:
        monkeypatch.undo()


def test_cancel_with_full_refund_handles_credit_release_failure(db, test_student, test_instructor_with_availability):
    class CreditFail(FakeCreditService):
        def release_credits_for_booking(self, *, booking_id: str, use_transaction: bool = True):
            raise RuntimeError("boom")

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.SETTLED.value)
    db.commit()
    db.expire_all()

    credit = CreditFail()
    service, _ = _build_service(db, credit=credit)
    booking = db.query(Booking).options(selectinload(Booking.payment_detail)).filter(Booking.id == booking_id).first()
    refund_id, refund_issued = service._cancel_with_full_refund(
        booking,
        reason_code="ADMIN_DISCRETION",
        idempotency_key="idem",
    )
    assert refund_issued is True
    assert refund_id is not None


def test_cancel_without_refund_handles_credit_forfeit_failure(db, test_student, test_instructor_with_availability):
    class CreditFail(FakeCreditService):
        def forfeit_credits_for_booking(self, *, booking_id: str, use_transaction: bool = True):
            raise RuntimeError("boom")

    service_id = _get_active_service_id(db, test_instructor_with_availability.id)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service_id,
    )
    _attach_payment(db, booking_id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.commit()

    credit = CreditFail()
    service, _ = _build_service(db, credit=credit)
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    service._cancel_without_refund(booking, reason_code="ADMIN_DISCRETION")
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    assert booking.status == BookingStatus.CANCELLED
