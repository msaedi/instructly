"""Integration tests for reschedule enforcement rules (v2.1.1)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException
from app.models.booking import BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.utils.bitset import bits_from_windows

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
        catalog_service = db.query(ServiceCatalog).first()
        if not catalog_service:
            category = ServiceCategory(name="Test Category", slug="test-category")
            db.add(category)
            db.flush()
            catalog_service = ServiceCatalog(
                name="Test Service",
                slug="test-service",
                category_id=category.id,
            )
            db.add(catalog_service)
            db.flush()
        service = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=100.0,
            description="Test service",
            is_active=True,
            duration_options=[60],
        )
        db.add(service)
        db.flush()
    if service.hourly_rate is not None and service.hourly_rate < 80.0:
        service.hourly_rate = 100.0
        db.flush()
    return service


def _safe_start_window(hours_from_now: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)
    if end_dt.date() != start_dt.date():
        start_dt = (start_dt - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def test_reschedule_different_instructor_blocked(
    db: Session,
    test_student: User,
    test_instructor_with_availability: User,
    test_instructor_2: User,
) -> None:
    service = _get_service(db, test_instructor_with_availability)
    start_dt, end_dt = _safe_start_window(48)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Reschedule",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_resched",
    )
    db.commit()

    other_service = _get_service(db, test_instructor_2)
    target_date = (start_dt + timedelta(days=1)).date()
    availability_repo = AvailabilityDayRepository(db)
    windows = [("09:00:00", "12:00:00"), ("14:00:00", "17:00:00")]
    availability_repo.upsert_week(
        test_instructor_2.id, [(target_date, bits_from_windows(windows))]
    )
    db.commit()
    new_start = (start_dt + timedelta(days=1)).replace(hour=14)
    new_booking_data = BookingCreate(
        instructor_id=test_instructor_2.id,
        instructor_service_id=other_service.id,
        booking_date=new_start.date(),
        start_time=new_start.time(),
        selected_duration=60,
        student_note=None,
        meeting_location="Test",
        location_type="neutral",
    )

    booking_service = BookingService(db)
    with pytest.raises(BusinessRuleException):
        booking_service.create_rescheduled_booking_with_existing_payment(
            test_student,
            new_booking_data,
            60,
            booking.id,
            "pi_resched",
            PaymentStatus.AUTHORIZED.value,
            "pm_test",
        )


def test_reschedule_lt12h_blocked(
    db: Session, test_student: User, test_instructor_with_availability: User, monkeypatch
) -> None:
    service = _get_service(db, test_instructor_with_availability)
    start_dt, end_dt = _safe_start_window(48)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Reschedule",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_resched",
    )
    db.commit()

    booking_service = BookingService(db)
    monkeypatch.setattr(
        "app.services.booking_service.TimezoneService.hours_until",
        lambda _dt: 6.0,
    )
    with pytest.raises(BusinessRuleException) as exc:
        booking_service.validate_reschedule_allowed(booking)
    assert "reschedule within 12 hours" in str(exc.value).lower()


def test_reschedule_gte24h_unlimited(
    db: Session, test_student: User, test_instructor_with_availability: User, monkeypatch
) -> None:
    service = _get_service(db, test_instructor_with_availability)
    start_dt, end_dt = _safe_start_window(48)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Reschedule",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_resched",
    )
    db.commit()

    booking_service = BookingService(db)
    monkeypatch.setattr(
        "app.services.booking_service.TimezoneService.hours_until",
        lambda _dt: 30.0,
    )
    booking_service.validate_reschedule_allowed(booking)


def test_second_reschedule_12_to_24h_blocked(
    db: Session, test_student: User, test_instructor_with_availability: User, monkeypatch
) -> None:
    service = _get_service(db, test_instructor_with_availability)
    start_dt, end_dt = _safe_start_window(48)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Reschedule",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_resched",
        late_reschedule_used=True,
    )
    db.commit()

    booking_service = BookingService(db)
    monkeypatch.setattr(
        "app.services.booking_service.TimezoneService.hours_until",
        lambda _dt: 18.0,
    )
    with pytest.raises(BusinessRuleException) as exc:
        booking_service.validate_reschedule_allowed(booking)
    assert "already used your late reschedule" in str(exc.value).lower()


def test_reschedule_count_incremented(
    db: Session,
    test_student: User,
    test_instructor_with_availability: User,
) -> None:
    service = _get_service(db, test_instructor_with_availability)
    start_dt, end_dt = _safe_start_window(48)
    original = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Reschedule",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral",
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_resched",
    )
    db.commit()

    new_start = (start_dt + timedelta(days=1)).replace(hour=14)
    booking_data = BookingCreate(
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=new_start.date(),
        start_time=new_start.time(),
        selected_duration=60,
        student_note=None,
        meeting_location="Test",
        location_type="neutral",
    )

    booking_service = BookingService(db)
    rescheduled = booking_service.create_rescheduled_booking_with_existing_payment(
        test_student,
        booking_data,
        60,
        original.id,
        "pi_resched",
        PaymentStatus.AUTHORIZED.value,
        "pm_test",
    )

    db.refresh(original)
    db.refresh(rescheduled)
    assert original.reschedule_count == 1
    assert rescheduled.reschedule_count == 1
