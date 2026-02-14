from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.tests.factories.booking_builders import create_booking_pg_safe
import pytest
import ulid

from app.core.exceptions import (
    ConflictException,
    MCPTokenError,
    NotFoundException,
    ValidationException,
)
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_payment import BookingPayment
from app.models.conversation import Conversation
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.service_catalog import InstructorService as Service
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_instructor_actions import (
    CommissionAction,
    CommissionTier,
    PayoutHoldAction,
    VerificationType,
)
from app.services.instructor_admin_service import (
    InstructorAdminService,
    _booking_amount,
    _cents_to_decimal,
    _normalize_rate,
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


class StubBookingService:
    def __init__(self, db, refund_cents: int = 2500, raise_on: bool = False) -> None:
        self.db = db
        self.refund_cents = refund_cents
        self.raise_on = raise_on

    def cancel_booking(self, booking_id: str, user, reason: str | None = None):
        if self.raise_on:
            raise RuntimeError("cancel failed")
        booking = self.db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            raise ValueError("missing booking")
        booking.status = BookingStatus.CANCELLED
        booking.refunded_to_card_amount = self.refund_cents
        booking.cancelled_at = datetime.now(timezone.utc)
        self.db.flush()
        return booking


def _service(db, *, booking_service=None, idempotency=None) -> InstructorAdminService:
    return InstructorAdminService(
        db,
        booking_service=booking_service,
        idempotency_service=idempotency,
    )


def _profile_for(db, user_id: str) -> InstructorProfile:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()
    if not profile:
        raise AssertionError("Missing profile")
    return profile


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


def _seed_completed_booking(db, *, instructor_id: str, student_id: str, service_id: str, total: float) -> Booking:
    booking_date = date.today() - timedelta(days=2)
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service_id,
        booking_date=booking_date,
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test",
        hourly_rate=total,
        total_price=total,
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
        meeting_location="Test",
        offset_index=5,
        max_shifts=240,
    )
    bp = BookingPayment(id=str(ulid.ULID()), booking_id=booking.id, payment_status=PaymentStatus.AUTHORIZED.value)
    db.add(bp)
    booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    return booking


def test_helper_functions_cover_branches():
    assert _cents_to_decimal(None) == Decimal("0.00")
    assert _normalize_rate(None) == Decimal("0.0000")

    booking_missing = SimpleNamespace(
        total_price=None,
        hourly_rate=None,
        duration_minutes=None,
    )
    assert _booking_amount(booking_missing) == Decimal("0.00")

    booking_calc = SimpleNamespace(
        total_price=None,
        hourly_rate=Decimal("30.00"),
        duration_minutes=90,
    )
    assert _booking_amount(booking_calc) == Decimal("45.00")


def test_load_instructor_missing_user(db, test_instructor, monkeypatch):
    service = _service(db)
    profile = _profile_for(db, test_instructor.id)
    monkeypatch.setattr(service.user_repo, "get_by_id", lambda _id: None)
    with pytest.raises(NotFoundException):
        service._load_instructor(profile.user_id)


def test_tier_mapping_truncates_extra_tiers(db):
    service = _service(db)
    service.config_service.get_pricing_config = lambda: (
        {
            "instructor_tiers": [
                {"min": 0, "pct": 15},
                {"min": 5, "pct": 12},
                {"min": 11, "pct": 10},
                {"min": 20, "pct": 8},
            ]
        },
        None,
    )
    mapping = service._tier_mapping()
    assert mapping["entry"] == Decimal("0.1500")
    assert mapping["growth"] == Decimal("0.1200")
    assert mapping["pro"] == Decimal("0.1000")
    assert "founding" in mapping


def test_current_rate_default_and_custom_tier(db, test_instructor):
    service = _service(db)
    profile = _profile_for(db, test_instructor.id)
    profile.is_founding_instructor = False
    profile.commission_override_pct = None
    profile.commission_override_until = None
    profile.current_tier_pct = None

    default_rate = service._resolve_current_rate(profile)
    assert default_rate == service._tier_mapping().get("entry")

    profile.current_tier_pct = Decimal("13.33")
    assert service._resolve_current_tier(profile) == "custom"


