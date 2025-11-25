from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from backend.tests.factories.booking_builders import create_booking_pg_safe
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from ulid import ULID

from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.models.user import User


def _service_for(db: Session, instructor: User) -> InstructorService:
    profile = db.query(InstructorProfile).filter_by(user_id=instructor.id).first()
    assert profile is not None, "Instructor profile required for tests"
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == profile.id, InstructorService.is_active.is_(True))
        .first()
    )
    if service is None:
        catalog_entry = (
            db.query(InstructorService.service_catalog_id)
            .filter(InstructorService.service_catalog_id.isnot(None))
            .first()
        )
        catalog_id = catalog_entry[0] if catalog_entry else None
        if catalog_id is None:
            catalog_entry = db.query(ServiceCatalog.id).first()
            catalog_id = catalog_entry[0] if catalog_entry else None
        assert catalog_id is not None, "No catalog service available to seed instructor service"
        service = InstructorService(
            id=str(ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_id,
            hourly_rate=50.0,
            duration_options=[60],
            location_types=['in-person'],
            age_groups=['adults'],
            levels_taught=['beginner'],
            is_active=True,
        )
        db.add(service)
        db.flush()
    return service


def _seed_booking(
    db: Session,
    *,
    instructor: User,
    student: User,
    service: InstructorService,
    status: BookingStatus,
    day_offset: int = 0,
    booking_date_override: Optional[date] = None,
    start_time_override: Optional[time] = None,
    end_time_override: Optional[time] = None,
) -> str:
    booking_date = booking_date_override or (date.today() + timedelta(days=day_offset))
    start = start_time_override or time(10, 0)
    end = end_time_override or time(11, 0)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=start,
        end_time=end,
        status=status,
        service_name="Test Session",
        hourly_rate=50.0,
        total_price=50.0,
        duration_minutes=60,
    )
    booking.completed_at = booking_date if status == BookingStatus.COMPLETED else None
    db.flush()
    return booking.id


@pytest.mark.parametrize(
    "endpoint,status_filter",
    [("/completed", BookingStatus.COMPLETED), ("/upcoming", BookingStatus.CONFIRMED)],
)
def test_instructor_booking_endpoints_filter_by_current_instructor(
    client: TestClient,
    db: Session,
    test_instructor: User,
    test_instructor_2: User,
    test_student: User,
    auth_headers_instructor: dict,
    endpoint: str,
    status_filter: BookingStatus,
):
    """Ensure instructor booking endpoints only return the authenticated instructor's bookings."""
    primary_service = _service_for(db, test_instructor)
    other_service = _service_for(db, test_instructor_2)

    # Seed bookings for authenticated instructor
    kept_ids = {
        _seed_booking(
            db,
            instructor=test_instructor,
            student=test_student,
            service=primary_service,
            status=status_filter,
            day_offset=-2 if status_filter == BookingStatus.COMPLETED else 2,
        ),
        _seed_booking(
            db,
            instructor=test_instructor,
            student=test_student,
            service=primary_service,
            status=status_filter,
            day_offset=-3 if status_filter == BookingStatus.COMPLETED else 3,
        ),
    }

    # Seed bookings for another instructor which should never be returned
    _seed_booking(
        db,
        instructor=test_instructor_2,
        student=test_student,
        service=other_service,
        status=status_filter,
        day_offset=-4 if status_filter == BookingStatus.COMPLETED else 4,
    )

    # Use v1 API path exclusively - legacy paths removed in Phase 9
    path = f"/api/v1/instructor-bookings{endpoint}"
    response = client.get(path, headers=auth_headers_instructor)
    assert response.status_code == 200, response.text
    payload = response.json()
    returned_ids = {item["id"] for item in payload.get("items", [])}
    assert returned_ids == kept_ids
    for item in payload.get("items", []):
        assert item["instructor_id"] == test_instructor.id


