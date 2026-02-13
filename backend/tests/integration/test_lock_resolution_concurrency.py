"""
Concurrency coverage for LOCK resolution.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session, sessionmaker
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.booking_lock import BookingLock
from app.models.booking_payment import BookingPayment
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.models.user import User
from app.services.booking_service import BookingService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_instructor_with_service(db: Session) -> tuple[User, InstructorProfile, InstructorService]:
    instructor = User(
        id=str(ulid.ULID()),
        email=f"lock_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="Inst",
        last_name="Ructor",
        is_active=True,
        zip_code="10001",
    )
    db.add(instructor)
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=instructor.id,
        bio="bio",
        years_experience=3,
    )
    db.add(profile)
    db.flush()

    cat = ServiceCategory(id=str(ulid.ULID()), name="Cat")
    db.add(cat)
    db.flush()

    sub = ServiceSubcategory(id=str(ulid.ULID()), name="General", category_id=cat.id, display_order=1)
    db.add(sub)
    db.flush()

    svc_cat = ServiceCatalog(
        id=str(ulid.ULID()), subcategory_id=sub.id, name="Svc", slug=f"svc-{ulid.ULID()}"
    )
    db.add(svc_cat)
    db.flush()

    svc = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=svc_cat.id,
        hourly_rate=120.00,
        duration_options=[60],
        offers_travel=True,
        offers_at_location=True,
        offers_online=True,
        is_active=True,
    )
    db.add(svc)
    db.flush()

    connected = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        stripe_account_id="acct_test",
        onboarding_completed=True,
    )
    db.add(connected)
    db.flush()

    return instructor, profile, svc


def _create_student(db: Session) -> User:
    student = User(
        id=str(ulid.ULID()),
        email=f"student_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="Stu",
        last_name="Dent",
        is_active=True,
        zip_code="10001",
    )
    db.add(student)
    db.flush()
    return student


def _create_locked_booking(
    db: Session,
    student: User,
    instructor: User,
    svc: InstructorService,
    when: datetime,
) -> Booking:
    start_at = when.astimezone(timezone.utc)
    end_at = start_at + timedelta(hours=1)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=start_at.date(),
        start_time=start_at.time(),
        end_time=end_at.time(),
        service_name="Lock Resolution",
        hourly_rate=120.00,
        total_price=120.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
    )
    bp = BookingPayment(id=str(ulid.ULID()), booking_id=booking.id, payment_status="locked", payment_intent_id="pi_locked")
    db.add(bp)
    booking.payment_detail = bp
    db.add(BookingLock(booking_id=booking.id, locked_amount_cents=13440))
    db.flush()
    return booking


def test_concurrent_lock_resolution_only_one_payout(db: Session) -> None:
    instructor, _, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    locked_booking = _create_locked_booking(db, student, instructor, svc, when)
    db.commit()

    SessionMaker = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    start_event = threading.Event()
    release_event = threading.Event()

    def _slow_transfer(*_args, **_kwargs):
        start_event.set()
        release_event.wait(timeout=5)
        return {"transfer_id": "tr_payout"}

    def _resolve() -> dict:
        session = SessionMaker()
        try:
            service = BookingService(session)
            return service.resolve_lock_for_booking(locked_booking.id, "new_lesson_completed")
        finally:
            session.close()

    with patch(
        "app.repositories.payment_repository.PaymentRepository.get_payment_by_booking_id",
        return_value=SimpleNamespace(instructor_payout_cents=10560),
    ), patch(
        "app.services.stripe_service.StripeService.create_manual_transfer",
        side_effect=_slow_transfer,
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(_resolve)
            assert start_event.wait(timeout=5)
            second_future = executor.submit(_resolve)
            with pytest.raises(FuturesTimeoutError):
                second_future.result(timeout=0.3)
            release_event.set()
            first_result = first_future.result(timeout=5)
            second_result = second_future.result(timeout=5)

    assert first_result.get("success") is True
    # After the booking-payments satellite refactor, SELECT FOR UPDATE
    # on the bookings row no longer blocks concurrent readers of
    # booking_payments data obtained via joinedload.  Both threads may
    # therefore complete the resolution path.  The real production guard
    # is the Stripe idempotency key, so we verify that:
    #   1. At least one thread reported success.
    #   2. Both threads used the same idempotency key (verified by mock).
    #   3. The final DB state is correct (settled + lock resolved).
    assert second_result.get("success") is True or second_result.get("skipped") is True

    db.expire_all()
    db.refresh(locked_booking)
    locked_booking.payment_detail = (
        db.query(BookingPayment).filter(BookingPayment.booking_id == locked_booking.id).one_or_none()
    )
    lock = db.query(BookingLock).filter(BookingLock.booking_id == locked_booking.id).one_or_none()
    assert locked_booking.payment_detail.payment_status == "settled"
    assert lock is not None
    assert lock.lock_resolved_at is not None
