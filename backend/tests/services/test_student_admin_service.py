from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.tests.factories.booking_builders import create_booking_pg_safe
import pytest

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation
from app.models.payment import PlatformCredit
from app.models.service_catalog import InstructorService as Service
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_student_actions import CreditAdjustAction
from app.services.student_admin_service import (
    _SUSPEND_CREDIT_REVOKE_REASON,
    StudentAdminService,
    _booking_amount,
    _cents_to_decimal,
    _decimal_to_cents,
    _ensure_utc,
)


class FakeIdempotency:
    def __init__(self, already_done: bool = False, cached: dict | None = None) -> None:
        self.already_done = already_done
        self.cached = cached
        self.stored: list[tuple[str, dict]] = []

    async def check_and_store(self, key: str, operation: str):
        return self.already_done, self.cached

    async def store_result(self, key: str, result: dict):
        self.stored.append((key, result))


class BoomIdempotency:
    async def check_and_store(self, key: str, operation: str):
        raise RuntimeError("boom")

    async def store_result(self, key: str, result: dict):
        return None


class StubNotificationService:
    def __init__(self) -> None:
        self.student_calls: list[str] = []
        self.instructor_calls: list[str] = []

    def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
        self.student_calls.append(booking.id)
        return True

    def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
        self.instructor_calls.append(booking.id)
        return True


class StubBookingAdminService:
    def __init__(self, db, refund_cents: int = 2500, raise_on: bool = False) -> None:
        self.db = db
        self.refund_cents = refund_cents
        self.raise_on = raise_on

    def _cancel_with_full_refund(self, booking: Booking, *, reason_code: str, idempotency_key: str):
        if self.raise_on:
            raise RuntimeError("cancel failed")
        booking.status = BookingStatus.CANCELLED
        booking.refunded_to_card_amount = self.refund_cents
        booking.cancelled_at = datetime.now(timezone.utc)
        self.db.flush()
        return "refund", True

    def _cancel_without_refund(self, booking: Booking, *, reason_code: str) -> None:
        if self.raise_on:
            raise RuntimeError("cancel failed")
        booking.status = BookingStatus.CANCELLED
        booking.refunded_to_card_amount = 0
        booking.cancelled_at = datetime.now(timezone.utc)
        self.db.flush()


def _service(
    db,
    *,
    booking_admin_service=None,
    idempotency=None,
    notification_service=None,
) -> StudentAdminService:
    return StudentAdminService(
        db,
        booking_admin_service=booking_admin_service,
        idempotency_service=idempotency,
        notification_service=notification_service,
    )


def _first_service(db, profile_id: str) -> Service:
    svc = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile_id, Service.is_active == True)  # noqa: E712
        .order_by(Service.id)
        .first()
    )
    if not svc:
        raise AssertionError("Missing service")
    return svc


def test_helper_functions_cover_branches():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert _ensure_utc(naive).tzinfo is not None
    assert _ensure_utc(aware) == aware
    assert _cents_to_decimal(None) == Decimal("0.00")
    assert _decimal_to_cents("1.25") == 125

    booking_missing = SimpleNamespace(total_price=None, hourly_rate=None, duration_minutes=None)
    assert _booking_amount(booking_missing) == Decimal("0.00")

    booking_total = SimpleNamespace(total_price=Decimal("12.34"), hourly_rate=None, duration_minutes=None)
    assert _booking_amount(booking_total) == Decimal("12.34")

    booking_calc = SimpleNamespace(total_price=None, hourly_rate=Decimal("40.00"), duration_minutes=90)
    assert _booking_amount(booking_calc) == Decimal("60.00")


def test_load_student_by_email_and_validation(db, test_student, test_instructor):
    service = _service(db)
    loaded = service._load_student(test_student.email)
    assert loaded.id == test_student.id

    with pytest.raises(ValidationException):
        service._load_student(test_instructor.id)

    with pytest.raises(NotFoundException):
        service._load_student("missing-student")


