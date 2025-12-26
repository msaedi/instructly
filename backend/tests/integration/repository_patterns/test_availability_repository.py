# backend/tests/integration/repository_patterns/test_availability_repository.py
"""Bitmap-era repository pattern examples for instructor availability."""

from datetime import date, time, timedelta

import pytest
from tests.integration.repository_patterns._bitmap_helpers import (
    delete_day,
    fetch_days,
    flatten_windows,
    overlaps,
    seed_day,
    window_counts,
    window_exists,
)

from app.core.exceptions import RepositoryException
from app.core.timezone_utils import get_user_today
from app.core.ulid_helper import generate_ulid
from app.models.availability import BlackoutDate
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    InstructorService as Service,
    ServiceCatalog,
    ServiceCategory,
)
from app.repositories.availability_repository import AvailabilityRepository
from app.utils.bitset import windows_from_bits

try:  # pragma: no cover - fallback for direct backend pytest invocation
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture
def test_service(db, test_instructor):
    """Create a catalog + instructor service for bookings."""
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    if not profile:
        profile = InstructorProfile(
            user_id=test_instructor.id,
            bio="Test bio",
            years_experience=5,
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()
        add_service_areas_for_boroughs(db, user=test_instructor, boroughs=["Manhattan"])

    category = db.query(ServiceCategory).first()
    if not category:
        category = ServiceCategory(name="Test Category", slug=f"test-category-{generate_ulid().lower()}")
        db.add(category)
        db.flush()

    slug = f"test-service-{generate_ulid().lower()}"
    catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    if not catalog_service:
        catalog_service = ServiceCatalog(
            name="Test Service",
            slug=slug,
            category_id=category.id,
            description="Test service description",
        )
        db.add(catalog_service)
        db.flush()

    service = Service(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=50.0,
        description="Test service description",
        is_active=True,
    )
    db.add(service)
    db.commit()
    return service


class TestAvailabilityRepositoryQueries:
    """Query patterns expressed in bitmap storage."""

    def test_get_week_availability(self, db, test_instructor):
        monday = date.today() - timedelta(days=date.today().weekday())
        for offset in range(7):
            current = monday + timedelta(days=offset)
            windows = [
                (time(9, 0), time(10, 0)),
                (time(14, 0), time(15, 0)),
                (time(18, 0), time(19, 0)),
            ]
            seed_day(db, test_instructor.id, current, windows)

        rows = fetch_days(db, test_instructor.id, monday, monday + timedelta(days=6))
        flat = flatten_windows(rows)

        assert len(flat) == 21
        assert flat == sorted(flat, key=lambda item: (item["date"], item["start_time"], item["end_time"]))

    def test_get_booked_slots_in_range(self, db, test_instructor, test_student, test_service):
        repo_start = date.today() - timedelta(days=1)
        repo_end = date.today() + timedelta(days=1)
        booking_offsets = [-1, 0, 1, 7]

        for offset in booking_offsets:
            booking_date = date.today() + timedelta(days=offset)
            start_time = time(10, 0)
            end_time = time(11, 0)
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=test_service.id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                **booking_timezone_fields(booking_date, start_time, end_time),
                status=BookingStatus.CONFIRMED,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        booking_date = date.today()
        start_time = time(14, 0)
        end_time = time(15, 0)
        cancelled = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=test_service.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            **booking_timezone_fields(booking_date, start_time, end_time),
            status=BookingStatus.CANCELLED,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
        )
        db.add(cancelled)
        db.flush()

        results = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date >= repo_start,
                Booking.booking_date <= repo_end,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(Booking.booking_date, Booking.start_time)
            .all()
        )

        assert len(results) == 3
        assert all(repo_start <= r.booking_date <= repo_end for r in results)

    def test_get_booked_time_ranges(self, db, test_instructor, test_student, test_service):
        target_date = date.today()
        windows = [
            (time(9, 0), time(10, 0)),
            (time(11, 0), time(12, 30)),
            (time(14, 0), time(15, 0)),
        ]
        for start, end in windows:
            db.add(
                Booking(
                    student_id=test_student.id,
                    instructor_id=test_instructor.id,
                    instructor_service_id=test_service.id,
                    booking_date=target_date,
                    start_time=start,
                    end_time=end,
                    **booking_timezone_fields(target_date, start, end),
                    status=BookingStatus.CONFIRMED,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                )
            )
        db.flush()

        results = (
            db.query(Booking.start_time, Booking.end_time)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(Booking.start_time)
            .all()
        )
        assert results == windows

    def test_find_time_conflicts(self, db, test_instructor):
        target_date = date.today()
        seed_day(
            db,
            test_instructor.id,
            target_date,
            [
                (time(9, 0), time(10, 0)),
                (time(10, 30), time(11, 0)),
                (time(11, 30), time(12, 0)),
                (time(12, 30), time(13, 0)),
                (time(13, 30), time(14, 0)),
            ],
        )

        rows = fetch_days(db, test_instructor.id, target_date, target_date)
        assert rows
        day_windows = windows_from_bits(rows[0].bits or b"")

        conflicts = [w for w in day_windows if overlaps(w, time(10, 45), time(12, 45))]
        assert len(conflicts) == 3

    def test_get_availability_summary(self, db, test_instructor):
        start_date = date.today()
        slot_counts = [3, 5, 2, 0, 4]
        for offset, count in enumerate(slot_counts):
            windows = [(time(9 + (i * 2), 0), time(10 + (i * 2), 0)) for i in range(count)]
            seed_day(db, test_instructor.id, start_date + timedelta(days=offset), windows)

        rows = fetch_days(db, test_instructor.id, start_date, start_date + timedelta(days=4))
        summary = window_counts(rows)

        assert len(summary) == 4
        for offset, count in enumerate(slot_counts):
            if count:
                assert summary[(start_date + timedelta(days=offset)).isoformat()] == count

    def test_get_instructor_availability_stats(self, db, test_instructor, test_student, test_service):
        today = date.today()
        future_dates = [today + timedelta(days=i) for i in range(1, 8)]
        for date_val in future_dates:
            seed_day(
                db,
                test_instructor.id,
                date_val,
                [(time(9, 0), time(10, 0)), (time(11, 0), time(12, 0)), (time(14, 0), time(15, 0))],
            )

        for i in range(5):
            db.add(
                Booking(
                    student_id=test_student.id,
                    instructor_id=test_instructor.id,
                    instructor_service_id=test_service.id,
                    booking_date=future_dates[i],
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                    **booking_timezone_fields(future_dates[i], time(9, 0), time(10, 0)),
                    status=BookingStatus.CONFIRMED,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                )
            )
        db.flush()

        rows = fetch_days(db, test_instructor.id, future_dates[0], future_dates[-1])
        total_slots = sum(len(windows_from_bits(row.bits or b"")) for row in rows)
        booked_slots = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date >= future_dates[0],
                Booking.booking_date <= future_dates[-1],
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .count()
        )

        utilization_rate = (booked_slots / total_slots) * 100
        assert total_slots == 21
        assert booked_slots == 5
        assert pytest.approx(utilization_rate, rel=0.1) == 23.8
        assert rows[0].day_date == future_dates[0]
        assert rows[-1].day_date == future_dates[-1]


