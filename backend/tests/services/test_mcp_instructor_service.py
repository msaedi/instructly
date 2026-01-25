from datetime import date, datetime, time, timezone

import pytest

from app.core.exceptions import NotFoundException
from app.models.review import Review, ReviewStatus
from app.services.mcp_instructor_service import MCPInstructorService

try:  # pragma: no cover
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def test_list_instructors_returns_structure(db, test_instructor):
    service = MCPInstructorService(db)
    payload = service.list_instructors(
        status=None,
        is_founding=None,
        service_slug=None,
        category_slug=None,
        limit=10,
        cursor=None,
    )

    assert "items" in payload
    assert payload["items"]
    item = payload["items"][0]
    assert "user_id" in item
    assert "status" in item
    assert "admin_url" in item


def test_get_service_coverage(db, test_instructor):
    service = MCPInstructorService(db)
    data = service.get_service_coverage(status="live", group_by="service", top=5)
    assert data["group_by"] == "service"
    assert isinstance(data["labels"], list)
    assert isinstance(data["values"], list)


def test_get_instructor_detail_identifiers(db, test_instructor, test_student):
    service = MCPInstructorService(db)

    profile = test_instructor.instructor_profile
    assert profile is not None
    service_record = profile.instructor_services[0]

    today = date.today()
    start_time = time(10, 0)
    end_time = time(11, 0)
    hourly_rate = float(service_record.hourly_rate)
    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service_record.id,
        booking_date=today,
        start_time=start_time,
        end_time=end_time,
        status="COMPLETED",
        offset_index=0,
        service_name=service_record.catalog_entry.name if service_record.catalog_entry else "Lesson",
        hourly_rate=hourly_rate,
        total_price=hourly_rate,
        duration_minutes=60,
    )
    booking.completed_at = datetime.now(timezone.utc)
    db.flush()

    review = Review(
        booking_id=booking.id,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=service_record.id,
        rating=5,
        review_text="Great",
        status=ReviewStatus.PUBLISHED,
        is_verified=True,
        booking_completed_at=booking.completed_at,
    )
    db.add(review)
    db.flush()

    detail = service.get_instructor_detail(test_instructor.id)
    assert detail["user_id"] == test_instructor.id
    assert detail["stats"]["rating_count"] == 1

    detail_email = service.get_instructor_detail(test_instructor.email)
    assert detail_email["user_id"] == test_instructor.id

    test_instructor.first_name = f"Unique{test_instructor.id[-4:]}"
    test_instructor.last_name = f"Name{test_instructor.id[-6:]}"
    db.flush()
    full_name = f"{test_instructor.first_name} {test_instructor.last_name}"
    detail_name = service.get_instructor_detail(full_name)
    assert detail_name["user_id"] == test_instructor.id


def test_get_instructor_detail_not_found(db):
    service = MCPInstructorService(db)
    with pytest.raises(NotFoundException):
        service.get_instructor_detail("Unknown Person")
