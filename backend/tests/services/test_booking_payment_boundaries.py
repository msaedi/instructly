from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from tests.utils.time import (
    booking_fields_from_start,
    start_just_over_24h,
    start_just_under_24h,
)
import ulid

from app.core.enums import RoleName
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.rbac import Role
from app.models.user import User
from app.services.booking_service import BookingService

try:  # pragma: no cover - support repo or backend invocation
    from backend.tests._utils import ensure_instructor_service_for_tests
except ModuleNotFoundError:  # pragma: no cover
    from tests._utils import ensure_instructor_service_for_tests


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    yield

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def test_immediate_vs_scheduled_boundary(db: Session) -> None:
    # Ensure roles
    student_role = db.query(Role).filter_by(name=RoleName.STUDENT).first()
    if not student_role:
        student_role = Role(id=str(ulid.ULID()), name=RoleName.STUDENT, description="Student")
        db.add(student_role)
        db.flush()

    instructor_role = db.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
    if not instructor_role:
        instructor_role = Role(id=str(ulid.ULID()), name=RoleName.INSTRUCTOR, description="Instructor")
        db.add(instructor_role)
        db.flush()

    # Create student & instructor
    student = User(
        id=str(ulid.ULID()),
        email=f"student_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="S",
        last_name="T",
        zip_code="10001",
        is_active=True,
    )
    student.roles.append(student_role)
    db.add(student)
    db.flush()

    instructor = User(
        id=str(ulid.ULID()),
        email=f"instructor_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="I",
        last_name="N",
        zip_code="10001",
        is_active=True,
    )
    instructor.roles.append(instructor_role)
    db.add(instructor)
    db.flush()

    # Instructor profile and service
    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=instructor.id,
        bio="Test",
        years_experience=5,
    )
    db.add(profile)
    db.flush()

    duration_minutes = 60

    _, instructor_service_id = ensure_instructor_service_for_tests(
        db,
        instructor_profile_id=profile.id,
        service_name="Svc",
        duration_minutes=duration_minutes,
        hourly_rate=100.0,
        extra_instructor_service_fields={"duration_options": [30, 60, 90]},
    )

    svc = BookingService(db)

    # 23h59m ⇒ authorizing
    start1 = start_just_under_24h()
    bd1, st1, et1 = booking_fields_from_start(start1, duration_minutes=duration_minutes)
    b1 = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor_service_id,
        booking_date=bd1,
        start_time=st1,
        end_time=et1,
        service_name="Test",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.PENDING,
        payment_status="pending_payment_method",
        offset_index=0,
    )
    c1 = svc.confirm_booking_payment(b1.id, student, "pm_x", False)
    assert c1.payment_status == "authorizing"

    # 24h01m ⇒ scheduled
    start2 = start_just_over_24h()
    bd2, st2, et2 = booking_fields_from_start(start2, duration_minutes=duration_minutes)
    first_end_dt = datetime.combine(bd1, et1)
    second_start_dt = datetime.combine(bd2, st2)
    minimum_gap = first_end_dt + timedelta(minutes=90)
    if second_start_dt <= minimum_gap:
        second_start_dt = minimum_gap
    second_end_dt = second_start_dt + timedelta(minutes=duration_minutes)
    if second_end_dt.date() != second_start_dt.date():
        second_start_dt = (first_end_dt + timedelta(hours=3)).replace(
            minute=0, second=0, microsecond=0
        )
        second_end_dt = second_start_dt + timedelta(minutes=duration_minutes)
    bd2 = second_start_dt.date()
    st2 = second_start_dt.time()
    et2 = second_end_dt.time()
    b2 = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor_service_id,
        booking_date=bd2,
        start_time=st2,
        end_time=et2,
        service_name="Test",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=duration_minutes,
        status=BookingStatus.PENDING,
        payment_status="pending_payment_method",
        offset_index=2,
    )
    c2 = svc.confirm_booking_payment(b2.id, student, "pm_x", False)
    assert c2.payment_status == "scheduled"