def test_pending_payouts_invalid_payment_values(db, test_instructor, monkeypatch):
    service = _service(db)
    profile = _profile_for(db, test_instructor.id)

    booking_one = SimpleNamespace(
        payment_intent=SimpleNamespace(
            instructor_payout_cents="bad",
            amount=10000,
            application_fee=500,
        ),
        total_price=Decimal("100.00"),
        hourly_rate=None,
        duration_minutes=None,
    )
    booking_two = SimpleNamespace(
        payment_intent=SimpleNamespace(
            instructor_payout_cents=None,
            amount="bad",
            application_fee="fee",
        ),
        total_price=None,
        hourly_rate=Decimal("40.00"),
        duration_minutes=60,
    )

    bookings = [booking_one, booking_two]

    monkeypatch.setattr(
        service.booking_repo,
        "get_instructor_completed_authorized_bookings",
        lambda _id: bookings,
    )
    count, amount = service._pending_payouts("01INS", profile)
    assert count == 2
    assert amount >= Decimal("0.00")


def test_recent_volume_with_completed_booking(db, test_instructor_with_availability, test_student):
    service = _service(db)
    profile = _profile_for(db, test_instructor_with_availability.id)
    svc = _first_service(db, profile.id)

    _seed_completed_booking(
        db,
        instructor_id=test_instructor_with_availability.id,
        student_id=test_student.id,
        service_id=svc.id,
        total=75.0,
    )

    total = service._recent_volume(test_instructor_with_availability.id)
    assert total > Decimal("0.00")


def test_load_instructor_variants(db, test_instructor):
    service = _service(db)
    user, profile = service._load_instructor(test_instructor.id)
    assert user.id == test_instructor.id
    user2, profile2 = service._load_instructor(profile.id)
    assert profile2.id == profile.id
    user3, profile3 = service._load_instructor(test_instructor.email)
    assert user3.id == test_instructor.id
    assert profile3.id == profile.id
    with pytest.raises(NotFoundException):
        service._load_instructor("missing")


def test_ensure_instructor_and_is_verified(db, test_instructor, test_student):
    service = _service(db)
    with pytest.raises(ValidationException):
        service._ensure_instructor(test_student)

    profile = _profile_for(db, test_instructor.id)
    assert service._is_verified(profile) is False
    profile.identity_verified_at = datetime.now(timezone.utc)
    profile.bgc_status = "passed"
    db.add(
        StripeConnectedAccount(
            instructor_profile_id=profile.id,
            stripe_account_id="acct_123",
            onboarding_completed=True,
        )
    )
    db.commit()
    assert service._is_verified(profile) is True


def test_pending_payouts_branches(db, test_instructor_with_availability, test_student):
    profile = _profile_for(db, test_instructor_with_availability.id)
    service = _service(db)
    svc = _first_service(db, profile.id)

    booking_one = _seed_completed_booking(
        db,
        instructor_id=test_instructor_with_availability.id,
        student_id=test_student.id,
        service_id=svc.id,
        total=100.0,
    )
    booking_two = _seed_completed_booking(
        db,
        instructor_id=test_instructor_with_availability.id,
        student_id=test_student.id,
        service_id=svc.id,
        total=80.0,
    )
    booking_three = _seed_completed_booking(
        db,
        instructor_id=test_instructor_with_availability.id,
        student_id=test_student.id,
        service_id=svc.id,
        total=60.0,
    )

    payment_repo = RepositoryFactory.create_payment_repository(db)
    payment_repo.create_payment_record(
        booking_id=booking_one.id,
        payment_intent_id="pi_one",
        amount=10000,
        application_fee=1500,
        status="requires_capture",
        instructor_payout_cents=8500,
    )
    booking_one.payment_intent_id = "pi_one"

    payment_repo.create_payment_record(
        booking_id=booking_two.id,
        payment_intent_id="pi_two",
        amount=8000,
        application_fee=1200,
        status="requires_capture",
    )
    booking_two.payment_intent_id = "pi_two"
    booking_three.payment_intent_id = None
    db.commit()

    count, amount = service._pending_payouts(test_instructor_with_availability.id, profile)
    assert count == 3
    assert amount > Decimal("0.00")