def test_conversation_pagination_branches(db, test_student, monkeypatch):
    service = _service(db)
    now = datetime.now(timezone.utc)
    conversations = [
        SimpleNamespace(id=f"conv-{idx}", last_message_at=now, created_at=now) for idx in range(200)
    ]
    calls = {"count": 0}

    def fake_find_for_user(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return conversations
        return []

    monkeypatch.setattr(service.conversation_repo, "find_for_user", fake_find_for_user)
    ids = service._conversation_ids_for_user(test_student.id)
    assert len(ids) == 200

    monkeypatch.setattr(
        service.conversation_repo,
        "find_for_user",
        lambda *args, **kwargs: [
            SimpleNamespace(id=f"conv-{idx}", last_message_at=None, created_at=None)
            for idx in range(200)
        ],
    )
    ids = service._conversation_ids_for_user(test_student.id)
    assert len(ids) == 200


def test_preview_suspend_deactivated(db, test_student):
    service = _service(db)
    test_student.account_status = "deactivated"
    db.flush()

    response = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
    )
    assert response.eligible is False
    assert response.ineligible_reason == "Account deactivated"


def test_preview_suspend_pending_no_cancel_warning(db, test_student, test_instructor):
    service = _service(db)
    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=8,
        max_shifts=120,
    )

    response = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=False,
        forfeit_credits=False,
        actor_id="admin",
    )
    assert any("Pending bookings will remain active" in warning for warning in response.warnings)


def test_preview_suspend_ineligible(db, test_student):
    service = _service(db)
    test_student.account_status = "suspended"
    db.flush()

    response = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
    )
    assert response.eligible is False
    assert response.confirm_token is None
    assert response.ineligible_reason == "Already suspended"


def test_preview_suspend_generates_token_and_warnings(db, test_student, test_instructor):
    payment_repo = RepositoryFactory.create_payment_repository(db)
    service = _service(db)

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=3,
        max_shifts=120,
    )

    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=1500,
        reason="goodwill",
        source_type="admin",
        status="available",
    )

    conversation = Conversation(student_id=test_student.id, instructor_id=test_instructor.id)
    db.add(conversation)
    db.flush()

    response = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=True,
        actor_id="admin",
    )
    assert response.eligible is True
    assert response.confirm_token is not None
    assert response.pending_bookings_count == 1
    assert any("pending bookings" in warning for warning in response.warnings)
    assert any("credits" in warning for warning in response.warnings)
    assert response.active_conversations == 1
    assert booking.id


@pytest.mark.asyncio
async def test_execute_suspend_success_and_forfeit(db, test_student, test_instructor, monkeypatch):
    payment_repo = RepositoryFactory.create_payment_repository(db)
    notification_service = StubNotificationService()
    booking_admin_service = StubBookingAdminService(db, refund_cents=0)
    idempotency = FakeIdempotency()

    service = _service(
        db,
        booking_admin_service=booking_admin_service,
        idempotency=idempotency,
        notification_service=notification_service,
    )
    invalidation_calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        service.user_repo,
        "invalidate_all_tokens",
        lambda user_id, trigger=None: invalidation_calls.append((user_id, trigger)) or True,
    )

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=5,
        max_shifts=120,
    )

    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=2000,
        reason="goodwill",
        source_type="admin",
        status="available",
    )
    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=0,
        reason="zero",
        source_type="admin",
        status="available",
    )
    revoked = PlatformCredit(
        id="01REVX",
        user_id=test_student.id,
        amount_cents=500,
        reason="revoked",
        source_type="admin",
        status="revoked",
    )
    revoked.revoked = True
    revoked.revoked_reason = "other"
    expired = PlatformCredit(
        id="01EXPX",
        user_id=test_student.id,
        amount_cents=500,
        reason="expired",
        source_type="admin",
        status="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        original_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add_all([revoked, expired])
    db.flush()

    conversation = Conversation(student_id=test_student.id, instructor_id=test_instructor.id)
    db.add(conversation)
    db.flush()

    preview = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=True,
        actor_id="admin",
    )

    response = await service.execute_suspend(
        student_id=test_student.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )

    assert response.success is True
    assert response.bookings_cancelled == 1
    assert response.credits_forfeited == Decimal("20.00")
    assert test_student.account_status == "suspended"
    assert "conversations_archived" in response.notifications_sent
    assert invalidation_calls == [(test_student.id, "suspension")]

    revoked_credit = (
        db.query(PlatformCredit)
        .filter(
            PlatformCredit.user_id == test_student.id,
            PlatformCredit.status == "revoked",
            PlatformCredit.revoked_reason == _SUSPEND_CREDIT_REVOKE_REASON,
        )
        .first()
    )
    assert revoked_credit is not None
    assert revoked_credit.revoked_reason == _SUSPEND_CREDIT_REVOKE_REASON
    assert notification_service.student_calls == [booking.id]
    assert notification_service.instructor_calls == [booking.id]


