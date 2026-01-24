"""Integration tests for dispute resolution outcomes."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentIntent
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_booking_with_payment(
    db: Session, *, student: User, instructor: User, payment_intent_id: str
) -> Booking:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor.instructor_profile.instructor_services[0].id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=(start_dt + timedelta(hours=1)).time(),
        service_name="Dispute Resolution",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
        meeting_location="Test",
        location_type="neutral_location",
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
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


def test_dispute_lost_revokes_credits(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_booking_with_payment(
        db, student=test_student, instructor=test_instructor, payment_intent_id="pi_lost"
    )
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=5000,
        reason="cancel_credit_12_24",
        source_type="cancel_credit_12_24",
        source_booking_id=booking.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        status="frozen",
    )
    credit.frozen_at = datetime.now(timezone.utc)
    db.commit()

    stripe_service = StripeService(
        db, config_service=ConfigService(db), pricing_service=PricingService(db)
    )
    event = {
        "type": "charge.dispute.closed",
        "data": {"object": {"id": "dp_lost", "payment_intent": "pi_lost", "status": "lost"}},
    }
    stripe_service._handle_dispute_closed(event)

    db.refresh(credit)
    db.refresh(test_student)
    db.refresh(booking)
    assert credit.status == "revoked"
    assert credit.revoked_at is not None
    assert test_student.account_restricted is True
    assert booking.settlement_outcome == "student_wins_dispute_full_refund"


def test_dispute_won_unfreezes_credits_and_clears_negative_balance(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_booking_with_payment(
        db, student=test_student, instructor=test_instructor, payment_intent_id="pi_won"
    )
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=5000,
        reason="cancel_credit_12_24",
        source_type="cancel_credit_12_24",
        source_booking_id=booking.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        status="frozen",
    )
    credit.frozen_at = datetime.now(timezone.utc)
    test_student.credit_balance_cents = -5000
    test_student.account_restricted = True
    test_student.account_restricted_reason = "dispute_opened:dp_won"
    payment_repo.create_payment_event(
        booking_id=booking.id,
        event_type="negative_balance_applied",
        event_data={"dispute_id": "dp_won", "amount_cents": 5000},
    )
    db.commit()

    stripe_service = StripeService(
        db, config_service=ConfigService(db), pricing_service=PricingService(db)
    )
    event = {
        "type": "charge.dispute.closed",
        "data": {"object": {"id": "dp_won", "payment_intent": "pi_won", "status": "won"}},
    }
    stripe_service._handle_dispute_closed(event)

    db.refresh(credit)
    db.refresh(test_student)
    db.refresh(booking)
    assert credit.status == "available"
    assert test_student.credit_balance_cents >= 0
    assert test_student.account_restricted is False
    assert booking.settlement_outcome == "dispute_won"
