"""Integration tests for immediate auth confirmation gating (<24h)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.services.booking_service import BookingService

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


def _safe_start_window(hours_from_now: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)
    if end_dt.date() != start_dt.date():
        start_dt = (start_dt - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def _create_pending_booking(
    db: Session,
    *,
    student: User,
    instructor: User,
    hours_from_now: int,
) -> Booking:
    service = _get_service(db, instructor)
    start_dt, end_dt = _safe_start_window(hours_from_now)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Auth Gating",
        hourly_rate=float(service.hourly_rate or 120.0),
        total_price=float(service.hourly_rate or 120.0),
        duration_minutes=60,
        status=BookingStatus.PENDING,
        meeting_location="Test",
        location_type="neutral",
    )
    booking.payment_status = PaymentStatus.SCHEDULED.value
    db.commit()
    return booking


def test_immediate_auth_success_confirms_booking(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_pending_booking(
        db, student=test_student, instructor=test_instructor, hours_from_now=6
    )
    booking_service = BookingService(db)

    def _auth_success(booking_id: str, _hours_until: float) -> dict:
        target = db.query(Booking).filter(Booking.id == booking_id).first()
        assert target is not None
        target.payment_status = PaymentStatus.AUTHORIZED.value
        target.status = BookingStatus.CONFIRMED
        target.confirmed_at = datetime.now(timezone.utc)
        db.commit()
        return {"success": True}

    with patch("app.tasks.payment_tasks._process_authorization_for_booking", _auth_success):
        booking_service.confirm_booking_payment(
            booking.id, test_student, payment_method_id="pm_test", save_payment_method=False
        )

    db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_status == PaymentStatus.AUTHORIZED.value


def test_immediate_auth_failure_keeps_booking_pending(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_pending_booking(
        db, student=test_student, instructor=test_instructor, hours_from_now=6
    )
    booking_service = BookingService(db)

    def _auth_failure(booking_id: str, _hours_until: float) -> dict:
        target = db.query(Booking).filter(Booking.id == booking_id).first()
        assert target is not None
        target.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        target.auth_failure_count = 1
        target.auth_attempted_at = datetime.now(timezone.utc)
        db.commit()
        return {"success": False, "error": "card_declined"}

    with patch("app.tasks.payment_tasks._process_authorization_for_booking", _auth_failure):
        booking_service.confirm_booking_payment(
            booking.id, test_student, payment_method_id="pm_test", save_payment_method=False
        )

    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING
    assert booking.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


def test_immediate_auth_failure_does_not_reserve_slot(
    db: Session, test_student: User, test_instructor: User
) -> None:
    booking = _create_pending_booking(
        db, student=test_student, instructor=test_instructor, hours_from_now=6
    )
    booking_service = BookingService(db)

    def _auth_failure(booking_id: str, _hours_until: float) -> dict:
        target = db.query(Booking).filter(Booking.id == booking_id).first()
        assert target is not None
        target.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        target.auth_failure_count = 1
        target.auth_attempted_at = datetime.now(timezone.utc)
        db.commit()
        return {"success": False, "error": "card_declined"}

    with patch("app.tasks.payment_tasks._process_authorization_for_booking", _auth_failure):
        booking_service.confirm_booking_payment(
            booking.id, test_student, payment_method_id="pm_test", save_payment_method=False
        )

    db.refresh(booking)
    service = _get_service(db, test_instructor)
    availability = booking_service.check_availability(
        instructor_id=booking.instructor_id,
        booking_date=booking.booking_date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        instructor_service_id=service.id,
        exclude_booking_id=None,
    )

    available_flag = availability.get("available") if isinstance(availability, dict) else bool(
        availability
    )
    assert available_flag is True
