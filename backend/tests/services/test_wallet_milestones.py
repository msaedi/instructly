"""Tests for student milestone credit service."""

from datetime import datetime, time, timedelta, timezone

import pytest
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.services.student_credit_service import StudentCreditService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def student(db):
    user = User(
        id=str(ulid.ULID()),
        email=f"student_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Student",
        last_name="Test",
        zip_code="10001",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def instructor_setup(db):
    instructor_user = User(
        id=str(ulid.ULID()),
        email=f"instructor_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Instructor",
        last_name="Test",
        zip_code="10001",
    )
    db.add(instructor_user)
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=instructor_user.id,
        bio="Test instructor",
        years_experience=5,
    )
    db.add(profile)
    db.flush()

    category = ServiceCategory(
        id=str(ulid.ULID()),
        name="Music",
        slug=f"music-{str(ulid.ULID()).lower()}",
        description="Music lessons",
    )
    db.add(category)
    db.flush()

    service_catalog = ServiceCatalog(
        id=str(ulid.ULID()),
        category_id=category.id,
        name="Piano",
        slug=f"piano-{str(ulid.ULID()).lower()}",
        description="Piano lessons",
    )
    db.add(service_catalog)
    db.flush()

    instructor_service = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=service_catalog.id,
        hourly_rate=50.0,
        is_active=True,
    )
    db.add(instructor_service)
    db.flush()

    return instructor_user, instructor_service


def _create_completed_booking(db, student, instructor_service, instructor_id: str, index: int) -> Booking:
    base_date = datetime.now(timezone.utc).date()
    start_hour = 14 + index  # stagger bookings per index to prevent overlaps
    start_time = time(start_hour % 24, 0)
    end_time = (datetime.combine(base_date, start_time) + timedelta(minutes=60)).time()

    booking = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service.id,
        service_name="Piano",
        hourly_rate=50.0,
        total_price=50.0,
        duration_minutes=60,
        booking_date=base_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(base_date, start_time, end_time),
        status=BookingStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc) + timedelta(minutes=index),
    )
    db.add(booking)
    db.flush()
    return booking


def test_milestone_issuance_cycle(db, student, instructor_setup):
    db.query(Booking).delete()
    instructor_user, instructor_service = instructor_setup
    service = StudentCreditService(db)
    payment_repo = PaymentRepository(db)

    issued_bookings = []
    for idx in range(1, 12):
        booking = _create_completed_booking(
            db, student, instructor_service, instructor_user.id, idx
        )
        issued = service.maybe_issue_milestone_credit(
            student_id=student.id, booking_id=booking.id
        )
        db.commit()
        issued_bookings.append((booking, issued))

    fifth_booking, fifth_credit = issued_bookings[4]
    assert fifth_credit is not None
    assert fifth_credit.amount_cents == 1000
    assert fifth_credit.reason == "milestone_s5"

    eleventh_booking, eleventh_credit = issued_bookings[10]
    assert eleventh_credit is not None
    assert eleventh_credit.amount_cents == 2000
    assert eleventh_credit.reason == "milestone_s11"

    # Idempotency
    service.maybe_issue_milestone_credit(student_id=student.id, booking_id=fifth_booking.id)
    service.maybe_issue_milestone_credit(student_id=student.id, booking_id=eleventh_booking.id)
    credits_for_fifth = payment_repo.get_credits_issued_for_source(fifth_booking.id)
    credits_for_eleventh = payment_repo.get_credits_issued_for_source(eleventh_booking.id)
    assert len([c for c in credits_for_fifth if c.reason == "milestone_s5"]) == 1
    assert len([c for c in credits_for_eleventh if c.reason == "milestone_s11"]) == 1


def test_revoke_milestone_credit(db, student, instructor_setup):
    db.query(Booking).delete()
    instructor_user, instructor_service = instructor_setup
    service = StudentCreditService(db)
    payment_repo = PaymentRepository(db)

    bookings = []
    for idx in range(1, 12):
        booking = _create_completed_booking(
            db, student, instructor_service, instructor_user.id, idx
        )
        service.maybe_issue_milestone_credit(student_id=student.id, booking_id=booking.id)
        db.commit()
        bookings.append(booking)

    eleventh_booking = bookings[-1]
    revoked = service.revoke_milestone_credit(source_booking_id=eleventh_booking.id)
    db.commit()
    assert revoked == 2000

    remaining = payment_repo.get_credits_issued_for_source(eleventh_booking.id)
    assert all(c.reason != "milestone_s11" or c.used_at is not None for c in remaining)

    # Re-running is idempotent
    assert service.revoke_milestone_credit(source_booking_id=eleventh_booking.id) == 0


def test_reinstate_used_credits(db, student, instructor_setup):
    db.query(Booking).delete()
    instructor_user, instructor_service = instructor_setup
    service = StudentCreditService(db)
    payment_repo = PaymentRepository(db)

    source_booking = _create_completed_booking(
        db, student, instructor_service, instructor_user.id, 1
    )
    service.issue_milestone_credit(
        student_id=student.id,
        booking_id=source_booking.id,
        amount_cents=1500,
        reason="milestone_s5",
    )
    db.commit()

    booking_date = datetime.now(timezone.utc).date()
    start_time = time(10, 0)
    end_time = time(11, 0)
    refund_booking = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor_user.id,
        instructor_service_id=instructor_service.id,
        service_name="Piano",
        hourly_rate=50.0,
        total_price=50.0,
        duration_minutes=60,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(booking_date, start_time, end_time),
        status=BookingStatus.CONFIRMED,
    )
    db.add(refund_booking)
    db.flush()

    credit_amount = 12 * 100
    payment_repo.apply_credits_for_booking(
        user_id=student.id,
        booking_id=refund_booking.id,
        amount_cents=credit_amount,
    )
    db.commit()

    reinstated = service.reinstate_used_credits(refunded_booking_id=refund_booking.id)
    db.commit()

    assert reinstated == credit_amount
    refund_credits = [
        c for c in payment_repo.get_credits_issued_for_source(refund_booking.id)
        if c.reason == "refund_reinstate"
    ]
    assert len(refund_credits) == 1
    assert refund_credits[0].amount_cents == credit_amount
    assert refund_credits[0].used_at is None

    # Idempotent
    assert service.reinstate_used_credits(refunded_booking_id=refund_booking.id) == 0
