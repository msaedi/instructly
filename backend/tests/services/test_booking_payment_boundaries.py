from __future__ import annotations

import ulid
import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.models.rbac import Role
from app.models.user import User
from app.models.instructor import InstructorProfile
from app.models.service_catalog import ServiceCatalog, ServiceCategory, InstructorService
from app.models.booking import Booking, BookingStatus
from app.services.booking_service import BookingService
from tests.utils.time import (
    start_just_under_24h,
    start_just_over_24h,
    booking_fields_from_start,
)


@pytest.mark.asyncio
async def test_immediate_vs_scheduled_boundary(db: Session) -> None:
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

    category = ServiceCategory(
        id=str(ulid.ULID()),
        name="Cat",
        slug=f"cat-{str(ulid.ULID()).lower()}",
        description="Cat",
    )
    db.add(category)
    db.flush()

    catalog = ServiceCatalog(
        id=str(ulid.ULID()),
        category_id=category.id,
        name="Svc",
        slug=f"svc-{str(ulid.ULID()).lower()}",
        description="Svc",
    )
    db.add(catalog)
    db.flush()

    instr_service = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=100.0,
        duration_options=[30, 60, 90],
        is_active=True,
    )
    db.add(instr_service)
    db.flush()

    svc = BookingService(db)

    # 23h59m ⇒ authorizing
    start1 = start_just_under_24h()
    bd1, st1, et1 = booking_fields_from_start(start1)
    b1 = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instr_service.id,
        booking_date=bd1,
        start_time=st1,
        end_time=et1,
        service_name="Test",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.PENDING,
        payment_status="pending_payment_method",
    )
    db.add(b1)
    db.flush()
    c1 = await svc.confirm_booking_payment(b1.id, student, "pm_x", False)
    assert c1.payment_status == "authorizing"

    # 24h01m ⇒ scheduled
    start2 = start_just_over_24h()
    bd2, st2, et2 = booking_fields_from_start(start2)
    b2 = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instr_service.id,
        booking_date=bd2,
        start_time=st2,
        end_time=et2,
        service_name="Test",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        status=BookingStatus.PENDING,
        payment_status="pending_payment_method",
    )
    db.add(b2)
    db.flush()
    c2 = await svc.confirm_booking_payment(b2.id, student, "pm_x", False)
    assert c2.payment_status == "scheduled"
