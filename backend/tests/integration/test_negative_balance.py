"""Integration tests for negative balance mechanics on disputes."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session
import ulid

from app.core.exceptions import BusinessRuleException
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _get_service(db: Session, instructor: User) -> InstructorService:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    if not profile:
        raise RuntimeError("Instructor profile not found")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active.is_(True),
        )
        .first()
    )
    if not service:
        raise RuntimeError("Instructor service not found")
    return service


def _create_booking_with_payment(
    db: Session, *, student: User, instructor: User, payment_intent_id: str
) -> Booking:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor.instructor_profile.instructor_services[0].id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=(start_dt + timedelta(hours=1)).time(),
        service_name="Negative Balance",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.SETTLED.value,
        payment_intent_id=payment_intent_id,
    )
    payment_record = PaymentIntent(
        id=str(ulid.ULID()),
        booking_id=booking.id,
        stripe_payment_intent_id=payment_intent_id,
        amount=10000,
        application_fee=0,
        status="succeeded",
        instructor_payout_cents=8800,
    )
    db.add(payment_record)
    db.commit()
    return booking


def test_dispute_with_unspent_credits_freezes_only(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_booking_with_payment(
        db, student=test_student, instructor=test_instructor, payment_intent_id="pi_dispute1"
    )
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=5000,
        reason="cancel_credit_12_24",
        source_type="cancel_credit_12_24",
        source_booking_id=booking.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.commit()

    stripe_service = StripeService(
        db, config_service=ConfigService(db), pricing_service=PricingService(db)
    )
    event = {
        "type": "charge.dispute.created",
        "data": {"object": {"id": "dp_1", "payment_intent": "pi_dispute1", "status": "needs_response", "amount": 5000}},
    }
    stripe_service._handle_dispute_created(event)

    db.refresh(booking)
    db.refresh(test_student)
    db.refresh(credit)
    assert booking.payment_status == PaymentStatus.MANUAL_REVIEW.value
    assert credit.status == "frozen"
    assert test_student.credit_balance_cents == 0
    assert getattr(test_student, "account_restricted", False) is False


def test_dispute_with_spent_credits_creates_negative_balance(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_booking_with_payment(
        db, student=test_student, instructor=test_instructor, payment_intent_id="pi_dispute2"
    )
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=4000,
        reason="cancel_credit_12_24",
        source_type="cancel_credit_12_24",
        source_booking_id=booking.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        status="forfeited",
    )
    db.commit()

    stripe_service = StripeService(
        db, config_service=ConfigService(db), pricing_service=PricingService(db)
    )
    event = {
        "type": "charge.dispute.created",
        "data": {"object": {"id": "dp_2", "payment_intent": "pi_dispute2", "status": "needs_response", "amount": 4000}},
    }
    stripe_service._handle_dispute_created(event)

    db.refresh(test_student)
    db.refresh(credit)
    assert credit.status == "forfeited"
    assert test_student.credit_balance_cents == -4000
    assert test_student.account_restricted is True


def test_negative_balance_blocks_new_bookings(
    db: Session, test_student: User, test_instructor: User
) -> None:
    test_student.credit_balance_cents = -1000
    db.commit()

    service = _get_service(db, test_instructor)
    booking_data = BookingCreate(
        instructor_id=test_instructor.id,
        instructor_service_id=service.id,
        booking_date=datetime.now(timezone.utc).date() + timedelta(days=3),
        start_time=(
            datetime.now(timezone.utc)
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .time()
        ),
        selected_duration=60,
        student_note=None,
        meeting_location="Test",
        location_type="neutral",
    )
    booking_service = BookingService(db)
    with pytest.raises(BusinessRuleException):
        booking_service._validate_booking_prerequisites(test_student, booking_data)
