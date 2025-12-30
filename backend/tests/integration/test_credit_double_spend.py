"""
Integration tests for credit double-spend protection.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
import threading
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

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


def _create_booking(
    db: Session,
    *,
    student_id: str,
    instructor_id: str,
    service: InstructorService,
    hours_from_now: int,
) -> str:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Credit Lock",
        hourly_rate=float(service.hourly_rate or 100.0),
        total_price=float(service.hourly_rate or 100.0),
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
    )
    db.flush()
    return booking.id


def _create_credit(
    db: Session,
    *,
    user_id: str,
    amount_cents: int,
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
    db.flush()
    return credit


def test_concurrent_reservations_block_double_spend(db: Session, test_student, test_instructor):
    service = _get_service(db, test_instructor)
    booking_id_1 = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        service=service,
        hours_from_now=30,
    )
    booking_id_2 = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        service=service,
        hours_from_now=31,
    )

    _create_credit(
        db,
        user_id=test_student.id,
        amount_cents=5000,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.commit()

    SessionMaker = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    lock_acquired = threading.Event()
    release_lock = threading.Event()

    def _reserve_first() -> int:
        session = SessionMaker()
        try:
            credit_service = CreditService(session)
            session.begin()
            amount = credit_service.reserve_credits_for_booking(
                user_id=test_student.id,
                booking_id=booking_id_1,
                max_amount_cents=4000,
                use_transaction=False,
            )
            lock_acquired.set()
            release_lock.wait(timeout=5)
            session.commit()
            return amount
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _reserve_second() -> int:
        session = SessionMaker()
        try:
            credit_service = CreditService(session)
            lock_acquired.wait(timeout=5)
            return credit_service.reserve_credits_for_booking(
                user_id=test_student.id,
                booking_id=booking_id_2,
                max_amount_cents=4000,
                use_transaction=True,
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(_reserve_first)
        assert lock_acquired.wait(timeout=5)
        second_future = executor.submit(_reserve_second)
        with pytest.raises(FuturesTimeoutError):
            second_future.result(timeout=0.3)
        release_lock.set()
        reserved_first = first_future.result(timeout=5)
        reserved_second = second_future.result(timeout=5)

    total_reserved = reserved_first + reserved_second
    assert total_reserved <= 5000

    db.expire_all()
    reserved_rows = (
        db.query(PlatformCredit)
        .filter(
            PlatformCredit.user_id == test_student.id,
            PlatformCredit.status == "reserved",
        )
        .all()
    )
    reserved_sum = sum(
        int(credit.reserved_amount_cents or credit.amount_cents or 0) for credit in reserved_rows
    )
    assert reserved_sum == total_reserved


def test_reservation_idempotent_for_booking(db: Session, test_student, test_instructor) -> None:
    service = _get_service(db, test_instructor)
    booking_id = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        service=service,
        hours_from_now=30,
    )

    credit = _create_credit(
        db,
        user_id=test_student.id,
        amount_cents=5000,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    credit_service = CreditService(db)
    amount_first = credit_service.reserve_credits_for_booking(
        user_id=test_student.id,
        booking_id=booking_id,
        max_amount_cents=3000,
    )
    amount_second = credit_service.reserve_credits_for_booking(
        user_id=test_student.id,
        booking_id=booking_id,
        max_amount_cents=3000,
    )

    assert amount_first == 3000
    assert amount_second == 3000

    db.refresh(credit)
    assert credit.status == "reserved"
    assert credit.reserved_amount_cents == 3000
