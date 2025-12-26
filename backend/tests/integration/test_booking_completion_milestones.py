"""Integration tests for student milestone credits during booking lifecycle."""

import asyncio
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
import ulid

from app.core.enums import RoleName
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.booking_repository import BookingRepository
from app.repositories.payment_repository import PaymentRepository
from app.services.booking_service import BookingService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def milestone_setup(db):
    student = User(
        id=str(ulid.ULID()),
        email=f"student_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Student",
        last_name="Lifecycle",
        zip_code="10001",
    )
    instructor = User(
        id=str(ulid.ULID()),
        email=f"instructor_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Instructor",
        last_name="Lifecycle",
        zip_code="10001",
    )
    db.add_all([student, instructor])
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=instructor.id,
        bio="Lifecycle instructor",
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

    catalog = ServiceCatalog(
        id=str(ulid.ULID()),
        category_id=category.id,
        name="Piano",
        slug=f"piano-{str(ulid.ULID()).lower()}",
        description="Piano lessons",
    )
    db.add(catalog)
    db.flush()

    instructor_service = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=55.0,
        is_active=True,
    )
    db.add(instructor_service)
    db.flush()

    return student, instructor, instructor_service


def _new_confirmed_booking(student: User, instructor: User, instructor_service: InstructorService, offset: int) -> Booking:
    booking_date = (datetime.now(timezone.utc) - timedelta(days=offset)).date()
    start_time = time(12, 0)
    end_time = time(13, 0)
    booking = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor_service.id,
        service_name="Piano",
        hourly_rate=instructor_service.hourly_rate,
        total_price=55.0,
        duration_minutes=60,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(booking_date, start_time, end_time),
        status=BookingStatus.CONFIRMED,
    )
    return booking


@pytest.mark.asyncio
async def test_booking_completion_milestones_flow(db, milestone_setup):
    student, instructor, instructor_service = milestone_setup
    payment_repo = PaymentRepository(db)
    booking_service = BookingService(db)
    booking_repo = BookingRepository(db)
    instructor_actor = SimpleNamespace(
        id=instructor.id, roles=[SimpleNamespace(name=RoleName.INSTRUCTOR)]
    )

    # Create 11 bookings in confirmed state
    bookings: list[Booking] = []
    for idx in range(11):
        booking = _new_confirmed_booking(student, instructor, instructor_service, idx + 2)
        db.add(booking)
        bookings.append(booking)
    db.commit()

    # Mark each booking as completed via service
    for index, booking in enumerate(bookings, start=1):
        booking_service.complete_booking(booking.id, instructor_actor)
        db.commit()
        if index == 5:
            credits = payment_repo.get_credits_issued_for_source(booking.id)
            assert len([c for c in credits if c.reason == "milestone_s5"]) == 1
        if index == 11:
            credits = payment_repo.get_credits_issued_for_source(booking.id)
            assert len([c for c in credits if c.reason == "milestone_s11"]) == 1
            eleventh_booking = booking

    # Simulate cancellation of the 11th session after issuance
    booking_repo.update(eleventh_booking.id, status=BookingStatus.CONFIRMED, completed_at=None)
    db.commit()
    await asyncio.to_thread(booking_service.cancel_booking, eleventh_booking.id, instructor_actor)
    db.commit()

    revoked_credits = payment_repo.get_credits_issued_for_source(eleventh_booking.id)
    assert all(c.reason != "milestone_s11" or c.used_at is not None for c in revoked_credits)

    # Create booking that consumes credits and then gets cancelled (refund scenario)
    refund_booking = _new_confirmed_booking(student, instructor, instructor_service, 0)
    db.add(refund_booking)
    db.commit()

    payment_repo.apply_credits_for_booking(
        user_id=student.id,
        booking_id=refund_booking.id,
        amount_cents=600,
    )
    db.commit()

    await asyncio.to_thread(booking_service.cancel_booking, refund_booking.id, student)
    db.commit()

    reinstated = [
        c for c in payment_repo.get_credits_issued_for_source(refund_booking.id)
        if c.reason == "refund_reinstate"
    ]
    assert len(reinstated) == 1
    assert reinstated[0].amount_cents == 600
    assert reinstated[0].used_at is None
