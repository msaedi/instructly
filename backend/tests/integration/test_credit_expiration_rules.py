"""Integration tests for credit expiration rules."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.booking import BookingStatus
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.services.credit_service import CreditService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_booking(db: Session, *, student: User, instructor: User) -> str:
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
        service_name="Credit Expiration",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
    )
    db.commit()
    return booking.id


def test_new_credit_expires_in_one_year(db: Session, test_student: User) -> None:
    credit_service = CreditService(db)
    now = datetime.now(timezone.utc)
    credit = credit_service.issue_credit(
        user_id=test_student.id,
        amount_cents=5000,
        source_type="test_credit",
        reason="test",
        use_transaction=True,
    )
    assert credit is not None
    expected = now + timedelta(days=365)
    assert abs((credit.expires_at - expected).total_seconds()) < 120


def test_reserved_credit_not_expired(db: Session, test_student: User, test_instructor: User) -> None:
    booking_id = _create_booking(db, student=test_student, instructor=test_instructor)
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=3000,
        reason="test_credit",
        source_type="promo",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="available",
    )
    db.commit()

    credit_service = CreditService(db)
    credit_service.reserve_credits_for_booking(
        user_id=test_student.id,
        booking_id=booking_id,
        max_amount_cents=3000,
        use_transaction=True,
    )

    db.refresh(credit)
    assert credit.status == "reserved"

    credit.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    credit_service.expire_old_credits(use_transaction=True)
    db.refresh(credit)
    assert credit.status == "reserved"


def test_released_credit_keeps_original_expiration(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking_id = _create_booking(db, student=test_student, instructor=test_instructor)
    payment_repo = PaymentRepository(db)
    original_expiry = datetime.now(timezone.utc) + timedelta(days=30)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=2000,
        reason="test_credit",
        source_type="promo",
        expires_at=original_expiry,
        status="available",
    )
    db.commit()

    credit_service = CreditService(db)
    credit_service.reserve_credits_for_booking(
        user_id=test_student.id,
        booking_id=booking_id,
        max_amount_cents=2000,
        use_transaction=True,
    )
    credit_service.release_credits_for_booking(booking_id=booking_id, use_transaction=True)

    db.refresh(credit)
    assert credit.status == "available"
    assert credit.expires_at == original_expiry


def test_available_credit_expires(db: Session, test_student: User) -> None:
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=test_student.id,
        amount_cents=1500,
        reason="test_credit",
        source_type="promo",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        status="available",
    )
    db.commit()

    credit_service = CreditService(db)
    credit_service.expire_old_credits(use_transaction=True)

    db.refresh(credit)
    assert credit.status == "expired"