def test_execute_suspend_cancel_error_sets_error(db, test_student, test_instructor):
    booking_admin_service = StubBookingAdminService(db, raise_on=True)
    service = _service(db, booking_admin_service=booking_admin_service)

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=2),
        start_time=time(12, 0),
        end_time=time(13, 0),
        service_name="Test",
        hourly_rate=40,
        total_price=40,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=7,
        max_shifts=120,
    )

    response = service._execute_suspend_sync(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=False,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
        idempotency_key="idem",
    )
    assert response.success is False
    assert response.error == "cancel_pending_bookings_failed"
    assert booking.status == BookingStatus.CONFIRMED


def test_execute_suspend_already_suspended_raises(db, test_student):
    service = _service(db)
    test_student.account_status = "suspended"
    db.flush()
    with pytest.raises(ValidationException):
        service._execute_suspend_sync(
            student_id=test_student.id,
            reason_code="FRAUD",
            note="note",
            notify_student=False,
            cancel_pending_bookings=False,
            forfeit_credits=False,
            actor_id="admin",
            idempotency_key="idem",
        )


def test_execute_suspend_refund_counts(db, test_student, test_instructor):
    booking_admin_service = StubBookingAdminService(db, refund_cents=2500)
    notification_service = StubNotificationService()
    service = _service(
        db,
        booking_admin_service=booking_admin_service,
        notification_service=notification_service,
    )

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=2),
        start_time=time(14, 0),
        end_time=time(15, 0),
        service_name="Test",
        hourly_rate=60,
        total_price=60,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=12,
        max_shifts=120,
    )

    response = service._execute_suspend_sync(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
        idempotency_key="idem",
    )
    assert response.refunds_issued == 1
    assert response.total_refunded == Decimal("25.00")


def test_execute_suspend_booking_full_none(db, test_student, test_instructor, monkeypatch):
    booking_admin_service = StubBookingAdminService(db, refund_cents=0)
    notification_service = StubNotificationService()
    service = _service(
        db,
        booking_admin_service=booking_admin_service,
        notification_service=notification_service,
    )

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=3),
        start_time=time(16, 0),
        end_time=time(17, 0),
        service_name="Test",
        hourly_rate=60,
        total_price=60,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=15,
        max_shifts=120,
    )

    monkeypatch.setattr(service.booking_repo, "get_by_id", lambda _id: None)
    monkeypatch.setattr(service.booking_repo, "get_booking_with_details", lambda _id: None)

    response = service._execute_suspend_sync(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
        idempotency_key="idem",
    )
    assert response.bookings_cancelled == 0


def test_execute_suspend_notification_exceptions(db, test_student, test_instructor):
    class RaisingNotificationService:
        def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
            raise RuntimeError("boom")

        def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
            raise RuntimeError("boom")

    booking_admin_service = StubBookingAdminService(db, refund_cents=0)
    service = _service(
        db,
        booking_admin_service=booking_admin_service,
        notification_service=RaisingNotificationService(),
    )

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=4),
        start_time=time(18, 0),
        end_time=time(19, 0),
        service_name="Test",
        hourly_rate=60,
        total_price=60,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=18,
        max_shifts=120,
    )

    response = service._execute_suspend_sync(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
        idempotency_key="idem",
    )
    assert response.success is True


def test_execute_suspend_notify_student_false_branch(db, test_student, test_instructor):
    booking_admin_service = StubBookingAdminService(db, refund_cents=0)
    service = _service(db, booking_admin_service=booking_admin_service)

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=5),
        start_time=time(20, 0),
        end_time=time(21, 0),
        service_name="Test",
        hourly_rate=60,
        total_price=60,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=22,
        max_shifts=120,
    )

    response = service._execute_suspend_sync(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=False,
        cancel_pending_bookings=True,
        forfeit_credits=False,
        actor_id="admin",
        idempotency_key="idem",
    )
    assert response.success is True

def test_execute_suspend_credit_forfeit_error(db, test_student):
    service = _service(db)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    service._forfeit_all_credits = _boom  # type: ignore[assignment]

    response = service._execute_suspend_sync(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=False,
        cancel_pending_bookings=False,
        forfeit_credits=True,
        actor_id="admin",
        idempotency_key="idem",
    )
    assert response.success is False
    assert response.error == "credit_forfeit_failed"


