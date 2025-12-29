from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentEvent, PaymentIntent
from app.models.service_catalog import InstructorService
from app.services.admin_booking_service import AdminBookingService

try:  # pragma: no cover - support running from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _get_active_service_id(db, instructor_id: str) -> str:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise RuntimeError("Instructor profile not found for admin booking service test")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if not service:
        raise RuntimeError("Active service not found for admin booking service test")
    return service.id


def _create_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    status: BookingStatus,
    offset_index: int,
    service_name: str,
    payment_status: str | None = None,
) -> Booking:
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name=service_name,
        hourly_rate=75,
        total_price=75,
        duration_minutes=60,
        status=status,
        offset_index=offset_index,
    )
    if payment_status is not None:
        booking.payment_status = payment_status
    db.flush()
    return booking


def _attach_payment_events(db, booking: Booking, *, amount_cents: int) -> None:
    booking.payment_intent_id = booking.payment_intent_id or f"pi_{generate_ulid()}"
    booking.payment_status = "settled"
    booking.created_at = booking.created_at or datetime.now(timezone.utc)
    booking.completed_at = booking.completed_at or datetime.now(timezone.utc)
    booking.status = BookingStatus.COMPLETED
    db.flush()

    db.add(
        PaymentIntent(
            booking_id=booking.id,
            stripe_payment_intent_id=booking.payment_intent_id,
            amount=amount_cents,
            application_fee=1000,
            status="succeeded",
        )
    )
    db.add(
        PaymentEvent(
            booking_id=booking.id,
            event_type="auth_succeeded",
            event_data={"amount_cents": amount_cents},
        )
    )
    db.add(
        PaymentEvent(
            booking_id=booking.id,
            event_type="payment_captured",
            event_data={"amount_captured_cents": amount_cents},
        )
    )
    db.commit()


class TestAdminBookingService:
    def test_get_bookings_with_filters(self, db, test_student, test_instructor_with_availability):
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)
        booking_refunded = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=date.today(),
            status=BookingStatus.CANCELLED,
            offset_index=0,
            service_name="Refunded Lesson",
            payment_status="settled",
        )
        booking_refunded.settlement_outcome = "admin_refund"
        booking_captured = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=date.today(),
            status=BookingStatus.CONFIRMED,
            offset_index=1,
            service_name="Captured Lesson",
            payment_status = "settled",
        )

        service = AdminBookingService(db)
        response = service.list_bookings(
            search="Refunded",
            statuses=["CANCELLED"],
            payment_statuses=["refunded"],
            date_from=None,
            date_to=None,
            needs_action=None,
            page=1,
            per_page=20,
        )
        ids = [item.id for item in response.bookings]
        assert booking_refunded.id in ids
        assert booking_captured.id not in ids

    def test_build_timeline(self, db, test_booking):
        _attach_payment_events(db, test_booking, amount_cents=9000)
        service = AdminBookingService(db)
        detail = service.get_booking_detail(test_booking.id)

        assert detail is not None
        events = {item.event for item in detail.timeline}
        assert "booking_created" in events
        assert "lesson_completed" in events
        assert "payment_authorized" in events
        assert "payment_captured" in events

    def test_calculate_stats(self, db, test_student, test_instructor_with_availability):
        fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        today = fixed_now.date()
        yesterday = today - timedelta(days=1)
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)

        booking_today = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=today,
            status=BookingStatus.COMPLETED,
            offset_index=0,
            service_name="Stats Lesson",
        )
        _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=yesterday,
            status=BookingStatus.CONFIRMED,
            offset_index=1,
            service_name="Stats Lesson 2",
        )

        booking_today.payment_intent_id = f"pi_{generate_ulid()}"
        db.add(
            PaymentIntent(
                booking_id=booking_today.id,
                stripe_payment_intent_id=booking_today.payment_intent_id,
                amount=7500,
                application_fee=750,
                status="succeeded",
            )
        )
        db.commit()

        service = AdminBookingService(db)

        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with patch("app.services.admin_booking_service.datetime", _FixedDateTime):
            stats = service.get_booking_stats()
        assert stats.today.booking_count == 1
        assert stats.today.revenue == pytest.approx(75.0)
        assert stats.this_week.gmv == pytest.approx(150.0)
        assert stats.this_week.platform_revenue == pytest.approx(7.5)
        assert stats.needs_action.pending_completion == 1
