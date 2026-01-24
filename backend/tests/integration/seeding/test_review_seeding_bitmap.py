from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from scripts.backfill_bitmaps import backfill_bitmaps_range
from scripts.seed_utils import create_review_booking_pg_safe
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.rbac import Role, UserRole as UserRoleJunction
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.utils.bitset import bits_from_windows


def _create_user(session: Session, user_id: str, email: str, is_instructor: bool) -> User:
    user = User(
        id=user_id,
        email=email,
        first_name="Test",
        last_name="User",
        hashed_password="hashed",
        account_status="active",
        is_active=True,
        zip_code="10001",
        timezone="America/New_York",
    )
    session.add(user)
    session.flush()

    role_name = RoleName.INSTRUCTOR if is_instructor else RoleName.STUDENT
    role = session.query(Role).filter_by(name=role_name).one()
    session.add(UserRoleJunction(user_id=user_id, role_id=role.id))
    return user


def test_backfill_and_review_booking_creation(db: Session):
    instructor = _create_user(db, "instr-1", "instructor@example.com", is_instructor=True)
    student = _create_user(db, "stud-1", "student@example.com", is_instructor=False)

    category_slug = f"music-{uuid4().hex[:8]}"
    category = ServiceCategory(name="Music", slug=category_slug)
    db.add(category)
    db.flush()

    catalog_entry = ServiceCatalog(
        category_id=category.id,
        name="Piano Lessons",
        slug=f"piano-lessons-{uuid4().hex[:8]}",
        description="One-on-one piano instruction",
    )
    db.add(catalog_entry)
    db.flush()

    profile = InstructorProfile(user_id=instructor.id, is_live=True)
    db.add(profile)
    db.flush()

    service = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_entry.id,
        hourly_rate=50.0,
        duration_options=[30, 60],
        offers_online=True,
        offers_travel=False,
        offers_at_location=False,
    )
    db.add(service)
    db.flush()

    # Seed current week bitmap (Mon-Fri 10:00-16:00)
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    windows = [("10:00:00", "16:00:00")]
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == instructor.id).delete()
    for offset in range(5):
        db.add(
            AvailabilityDay(
                instructor_id=instructor.id,
                day_date=current_monday + timedelta(days=offset),
                bits=bits_from_windows(windows),
            )
        )
    db.commit()

    # Backfill historical weeks
    stats = backfill_bitmaps_range(db, days=28)
    db.commit()
    assert instructor.id in stats

    base_date = today - timedelta(days=14)

    booking = create_review_booking_pg_safe(
        session=db,
        instructor_id=instructor.id,
        student_id=student.id,
        instructor_service_id=service.id,
        base_date=base_date,
        location_type="neutral_location",
        meeting_location="Online",
        service_name="Piano Lessons",
        hourly_rate=Decimal("50.00"),
        total_price=Decimal("50.00"),
        student_note="Seeded review booking",
        completed_at=today - timedelta(days=34),
        duration_minutes=60,
        lookback_days=90,
        horizon_days=14,
        day_start_hour=9,
        day_end_hour=18,
        step_minutes=15,
        durations_minutes=[60, 45, 30],
        service_area=None,
    )

    assert booking is not None
    assert booking.status == BookingStatus.COMPLETED
    assert booking.booking_date <= date.today()
    db.commit()

    stored_booking = db.get(Booking, booking.id)
    assert stored_booking is not None
    assert stored_booking.student_id == student.id