def test_preview_suspend_warnings_and_ineligible_states(db, test_instructor_with_bookings, test_student):
    service = _service(db)
    profile = _profile_for(db, test_instructor_with_bookings.id)
    svc = _first_service(db, profile.id)

    _seed_completed_booking(
        db,
        instructor_id=test_instructor_with_bookings.id,
        student_id=test_student.id,
        service_id=svc.id,
        total=90.0,
    )
    db.add(
        Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_bookings.id,
        )
    )
    db.commit()

    preview = service.preview_suspend(
        instructor_id=test_instructor_with_bookings.id,
        reason_code="FRAUD",
        note="note",
        notify_instructor=True,
        cancel_pending_bookings=False,
        actor_id="admin",
    )
    assert preview.eligible is True
    assert preview.confirm_token
    assert preview.will_cancel_bookings is False
    assert any("Pending bookings will remain active" in msg for msg in preview.warnings)

    user = test_instructor_with_bookings
    user.account_status = "suspended"
    db.commit()
    preview2 = service.preview_suspend(
        instructor_id=user.id,
        reason_code="FRAUD",
        note="note",
        notify_instructor=True,
        cancel_pending_bookings=True,
        actor_id="admin",
    )
    assert preview2.eligible is False
    assert preview2.ineligible_reason == "Already suspended"
    user.account_status = "deactivated"
    db.commit()
    preview3 = service.preview_suspend(
        instructor_id=user.id,
        reason_code="FRAUD",
        note="note",
        notify_instructor=True,
        cancel_pending_bookings=True,
        actor_id="admin",
    )
    assert preview3.ineligible_reason == "Account deactivated"


