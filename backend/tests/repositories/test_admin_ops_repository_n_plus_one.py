"""Repository tests for AdminOpsRepository eager loading."""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import event

from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog
from app.repositories.admin_ops_repository import AdminOpsRepository

try:  # pragma: no cover - allow tests to run from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def test_get_bookings_in_date_range_with_service_eager_loads_category(
    db, test_instructor, test_student
):
    """Ensure booking summary query does not trigger N+1 when accessing category."""
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None

    services = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active.is_(True))
        .order_by(Service.id)
        .all()
    )
    assert len(services) >= 2

    booking_date = date.today() + timedelta(days=1)

    for idx, service in enumerate(services[:2]):
        catalog_entry = (
            db.query(ServiceCatalog)
            .filter(ServiceCatalog.id == service.service_catalog_id)
            .first()
        )
        service_name = catalog_entry.name if catalog_entry else "Test Service"
        create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=booking_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            offset_index=idx * 10,
            service_name=service_name,
            hourly_rate=service.hourly_rate,
            total_price=float(service.hourly_rate),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Test Location",
            cancel_duplicate=True,
        )

    db.expunge_all()

    repo = AdminOpsRepository(db)
    query_count = 0

    def count_query(*_args, **_kwargs):
        nonlocal query_count
        query_count += 1

    event.listen(db.bind, "before_cursor_execute", count_query)
    try:
        bookings = repo.get_bookings_in_date_range_with_service(
            start_date=booking_date - timedelta(days=1),
            end_date=booking_date + timedelta(days=1),
        )

        for booking in bookings:
            if booking.instructor_service:
                _ = booking.instructor_service.category
    finally:
        event.remove(db.bind, "before_cursor_execute", count_query)

    assert len(bookings) >= 2
    assert (
        query_count <= 3
    ), f"N+1 detected: {query_count} queries for {len(bookings)} bookings"