class TestAvailabilityRepositoryWindowManagement:
    """CRUD-like operations expressed via AvailabilityDay rows."""

    def test_create_window_success(self, db, test_instructor):
        target_date = date.today()
        seed_day(db, test_instructor.id, target_date, [(time(10, 0), time(11, 0))])
        assert window_exists(db, test_instructor.id, target_date, time(10, 0), time(11, 0))

    def test_duplicate_window_merge(self, db, test_instructor):
        target_date = date.today()
        window = (time(10, 0), time(11, 0))
        seed_day(db, test_instructor.id, target_date, [window])
        seed_day(db, test_instructor.id, target_date, [window])
        rows = fetch_days(db, test_instructor.id, target_date, target_date)
        assert len(windows_from_bits(rows[0].bits or b"")) == 1

    def test_window_exists_helper(self, db, test_instructor):
        target_date = date.today()
        seed_day(db, test_instructor.id, target_date, [(time(9, 0), time(10, 0))])
        assert window_exists(db, test_instructor.id, target_date, time(9, 0), time(10, 0))
        assert not window_exists(db, test_instructor.id, target_date, time(11, 0), time(12, 0))

    def test_delete_windows_except(self, db, test_instructor):
        target_date = date.today()
        all_windows = [
            (time(9, 0), time(10, 0)),
            (time(11, 0), time(12, 0)),
            (time(13, 0), time(14, 0)),
            (time(15, 0), time(16, 0)),
            (time(17, 0), time(18, 0)),
        ]
        keep = all_windows[:2]
        seed_day(db, test_instructor.id, target_date, all_windows)
        seed_day(db, test_instructor.id, target_date, keep)
        rows = fetch_days(db, test_instructor.id, target_date, target_date)
        remaining = set(windows_from_bits(rows[0].bits or b""))
        assert remaining == {("09:00:00", "10:00:00"), ("11:00:00", "12:00:00")}

    def test_delete_windows_by_dates(self, db, test_instructor):
        dates_to_delete = [date.today() + timedelta(days=i) for i in range(3)]
        keep_date = date.today() + timedelta(days=5)
        for day in dates_to_delete + [keep_date]:
            seed_day(db, test_instructor.id, day, [(time(9, 0), time(10, 0)), (time(11, 0), time(12, 0))])

        deleted = sum(delete_day(db, test_instructor.id, day) for day in dates_to_delete)
        assert deleted == 3

        rows = fetch_days(db, test_instructor.id, keep_date, keep_date)
        assert len(rows) == 1
        assert window_exists(db, test_instructor.id, keep_date, time(9, 0), time(10, 0))
        remaining_rows = (
            db.query(AvailabilityDay)
            .filter(AvailabilityDay.instructor_id == test_instructor.id)
            .all()
        )
        assert all(row.day_date == keep_date for row in remaining_rows)