@pytest.mark.asyncio
async def test_execute_suspend_success_and_errors(db, test_instructor_with_bookings, test_student):
    booking_service = StubBookingService(db)
    idempotency = FakeIdempotency()
    service = _service(db, booking_service=booking_service, idempotency=idempotency)

    preview = service.preview_suspend(
        instructor_id=test_instructor_with_bookings.id,
        reason_code="FRAUD",
        note="note",
        notify_instructor=True,
        cancel_pending_bookings=True,
        actor_id="admin",
    )
    response = await service.execute_suspend(
        instructor_id=test_instructor_with_bookings.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert response.success is True
    assert response.bookings_cancelled == 1
    assert response.refunds_issued == 1
    assert response.total_refunded > Decimal("0.00")

    with pytest.raises(ValidationException):
        await service.execute_suspend(
            instructor_id=test_instructor_with_bookings.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key="mismatch",
            actor_id="admin",
        )

    test_instructor_with_bookings.account_status = "suspended"
    db.commit()
    with pytest.raises(ValidationException):
        await service.execute_suspend(
            instructor_id=test_instructor_with_bookings.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key=preview.idempotency_key or "",
            actor_id="admin",
        )

    cached = {
        "success": True,
        "error": None,
        "instructor_id": test_instructor_with_bookings.id,
        "previous_status": "active",
        "new_status": "suspended",
        "bookings_cancelled": 0,
        "refunds_issued": 0,
        "total_refunded": "0.00",
        "notifications_sent": [],
        "audit_id": "audit",
    }
    idempotency_done = FakeIdempotency(already_done=True, cached=cached)
    service_cached = _service(db, booking_service=booking_service, idempotency=idempotency_done)
    cached_response = await service_cached.execute_suspend(
        instructor_id=test_instructor_with_bookings.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert cached_response.audit_id == "audit"

    test_instructor_with_bookings.account_status = "active"
    db.commit()

    profile = _profile_for(db, test_instructor_with_bookings.id)
    svc = _first_service(db, profile.id)
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_bookings.id,
        instructor_service_id=svc.id,
        booking_date=date.today() + timedelta(days=2),
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name="Test",
        hourly_rate=svc.hourly_rate,
        total_price=float(svc.hourly_rate),
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        offset_index=30,
        cancel_duplicate=True,
    )
    db.commit()

    error_service = _service(db, booking_service=StubBookingService(db, raise_on=True))
    preview2 = error_service.preview_suspend(
        instructor_id=test_instructor_with_bookings.id,
        reason_code="FRAUD",
        note="note",
        notify_instructor=True,
        cancel_pending_bookings=True,
        actor_id="admin",
    )
    result = await error_service.execute_suspend(
        instructor_id=test_instructor_with_bookings.id,
        confirm_token=preview2.confirm_token or "",
        idempotency_key=preview2.idempotency_key or "",
        actor_id="admin",
    )
    assert result.success is False
    assert result.error == "cancel_pending_bookings_failed"


@pytest.mark.asyncio
async def test_execute_suspend_token_and_idempotency_errors(db, test_instructor):
    service = _service(db)
    with pytest.raises(MCPTokenError):
        await service.execute_suspend(
            instructor_id=test_instructor.id,
            confirm_token="invalid",
            idempotency_key="idem-token",
            actor_id="admin",
        )

    bad_token = service.confirm_service._b64encode({"payload": []})
    with pytest.raises(ValidationException):
        await service.execute_suspend(
            instructor_id=test_instructor.id,
            confirm_token=bad_token,
            idempotency_key="idem-bad",
            actor_id="admin",
        )

    payload = {
        "instructor_id": test_instructor.id,
        "reason_code": "FRAUD",
        "note": "note",
        "notify_instructor": True,
        "cancel_pending_bookings": False,
        "idempotency_key": "idem-mismatch",
    }
    token, _ = service.confirm_service.generate_token(payload, actor_id="admin")
    with pytest.raises(ValidationException):
        await service.execute_suspend(
            instructor_id="other",
            confirm_token=token,
            idempotency_key="idem-mismatch",
            actor_id="admin",
        )

    boom_service = _service(db, idempotency=BoomIdempotency())
    boom_token, _ = boom_service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "reason_code": "FRAUD",
            "note": "note",
            "notify_instructor": True,
            "cancel_pending_bookings": False,
            "idempotency_key": "idem-boom",
        },
        actor_id="admin",
    )
    with pytest.raises(RuntimeError):
        await boom_service.execute_suspend(
            instructor_id=test_instructor.id,
            confirm_token=boom_token,
            idempotency_key="idem-boom",
            actor_id="admin",
        )

    conflict_service = _service(db, idempotency=FakeIdempotency(already_done=True, cached=None))
    conflict_token, _ = conflict_service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "reason_code": "FRAUD",
            "note": "note",
            "notify_instructor": True,
            "cancel_pending_bookings": False,
            "idempotency_key": "idem-conflict",
        },
        actor_id="admin",
    )
    with pytest.raises(ConflictException):
        await conflict_service.execute_suspend(
            instructor_id=test_instructor.id,
            confirm_token=conflict_token,
            idempotency_key="idem-conflict",
            actor_id="admin",
        )


def test_unsuspend_and_payout_hold(db, test_instructor):
    service = _service(db)
    profile = _profile_for(db, test_instructor.id)
    test_instructor.account_status = "suspended"
    profile.is_live = False
    profile.payout_hold = True
    db.commit()

    response = service.unsuspend(
        instructor_id=test_instructor.id,
        reason="cleared",
        restore_visibility=True,
        actor_id="admin",
    )
    assert response.visibility_restored is True
    assert response.payout_hold_released is True

    with pytest.raises(ValidationException):
        service.unsuspend(
            instructor_id=test_instructor.id,
            reason="no",
            restore_visibility=True,
            actor_id="admin",
        )

    hold = service.payout_hold(
        instructor_id=test_instructor.id,
        action=PayoutHoldAction.HOLD,
        reason="hold",
        actor_id="admin",
    )
    assert hold.action == "HOLD"
    release = service.payout_hold(
        instructor_id=test_instructor.id,
        action=PayoutHoldAction.RELEASE,
        reason="release",
        actor_id="admin",
    )
    assert release.held_amount == Decimal("0.00")


