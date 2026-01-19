"""
Integration tests for credit reservation ordering by expiration.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PlatformCredit
from app.models.service_catalog import InstructorService
from app.repositories.payment_repository import PaymentRepository
from app.services.credit_service import CreditService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _get_service(db: Session, instructor: Any) -> InstructorService:
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


def _create_booking(db: Session, *, student_id: str, instructor_id: str, service: InstructorService) -> str:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Credit FIFO",
        hourly_rate=float(service.hourly_rate or 100.0),
        total_price=float(service.hourly_rate or 100.0),
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
    )
    db.flush()
    return booking.id


def _create_credit(
    db: Session,
    *,
    user_id: str,
    amount_cents: int,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> PlatformCredit:
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=user_id,
        amount_cents=amount_cents,
        reason="test_credit",
        source_type="promo",
        expires_at=expires_at,
        status="available",
    )
    if created_at is not None:
        credit.created_at = created_at
    db.flush()
    return credit


def test_earlier_expiring_credit_used_first(db: Session, test_student, test_instructor) -> None:
    service = _get_service(db, test_instructor)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        service=service,
    )

    now = datetime.now(timezone.utc)
    credit_30d = _create_credit(
        db,
        user_id=test_student.id,
        amount_cents=5000,
        created_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=30),
    )
    credit_7d = _create_credit(
        db,
        user_id=test_student.id,
        amount_cents=5000,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )

    credit_service = CreditService(db)
    reserved_total = credit_service.reserve_credits_for_booking(
        user_id=test_student.id,
        booking_id=booking_id,
        max_amount_cents=3000,
    )
    assert reserved_total == 3000

    db.refresh(credit_30d)
    db.refresh(credit_7d)
    assert credit_7d.status == "reserved"
    assert credit_7d.reserved_amount_cents == 3000
    assert credit_30d.status == "available"
    assert credit_30d.reserved_amount_cents == 0

    remainder = (
        db.query(PlatformCredit)
        .filter(PlatformCredit.reason == f"Remainder of {credit_7d.id}")
        .first()
    )
    assert remainder is not None
    assert remainder.status == "available"
    assert remainder.amount_cents == 2000


def test_null_expiration_used_last(db: Session, test_student, test_instructor) -> None:
    service = _get_service(db, test_instructor)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        service=service,
    )

    now = datetime.now(timezone.utc)
    credit_expires = _create_credit(
        db,
        user_id=test_student.id,
        amount_cents=5000,
        expires_at=now + timedelta(days=365),
    )
    credit_no_expiry = _create_credit(
        db,
        user_id=test_student.id,
        amount_cents=5000,
        expires_at=None,
    )

    credit_service = CreditService(db)
    reserved_total = credit_service.reserve_credits_for_booking(
        user_id=test_student.id,
        booking_id=booking_id,
        max_amount_cents=3000,
    )
    assert reserved_total == 3000

    db.refresh(credit_expires)
    db.refresh(credit_no_expiry)
    assert credit_expires.status == "reserved"
    assert credit_expires.reserved_amount_cents == 3000
    assert credit_no_expiry.status == "available"
    assert credit_no_expiry.reserved_amount_cents == 0