@pytest.mark.asyncio
async def test_execute_suspend_idempotency_branches(db, test_student):
    service = _service(db, idempotency=FakeIdempotency(already_done=True, cached=None))

    preview = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=False,
        forfeit_credits=False,
        actor_id="admin",
    )

    with pytest.raises(ConflictException):
        await service.execute_suspend(
            student_id=test_student.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )

    cached_payload = {
        "success": True,
        "error": None,
        "student_id": test_student.id,
        "previous_status": "active",
        "new_status": "suspended",
        "bookings_cancelled": 0,
        "refunds_issued": 0,
        "total_refunded": "0.00",
        "credits_forfeited": "0.00",
        "notifications_sent": [],
        "audit_id": "audit",
    }
    service = _service(db, idempotency=FakeIdempotency(already_done=True, cached=cached_payload))

    response = await service.execute_suspend(
        student_id=test_student.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert response.student_id == test_student.id


@pytest.mark.asyncio
async def test_execute_suspend_validation_branches(db, test_student):
    service = _service(db, idempotency=FakeIdempotency())
    with pytest.raises(Exception):
        await service.execute_suspend(
            student_id=test_student.id,
            confirm_token="bad",
            idempotency_key="idem",
            actor_id="admin",
        )

    service = _service(db, idempotency=FakeIdempotency())
    service.confirm_service.decode_token = lambda _token: {"payload": "bad"}  # type: ignore[assignment]
    with pytest.raises(ValidationException):
        await service.execute_suspend(
            student_id=test_student.id,
            confirm_token="ctok",
            idempotency_key="idem",
            actor_id="admin",
        )

    service = _service(db, idempotency=FakeIdempotency())
    preview = service.preview_suspend(
        student_id=test_student.id,
        reason_code="FRAUD",
        note="note",
        notify_student=True,
        cancel_pending_bookings=False,
        forfeit_credits=False,
        actor_id="admin",
    )

    with pytest.raises(ValidationException):
        await service.execute_suspend(
            student_id=test_student.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key="wrong",
            actor_id="admin",
        )

    with pytest.raises(ValidationException):
        await service.execute_suspend(
            student_id="other",
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )

    service = _service(db, idempotency=BoomIdempotency())
    with pytest.raises(RuntimeError):
        await service.execute_suspend(
            student_id=test_student.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )


def test_unsuspend_restores_credits(db, test_student):
    payment_repo = RepositoryFactory.create_payment_repository(db)
    service = _service(db)
    test_student.account_status = "suspended"
    db.flush()

    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=1000,
        reason="revoked",
        source_type="admin",
        status="revoked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        original_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    revoked_credit = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.user_id == test_student.id)
        .first()
    )
    assert revoked_credit is not None
    revoked_credit.revoked = True
    revoked_credit.revoked_reason = _SUSPEND_CREDIT_REVOKE_REASON
    revoked_credit.revoked_at = datetime.now(timezone.utc)

    expired_credit = PlatformCredit(
        id="01EXP",
        user_id=test_student.id,
        amount_cents=500,
        reason="revoked",
        source_type="admin",
        status="revoked",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        original_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    expired_credit.revoked = True
    expired_credit.revoked_reason = _SUSPEND_CREDIT_REVOKE_REASON
    expired_credit.revoked_at = datetime.now(timezone.utc)
    db.add(expired_credit)
    db.flush()

    response = service.unsuspend(
        student_id=test_student.id,
        reason="ok",
        restore_credits=True,
        actor_id="admin",
    )
    assert response.new_status == "active"
    assert response.credits_restored == Decimal("10.00")

    updated = db.query(PlatformCredit).filter(PlatformCredit.id == revoked_credit.id).first()
    assert updated is not None
    assert updated.status == "available"


def test_unsuspend_without_restore(db, test_student):
    service = _service(db)
    test_student.account_status = "suspended"
    db.flush()
    response = service.unsuspend(
        student_id=test_student.id,
        reason="ok",
        restore_credits=False,
        actor_id="admin",
    )
    assert response.credits_restored == Decimal("0.00")


def test_unsuspend_requires_suspended(db, test_student):
    service = _service(db)
    with pytest.raises(ValidationException):
        service.unsuspend(
            student_id=test_student.id,
            reason="no",
            restore_credits=True,
            actor_id="admin",
        )


def test_preview_credit_adjust_ineligible_and_warning(db, test_student):
    service = _service(db)

    reserved = PlatformCredit(
        id="01RES",
        user_id=test_student.id,
        amount_cents=1000,
        reason="reserved",
        source_type="test",
        status="reserved",
        reserved_amount_cents=1000,
        reserved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        original_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(reserved)
    db.flush()

    response = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.REMOVE,
        amount=Decimal("50.00"),
        reason_code="GOODWILL",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    assert response.eligible is False
    assert response.confirm_token is None
    assert any("reserved" in warning for warning in response.warnings)


def test_preview_credit_adjust_generates_token(db, test_student):
    service = _service(db)
    response = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.ADD,
        amount=Decimal("10.00"),
        reason_code="GOODWILL",
        note="note",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        actor_id="admin",
    )
    assert response.confirm_token is not None
    assert response.will_create_credit is True


def test_preview_credit_adjust_validation_errors(db, test_student):
    service = _service(db)
    with pytest.raises(ValidationException):
        service.preview_credit_adjust(
            student_id=test_student.id,
            action=CreditAdjustAction.ADD,
            amount=Decimal("0.00"),
            reason_code="GOODWILL",
            note=None,
            expires_at=None,
            actor_id="admin",
        )

    with pytest.raises(ValidationException):
        service.preview_credit_adjust(
            student_id=test_student.id,
            action=CreditAdjustAction.ADD,
            amount=Decimal("5.00"),
            reason_code="GOODWILL",
            note=None,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            actor_id="admin",
        )

    response = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.SET,
        amount=Decimal("5.00"),
        reason_code="GOODWILL",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    assert response.will_remove_credit is False


@pytest.mark.asyncio
async def test_execute_credit_adjust_add_and_idempotency(db, test_student):
    idempotency = FakeIdempotency()
    service = _service(db, idempotency=idempotency)

    preview = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.ADD,
        amount=Decimal("5.00"),
        reason_code="GOODWILL",
        note=None,
        expires_at=None,
        actor_id="admin",
    )

    response = await service.execute_credit_adjust(
        student_id=test_student.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert response.success is True
    assert response.new_balance == Decimal("5.00")


def test_execute_credit_adjust_remove_and_set(db, test_student):
    service = _service(db)
    payment_repo = RepositoryFactory.create_payment_repository(db)

    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=5000,
        reason="credit",
        source_type="admin",
        status="available",
    )

    response = service._execute_credit_adjust_sync(
        student_id=test_student.id,
        action=CreditAdjustAction.REMOVE,
        amount_cents=2000,
        reason_code="CORRECTION",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    assert response.credits_revoked == 1

    remainder = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.user_id == test_student.id, PlatformCredit.status == "available")
        .first()
    )
    assert remainder is not None
    assert remainder.amount_cents == 3000

    response = service._execute_credit_adjust_sync(
        student_id=test_student.id,
        action=CreditAdjustAction.SET,
        amount_cents=1000,
        reason_code="CORRECTION",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    assert response.new_balance == Decimal("10.00")

    response = service._execute_credit_adjust_sync(
        student_id=test_student.id,
        action=CreditAdjustAction.SET,
        amount_cents=2000,
        reason_code="CORRECTION",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    assert response.new_balance == Decimal("20.00")

    response = service._execute_credit_adjust_sync(
        student_id=test_student.id,
        action=CreditAdjustAction.SET,
        amount_cents=_decimal_to_cents(response.new_balance),
        reason_code="CORRECTION",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    assert response.delta == Decimal("0.00")


def test_execute_credit_adjust_validation_and_helpers(db, test_student):
    service = _service(db)
    assert service._remove_available_credits(test_student.id, 0, "reason") == 0

    with pytest.raises(ValidationException):
        service._remove_available_credits(test_student.id, 1000, "reason")

    with pytest.raises(ValidationException):
        service._execute_credit_adjust_sync(
            student_id=test_student.id,
            action=CreditAdjustAction.ADD,
            amount_cents=0,
            reason_code="GOODWILL",
            note=None,
            expires_at=None,
            actor_id="admin",
        )


def test_remove_available_credits_branches(db, test_student):
    service = _service(db)
    payment_repo = RepositoryFactory.create_payment_repository(db)
    now = datetime.now(timezone.utc)
    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=0,
        reason="zero",
        source_type="admin",
        status="available",
        expires_at=now + timedelta(days=1),
        original_expires_at=now + timedelta(days=1),
    )
    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=5000,
        reason="big",
        source_type="admin",
        status="available",
        expires_at=now + timedelta(days=2),
        original_expires_at=now + timedelta(days=2),
    )
    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=1000,
        reason="small",
        source_type="admin",
        status="available",
        expires_at=now + timedelta(days=3),
        original_expires_at=now + timedelta(days=3),
    )

    revoked_count = service._remove_available_credits(test_student.id, 2000, "reason")
    assert revoked_count == 1