def test_verify_override_and_missing_account(db, test_instructor):
    service = _service(db)
    profile = _profile_for(db, test_instructor.id)
    payment_repo = RepositoryFactory.create_payment_repository(db)
    payment_repo.create_connected_account_record(
        instructor_profile_id=profile.id,
        stripe_account_id="acct_789",
        onboarding_completed=False,
    )
    db.commit()

    response = service.verify_override(
        instructor_id=test_instructor.id,
        verification_type=VerificationType.FULL,
        reason="manual",
        evidence=None,
        actor_id="admin",
    )
    assert response.success is True
    assert response.now_fully_verified is True

    connected = payment_repo.get_connected_account_by_instructor_id(profile.id)
    if connected:
        db.delete(connected)
        db.commit()

    other_service = _service(db)
    with pytest.raises(ValidationException):
        other_service.verify_override(
            instructor_id=test_instructor.id,
            verification_type=VerificationType.PAYMENT_SETUP,
            reason="manual",
            evidence=None,
            actor_id="admin",
        )


def test_preview_update_commission_variants(db, test_instructor):
    service = _service(db)
    profile = _profile_for(db, test_instructor.id)

    preview = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.SET_TIER,
        tier=CommissionTier.ENTRY,
        temporary_rate=None,
        temporary_until=None,
        reason="set",
        actor_id="admin",
    )
    assert preview.eligible is True
    assert preview.new_tier == "entry"

    preview_missing = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.SET_TIER,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="set",
        actor_id="admin",
    )
    assert preview_missing.eligible is False

    profile.is_founding_instructor = True
    db.commit()
    preview_founding = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.SET_TIER,
        tier=CommissionTier.GROWTH,
        temporary_rate=None,
        temporary_until=None,
        reason="set",
        actor_id="admin",
    )
    assert preview_founding.eligible is False

    preview_already = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.GRANT_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="grant",
        actor_id="admin",
    )
    assert preview_already.eligible is False

    profile.is_founding_instructor = False
    db.commit()
    service.profile_repo.count_founding_instructors = lambda: 100
    service.config_service.get_pricing_config = lambda: ({"founding_instructor_cap": 100}, None)
    preview_cap = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.GRANT_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="grant",
        actor_id="admin",
    )
    assert preview_cap.eligible is False
    assert any("Founding cap reached" in msg for msg in preview_cap.warnings)

    preview_revoke = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.REVOKE_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="revoke",
        actor_id="admin",
    )
    assert preview_revoke.eligible is False

    profile.is_founding_instructor = True
    db.commit()
    preview_revoke2 = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.REVOKE_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="revoke",
        actor_id="admin",
    )
    assert preview_revoke2.eligible is True

    profile.is_founding_instructor = False
    db.commit()
    preview_temp_missing = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.TEMPORARY_DISCOUNT,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="temp",
        actor_id="admin",
    )
    assert preview_temp_missing.eligible is False

    profile.is_founding_instructor = True
    db.commit()
    preview_temp_founding = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.TEMPORARY_DISCOUNT,
        tier=None,
        temporary_rate=Decimal("0.05"),
        temporary_until=None,
        reason="temp",
        actor_id="admin",
    )
    assert preview_temp_founding.eligible is False

    profile.is_founding_instructor = False
    db.commit()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    preview_temp_past = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.TEMPORARY_DISCOUNT,
        tier=None,
        temporary_rate=Decimal("0.05"),
        temporary_until=past,
        reason="temp",
        actor_id="admin",
    )
    assert preview_temp_past.eligible is False

    preview_invalid = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.TEMPORARY_DISCOUNT,
        tier=None,
        temporary_rate=Decimal("-0.1"),
        temporary_until=None,
        reason="temp",
        actor_id="admin",
    )
    assert preview_invalid.eligible is False