def test_completed_endpoint_includes_past_confirmed_lessons(
    client: TestClient,
    db: Session,
    test_instructor: User,
    test_student: User,
    auth_headers_instructor: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Past lessons endpoint should include chronologically past CONFIRMED bookings."""
    service = _service_for(db, test_instructor)

    fake_now = datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc)

    def _fake_user_now(user_id: str, _db: Session):
        assert user_id == test_instructor.id
        return fake_now

    monkeypatch.setattr("app.repositories.booking_repository.get_user_now_by_id", _fake_user_now)

    booking_date = fake_now.date()
    past_booking_id = _seed_booking(
        db,
        instructor=test_instructor,
        student=test_student,
        service=service,
        status=BookingStatus.CONFIRMED,
        booking_date_override=booking_date,
        start_time_override=time(17, 0),
        end_time_override=time(18, 0),
    )
    future_booking_id = _seed_booking(
        db,
        instructor=test_instructor,
        student=test_student,
        service=service,
        status=BookingStatus.CONFIRMED,
        booking_date_override=booking_date,
        start_time_override=time(21, 0),
        end_time_override=time(22, 0),
    )

    # Use v1 API paths exclusively - legacy paths removed in Phase 9
    response = client.get("/api/v1/instructor-bookings/completed", headers=auth_headers_instructor)
    assert response.status_code == 200
    payload = response.json()
    returned_ids = {item["id"] for item in payload.get("items", [])}
    assert returned_ids == {past_booking_id}

    response = client.get("/api/v1/instructor-bookings/upcoming", headers=auth_headers_instructor)
    assert response.status_code == 200
    payload = response.json()
    upcoming_ids = {item["id"] for item in payload.get("items", [])}
    assert upcoming_ids == {future_booking_id}


def test_instructor_earnings_endpoint_aggregates_bookings(
    client: TestClient,
    db: Session,
    test_instructor: User,
    test_instructor_2: User,
    test_student: User,
    auth_headers_instructor: dict,
):
    primary_service = _service_for(db, test_instructor)
    other_service = _service_for(db, test_instructor_2)

    booking_one = _seed_booking(
        db,
        instructor=test_instructor,
        student=test_student,
        service=primary_service,
        status=BookingStatus.COMPLETED,
        day_offset=-2,
    )
    booking_two = _seed_booking(
        db,
        instructor=test_instructor,
        student=test_student,
        service=primary_service,
        status=BookingStatus.COMPLETED,
        day_offset=-3,
    )
    _seed_booking(
        db,
        instructor=test_instructor_2,
        student=test_student,
        service=other_service,
        status=BookingStatus.COMPLETED,
        day_offset=-1,
    )

    # Create payment intents for the authenticated instructor's bookings
    db.add_all(
        [
            PaymentIntent(
                id=str(ULID()),
                booking_id=booking_one,
                stripe_payment_intent_id=f"pi_{ULID()}",
                amount=15000,
                application_fee=1800,
                status="succeeded",
            ),
            PaymentIntent(
                id=str(ULID()),
                booking_id=booking_two,
                stripe_payment_intent_id=f"pi_{ULID()}",
                amount=20000,
                application_fee=2400,
                status="succeeded",
            ),
        ]
    )
    db.add(
        PaymentIntent(
            id=str(ULID()),
            booking_id=_seed_booking(
                db,
                instructor=test_instructor_2,
                student=test_student,
                service=other_service,
                status=BookingStatus.COMPLETED,
                day_offset=-4,
            ),
            stripe_payment_intent_id=f"pi_{ULID()}",
            amount=5000,
            application_fee=600,
            status="succeeded",
        )
    )
    db.commit()

    response = client.get("/api/payments/earnings", headers=auth_headers_instructor)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["service_count"] == 2
    assert data["booking_count"] == 2
    # Instructor share should be total amount - fees for instructor's bookings
    assert data["total_earned"] == (15000 - 1800) + (20000 - 2400)
    assert pytest.approx(data["hours_invoiced"], rel=1e-3) == 2.0
    invoices = data.get("invoices", [])
    assert len(invoices) == 2
    assert {invoice["booking_id"] for invoice in invoices} == {booking_one, booking_two}
    assert all(invoice["status"] == "paid" for invoice in invoices)
    total_paid_values = sorted(invoice["total_paid_cents"] for invoice in invoices)
    assert total_paid_values == [15000, 20000]
    instructor_shares = sorted(invoice["instructor_share_cents"] for invoice in invoices)
    assert instructor_shares == sorted([(15000 - 1800), (20000 - 2400)])