def test_remove_available_credits_remainder_split(db, test_student):
    service = _service(db)
    payment_repo = RepositoryFactory.create_payment_repository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=5000,
        reason="split",
        source_type="admin",
        status="available",
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        original_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    service._remove_available_credits(test_student.id, 2000, "reason")
    remainder = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.reason == f"Remainder of {credit.id}")
        .first()
    )
    assert remainder is not None


def test_remove_available_credits_full_revoke_no_remainder(db, test_student):
    service = _service(db)
    payment_repo = RepositoryFactory.create_payment_repository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=2000,
        reason="full",
        source_type="admin",
        status="available",
        expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        original_expires_at=datetime.now(timezone.utc) + timedelta(days=5),
    )

    revoked_count = service._remove_available_credits(test_student.id, 2000, "reason")
    assert revoked_count == 1
    remainder = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.reason == f"Remainder of {credit.id}")
        .first()
    )
    assert remainder is None


@pytest.mark.asyncio
async def test_execute_credit_adjust_idempotency_branches(db, test_student):
    service = _service(db, idempotency=FakeIdempotency(already_done=True, cached=None))
    preview = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.ADD,
        amount=Decimal("3.00"),
        reason_code="GOODWILL",
        note=None,
        expires_at=None,
        actor_id="admin",
    )
    with pytest.raises(ConflictException):
        await service.execute_credit_adjust(
            student_id=test_student.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )

    cached_payload = {
        "success": True,
        "error": None,
        "student_id": test_student.id,
        "previous_balance": "0.00",
        "new_balance": "0.00",
        "delta": "0.00",
        "credits_created": 0,
        "credits_revoked": 0,
        "audit_id": "audit",
    }
    service = _service(db, idempotency=FakeIdempotency(already_done=True, cached=cached_payload))
    response = await service.execute_credit_adjust(
        student_id=test_student.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert response.student_id == test_student.id


@pytest.mark.asyncio
async def test_execute_credit_adjust_validation_branches(db, test_student):
    service = _service(db, idempotency=FakeIdempotency())
    with pytest.raises(Exception):
        await service.execute_credit_adjust(
            student_id=test_student.id,
            confirm_token="bad",
            idempotency_key="idem",
            actor_id="admin",
        )

    service = _service(db, idempotency=FakeIdempotency())
    service.confirm_service.decode_token = lambda _token: {"payload": "bad"}  # type: ignore[assignment]
    with pytest.raises(ValidationException):
        await service.execute_credit_adjust(
            student_id=test_student.id,
            confirm_token="ctok",
            idempotency_key="idem",
            actor_id="admin",
        )

    service = _service(db, idempotency=FakeIdempotency())
    preview = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.ADD,
        amount=Decimal("3.00"),
        reason_code="GOODWILL",
        note=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        actor_id="admin",
    )

    with pytest.raises(ValidationException):
        await service.execute_credit_adjust(
            student_id=test_student.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key="wrong",
            actor_id="admin",
        )

    with pytest.raises(ValidationException):
        await service.execute_credit_adjust(
            student_id="other",
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )

    service = _service(db, idempotency=BoomIdempotency())
    with pytest.raises(RuntimeError):
        await service.execute_credit_adjust(
            student_id=test_student.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )

    service = _service(db, idempotency=FakeIdempotency())
    preview = service.preview_credit_adjust(
        student_id=test_student.id,
        action=CreditAdjustAction.ADD,
        amount=Decimal("2.00"),
        reason_code="GOODWILL",
        note=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        actor_id="admin",
    )
    response = await service.execute_credit_adjust(
        student_id=test_student.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert response.new_balance == Decimal("2.00")


def test_credit_history_and_refund_history(db, test_student, test_instructor):
    payment_repo = RepositoryFactory.create_payment_repository(db)
    service = _service(db)

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    booking_for_credit = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() - timedelta(days=7),
        start_time=time(8, 0),
        end_time=time(9, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=2,
        max_shifts=120,
    )

    payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=1000,
        reason="available",
        source_type="admin",
        status="available",
    )
    reserved = PlatformCredit(
        id="01RES2",
        user_id=test_student.id,
        amount_cents=500,
        reason="reserved",
        source_type="admin",
        status="reserved",
        reserved_amount_cents=500,
        reserved_for_booking_id=booking_for_credit.id,
        reserved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        original_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    expired = PlatformCredit(
        id="01EXP2",
        user_id=test_student.id,
        amount_cents=700,
        reason="expired",
        source_type="admin",
        status="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        original_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    revoked = PlatformCredit(
        id="01REV",
        user_id=test_student.id,
        amount_cents=800,
        reason="revoked",
        source_type="admin",
        status="revoked",
    )
    revoked.revoked = True
    revoked.revoked_reason = "reason"
    forfeited = PlatformCredit(
        id="01FOR",
        user_id=test_student.id,
        amount_cents=600,
        reason="used",
        source_type="admin",
        status="forfeited",
    )
    forfeited.used_booking_id = booking_for_credit.id
    forfeited.used_at = datetime.now(timezone.utc)

    db.add_all([reserved, expired, revoked, forfeited])
    db.flush()

    credits = service.credit_repo.list_credits_for_user(
        user_id=test_student.id,
        include_expired=True,
    )
    negative_credit = SimpleNamespace(
        id="01NEG",
        amount_cents=-200,
        status="available",
        reason="negative",
        source_type="admin",
        created_at=datetime.now(timezone.utc),
        expires_at=None,
        used_at=None,
        forfeited_at=None,
        revoked_at=None,
        reserved_amount_cents=0,
        reserved_for_booking_id=None,
        used_booking_id=None,
    )
    service.credit_repo.list_credits_for_user = (  # type: ignore[assignment]
        lambda **_kwargs: credits + [negative_credit]
    )

    history = service.credit_history(student_id=test_student.id, include_expired=True)
    assert history.summary.total_earned == Decimal("36.00")
    assert history.summary.total_spent == Decimal("6.00")
    assert history.summary.total_expired == Decimal("7.00")
    assert history.summary.total_forfeited == Decimal("8.00")
    assert history.summary.available_balance == Decimal("10.00")
    assert history.summary.reserved_balance == Decimal("5.00")

    profile = test_instructor.instructor_profile
    svc = _first_service(db, profile.id)
    for idx in range(3):
        booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=svc.id,
            booking_date=date.today() - timedelta(days=idx + 1),
            start_time=time(9 + idx, 0),
            end_time=time(10 + idx, 0),
            service_name="Test",
            hourly_rate=50,
            total_price=50,
            duration_minutes=60,
            status=BookingStatus.CANCELLED,
            meeting_location="Test",
            offset_index=10 + idx,
            max_shifts=120,
        )
        booking.cancelled_at = datetime.now(timezone.utc) - timedelta(days=idx + 1)
        if idx < 2:
            booking.refunded_to_card_amount = 20000
        else:
            booking.student_credit_amount = 20000
        db.flush()

    extra = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() - timedelta(days=5),
        start_time=time(13, 0),
        end_time=time(14, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=20,
        max_shifts=120,
    )
    extra.refunded_to_card_amount = 10000
    extra.updated_at = None
    db.flush()

    old = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=svc.id,
        booking_date=date.today() - timedelta(days=40),
        start_time=time(15, 0),
        end_time=time(16, 0),
        service_name="Test",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CANCELLED,
        meeting_location="Test",
        offset_index=25,
        max_shifts=120,
    )
    old.cancelled_at = datetime.now(timezone.utc) - timedelta(days=40)
    old.refunded_to_card_amount = 5000
    db.flush()

    refunds = service.refund_history(student_id=test_student.id)
    assert refunds.summary.total_refunds == Decimal("750.00")
    assert refunds.fraud_flags.high_refund_rate is True
    assert refunds.fraud_flags.rapid_refunds is True
    assert refunds.fraud_flags.high_refund_amount is True