def test_preview_update_commission_invalid_cap(db, test_instructor):
    service = _service(db)
    service.config_service.get_pricing_config = lambda: ({"founding_instructor_cap": "bad"}, None)
    service.profile_repo.count_founding_instructors = lambda: 0
    preview = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.GRANT_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="grant",
        actor_id="admin",
    )
    assert preview.eligible is True
    assert preview.new_tier == "founding"


@pytest.mark.asyncio
async def test_execute_update_commission_variants(db, test_instructor):
    service = _service(db, idempotency=FakeIdempotency())
    profile = _profile_for(db, test_instructor.id)

    preview = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.SET_TIER,
        tier=CommissionTier.GROWTH,
        temporary_rate=None,
        temporary_until=None,
        reason="tier",
        actor_id="admin",
    )
    result = await service.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert result.new_tier == "growth"

    service.profile_repo.try_claim_founding_status = lambda _pid, _cap: (True, 1)
    preview_founding = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.GRANT_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="grant",
        actor_id="admin",
    )
    result_founding = await service.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=preview_founding.confirm_token or "",
        idempotency_key=preview_founding.idempotency_key or "",
        actor_id="admin",
    )
    assert result_founding.new_tier == "founding"

    profile.is_founding_instructor = True
    db.commit()
    preview_revoke = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.REVOKE_FOUNDING,
        tier=None,
        temporary_rate=None,
        temporary_until=None,
        reason="revoke",
        actor_id="admin",
    )
    result_revoke = await service.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=preview_revoke.confirm_token or "",
        idempotency_key=preview_revoke.idempotency_key or "",
        actor_id="admin",
    )
    assert result_revoke.founding_status_changed is True

    preview_temp = service.preview_update_commission(
        instructor_id=test_instructor.id,
        action=CommissionAction.TEMPORARY_DISCOUNT,
        tier=None,
        temporary_rate=Decimal("0.07"),
        temporary_until=None,
        reason="temp",
        actor_id="admin",
    )
    result_temp = await service.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=preview_temp.confirm_token or "",
        idempotency_key=preview_temp.idempotency_key or "",
        actor_id="admin",
    )
    assert result_temp.new_tier == "temporary_discount"

    cached = {
        "success": True,
        "error": None,
        "instructor_id": test_instructor.id,
        "previous_tier": "entry",
        "new_tier": "growth",
        "previous_rate": "0.15",
        "new_rate": "0.12",
        "founding_status_changed": False,
        "audit_id": "audit",
    }
    idempotency_done = FakeIdempotency(already_done=True, cached=cached)
    service_cached = _service(db, idempotency=idempotency_done)
    cached_response = await service_cached.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=preview.confirm_token or "",
        idempotency_key=preview.idempotency_key or "",
        actor_id="admin",
    )
    assert cached_response.audit_id == "audit"

    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=preview.confirm_token or "",
            idempotency_key="bad",
            actor_id="admin",
        )

    confirm_service = service.confirm_service
    token, _expires = confirm_service.generate_token(
        {"instructor_id": test_instructor.id, "action": "SET_TIER", "idempotency_key": "x"},
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token,
            idempotency_key="x",
            actor_id="admin",
        )

    token_temp, _ = confirm_service.generate_token(
        {"instructor_id": test_instructor.id, "action": "TEMPORARY_DISCOUNT", "idempotency_key": "y"},
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token_temp,
            idempotency_key="y",
            actor_id="admin",
        )

    profile.is_founding_instructor = True
    db.commit()
    token_founding, _ = confirm_service.generate_token(
        {"instructor_id": test_instructor.id, "action": "GRANT_FOUNDING", "idempotency_key": "z"},
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token_founding,
            idempotency_key="z",
            actor_id="admin",
        )

    profile.is_founding_instructor = False
    db.commit()
    token_revoke, _ = confirm_service.generate_token(
        {"instructor_id": test_instructor.id, "action": "REVOKE_FOUNDING", "idempotency_key": "k"},
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token_revoke,
            idempotency_key="k",
            actor_id="admin",
        )


