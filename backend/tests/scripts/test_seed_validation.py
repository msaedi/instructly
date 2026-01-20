"""Tests to validate seed script data integrity."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from scripts import reset_and_seed_yaml
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.rbac import Role, UserRole as UserRoleJunction
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.utils.bitset import bits_from_windows


def _create_user(session: Session, *, email: str, role: RoleName) -> User:
    user = User(
        email=email,
        first_name="Seed",
        last_name="Tester",
        hashed_password="hashed",
        account_status="active",
        is_active=True,
        zip_code="10001",
        timezone="America/New_York",
    )
    session.add(user)
    session.flush()

    role_row = session.query(Role).filter_by(name=role).one()
    session.add(UserRoleJunction(user_id=user.id, role_id=role_row.id))
    return user


def _seed_review_context(db: Session) -> None:
    instructor = _create_user(db, email=f"instructor.{uuid4().hex[:8]}@example.com", role=RoleName.INSTRUCTOR)
    _create_user(db, email=f"student.{uuid4().hex[:8]}@example.com", role=RoleName.STUDENT)

    category = ServiceCategory(
        name="Seed Validation",
        slug=f"seed-validation-{uuid4().hex[:8]}",
    )
    db.add(category)
    db.flush()

    catalog_entry = ServiceCatalog(
        category_id=category.id,
        name="Seed Validation Lesson",
        slug=f"seed-validation-{uuid4().hex[:8]}",
        description="Seed validation service",
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
        duration_options=[60],
        offers_online=True,
        offers_travel=False,
        offers_at_location=False,
        is_active=True,
    )
    db.add(service)
    db.flush()

    today = date.today()
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == instructor.id).delete()
    db.add(
        AvailabilityDay(
            instructor_id=instructor.id,
            day_date=today,
            bits=bits_from_windows([("10:00:00", "12:00:00")]),
        )
    )
    db.commit()


class TestSeedDataIntegrity:
    """Verify seed scripts create valid data."""

    def test_no_completed_bookings_with_future_dates(self, db: Session, monkeypatch):
        """
        Regression test: COMPLETED bookings must have past dates.

        Bug fixed: review seeding used horizon_days=21 which could create
        COMPLETED bookings up to 21 days in the future.
        """
        _seed_review_context(db)
        monkeypatch.setenv("SITE_MODE", "int")

        utc_today = datetime.now(timezone.utc).date()
        future_date = utc_today + timedelta(days=7)
        calls = []

        def _future_slot(*args, past_only=False, horizon_days=None, **kwargs):
            calls.append((past_only, horizon_days))
            return future_date, time(10, 0), time(11, 0)

        monkeypatch.setattr(reset_and_seed_yaml, "find_free_slot_bulk", _future_slot)

        reset_and_seed_yaml.DatabaseSeeder(db=db).create_reviews()

        assert calls, "Expected review seeding to request a slot."
        assert all(past_only is True for past_only, _ in calls)
        assert all(horizon_days == 0 for _, horizon_days in calls)
        db.expire_all()
        future_completed = db.query(Booking).filter(
            Booking.status == BookingStatus.COMPLETED.value,
            Booking.booking_date > utc_today,
        ).all()

        assert len(future_completed) == 0, (
            f"Found {len(future_completed)} COMPLETED bookings with future dates: "
            f"{[(b.id, b.booking_date) for b in future_completed]}"
        )

    def test_no_completed_bookings_before_lesson_time(self, db: Session, monkeypatch):
        """COMPLETED bookings should have completed_at after lesson end."""
        _seed_review_context(db)
        monkeypatch.setenv("SITE_MODE", "int")

        past_date = datetime.now(timezone.utc).date() - timedelta(days=120)
        calls = []

        def _past_slot(*args, past_only=False, horizon_days=None, **kwargs):
            slot_index = len(calls)
            calls.append((past_only, horizon_days))
            start_hour = 10 + slot_index * 2
            return past_date, time(start_hour, 0), time(start_hour + 1, 0)

        monkeypatch.setattr(reset_and_seed_yaml, "find_free_slot_bulk", _past_slot)

        reset_and_seed_yaml.DatabaseSeeder(db=db).create_reviews()

        assert calls, "Expected review seeding to request a slot."
        assert all(past_only is True for past_only, _ in calls)
        assert all(horizon_days == 0 for _, horizon_days in calls)
        db.expire_all()
        completed = db.query(Booking).filter(
            Booking.status == BookingStatus.COMPLETED.value,
            Booking.completed_at.isnot(None),
        ).all()

        assert completed, "Expected review seeding to create completed bookings."

        violations = []
        for booking in completed:
            lesson_end = datetime.combine(
                booking.booking_date, booking.end_time, tzinfo=timezone.utc
            )
            completed_at = booking.completed_at
            if completed_at is None:
                continue
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            else:
                completed_at = completed_at.astimezone(timezone.utc)
            if completed_at < lesson_end:
                violations.append((booking.id, booking.booking_date, completed_at))

        assert len(violations) == 0, f"COMPLETED before lesson ended: {violations}"