class TestAvailabilityRepositoryBlackoutDates:
    """Tests that still exercise the AvailabilityRepository class."""

    def test_create_blackout_date(self, db, test_instructor):
        repo = AvailabilityRepository(db)
        blackout = repo.create_blackout_date(
            instructor_id=test_instructor.id,
            blackout_date=date.today() + timedelta(days=7),
            reason="Vacation",
        )
        assert blackout.instructor_id == test_instructor.id

    def test_create_duplicate_blackout_error(self, db, test_instructor):
        repo = AvailabilityRepository(db)
        blackout_date = date.today() + timedelta(days=7)
        repo.create_blackout_date(instructor_id=test_instructor.id, blackout_date=blackout_date)
        db.flush()
        with pytest.raises(RepositoryException):
            repo.create_blackout_date(instructor_id=test_instructor.id, blackout_date=blackout_date)

    def test_get_future_blackout_dates(self, db, test_instructor):
        repo = AvailabilityRepository(db)
        instructor_today = get_user_today(test_instructor)
        db.add(BlackoutDate(instructor_id=test_instructor.id, date=instructor_today - timedelta(days=1)))
        for offset in range(1, 4):
            db.add(
                BlackoutDate(
                    instructor_id=test_instructor.id,
                    date=instructor_today + timedelta(days=offset),
                    reason=f"Trip {offset}",
                )
            )
        db.flush()

        future_dates = repo.get_future_blackout_dates(test_instructor.id)
        assert len(future_dates) == 3
        assert future_dates[0].date == instructor_today + timedelta(days=1)