@pytest.mark.asyncio
async def test_execute_update_commission_token_and_idempotency_errors(db, test_instructor):
    service = _service(db)
    with pytest.raises(MCPTokenError):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token="invalid",
            idempotency_key="idem-token",
            actor_id="admin",
        )

    bad_token = service.confirm_service._b64encode({"payload": []})
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=bad_token,
            idempotency_key="idem-bad",
            actor_id="admin",
        )

    payload = {
        "instructor_id": test_instructor.id,
        "action": "SET_TIER",
        "tier": "entry",
        "idempotency_key": "idem-mismatch",
    }
    token, _ = service.confirm_service.generate_token(payload, actor_id="admin")
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id="other",
            confirm_token=token,
            idempotency_key="idem-mismatch",
            actor_id="admin",
        )

    boom_service = _service(db, idempotency=BoomIdempotency())
    boom_token, _ = boom_service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "SET_TIER",
            "tier": "entry",
            "idempotency_key": "idem-boom",
        },
        actor_id="admin",
    )
    with pytest.raises(RuntimeError):
        await boom_service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=boom_token,
            idempotency_key="idem-boom",
            actor_id="admin",
        )

    conflict_service = _service(db, idempotency=FakeIdempotency(already_done=True, cached=None))
    conflict_token, _ = conflict_service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "SET_TIER",
            "tier": "entry",
            "idempotency_key": "idem-conflict",
        },
        actor_id="admin",
    )
    with pytest.raises(ConflictException):
        await conflict_service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=conflict_token,
            idempotency_key="idem-conflict",
            actor_id="admin",
        )


@pytest.mark.asyncio
async def test_execute_update_commission_founding_and_temp_paths(db, test_instructor):
    profile = _profile_for(db, test_instructor.id)
    service = _service(db, idempotency=FakeIdempotency())

    profile.is_founding_instructor = True
    db.commit()
    token_immune, _ = service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "SET_TIER",
            "tier": "growth",
            "idempotency_key": "idem-immune",
        },
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token_immune,
            idempotency_key="idem-immune",
            actor_id="admin",
        )

    profile.is_founding_instructor = False
    db.commit()
    service.config_service.get_pricing_config = lambda: ({"founding_instructor_cap": "bad"}, None)
    service.profile_repo.try_claim_founding_status = lambda _pid, _cap: (True, 1)
    token_cap, _ = service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "GRANT_FOUNDING",
            "idempotency_key": "idem-cap",
        },
        actor_id="admin",
    )
    result = await service.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=token_cap,
        idempotency_key="idem-cap",
        actor_id="admin",
    )
    assert result.new_tier == "founding"

    service.config_service.get_pricing_config = lambda: ({"founding_instructor_cap": 100}, None)
    service.profile_repo.try_claim_founding_status = lambda _pid, _cap: (False, 100)
    token_denied, _ = service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "GRANT_FOUNDING",
            "idempotency_key": "idem-denied",
        },
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token_denied,
            idempotency_key="idem-denied",
            actor_id="admin",
        )

    profile.is_founding_instructor = True
    db.commit()
    token_temp, _ = service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "TEMPORARY_DISCOUNT",
            "temporary_rate": "0.07",
            "idempotency_key": "idem-temp",
        },
        actor_id="admin",
    )
    with pytest.raises(ValidationException):
        await service.execute_update_commission(
            instructor_id=test_instructor.id,
            confirm_token=token_temp,
            idempotency_key="idem-temp",
            actor_id="admin",
        )

    profile.is_founding_instructor = False
    db.commit()
    token_bad_until, _ = service.confirm_service.generate_token(
        {
            "instructor_id": test_instructor.id,
            "action": "TEMPORARY_DISCOUNT",
            "temporary_rate": "0.07",
            "temporary_until": "not-a-date",
            "idempotency_key": "idem-bad-until",
        },
        actor_id="admin",
    )
    result_bad_until = await service.execute_update_commission(
        instructor_id=test_instructor.id,
        confirm_token=token_bad_until,
        idempotency_key="idem-bad-until",
        actor_id="admin",
    )
    assert result_bad_until.new_tier == "temporary_discount"
    assert profile.commission_override_until is None
