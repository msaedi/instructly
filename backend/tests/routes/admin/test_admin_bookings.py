from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.audit_log import AuditLog
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentEvent, PaymentIntent
from app.models.service_catalog import InstructorService

try:  # pragma: no cover - support running from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_related_booking(
    db,
    base_booking: Booking,
    *,
    booking_date: date,
    status: BookingStatus,
    offset_index: int,
    payment_status: str | None = None,
    payment_intent_id: str | None = None,
    service_name: str | None = None,
) -> Booking:
    booking = create_booking_pg_safe(
        db,
        student_id=base_booking.student_id,
        instructor_id=base_booking.instructor_id,
        instructor_service_id=base_booking.instructor_service_id,
        booking_date=booking_date,
        start_time=base_booking.start_time,
        end_time=base_booking.end_time,
        service_name=service_name or base_booking.service_name,
        hourly_rate=base_booking.hourly_rate,
        total_price=base_booking.total_price,
        duration_minutes=base_booking.duration_minutes,
        status=status,
        offset_index=offset_index,
    )
    if payment_status is not None:
        booking.payment_status = payment_status
    if payment_intent_id is not None:
        booking.payment_intent_id = payment_intent_id
    db.flush()
    return booking


def _attach_payment_details(db, booking: Booking, *, amount_cents: int, fee_cents: int) -> str:
    payment_intent_id = booking.payment_intent_id or f"pi_{generate_ulid()}"
    booking.payment_intent_id = payment_intent_id
    booking.payment_status = "settled"
    booking.completed_at = booking.completed_at or datetime.now(timezone.utc)
    booking.status = BookingStatus.COMPLETED
    db.flush()

    intent = PaymentIntent(
        booking_id=booking.id,
        stripe_payment_intent_id=payment_intent_id,
        amount=amount_cents,
        application_fee=fee_cents,
        status="succeeded",
        base_price_cents=amount_cents - fee_cents,
        instructor_payout_cents=amount_cents - fee_cents,
    )
    db.add(intent)
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
    return payment_intent_id


def _get_active_service_id(db, instructor_id: str) -> str:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise RuntimeError("Instructor profile not found for stats test")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if not service:
        raise RuntimeError("Active service not found for stats test")
    return service.id


class TestAdminBookingsList:
    """GET /api/v1/admin/bookings"""

    def test_list_bookings_requires_admin(self, client, auth_headers):
        response = client.get("/api/v1/admin/bookings", headers=auth_headers)
        assert response.status_code == 403

    def test_list_bookings_with_search(self, client, auth_headers_admin, test_booking):
        response = client.get(
            "/api/v1/admin/bookings",
            params={"search": test_booking.id},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == test_booking.id for item in data["bookings"])

        response = client.get(
            "/api/v1/admin/bookings",
            params={"search": "Student"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == test_booking.id for item in data["bookings"])

        response = client.get(
            "/api/v1/admin/bookings",
            params={"search": "Instructor"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == test_booking.id for item in data["bookings"])

    def test_list_bookings_filter_by_status(self, client, auth_headers_admin, test_booking, db):
        cancelled = _create_related_booking(
            db,
            test_booking,
            booking_date=date.today(),
            status=BookingStatus.CANCELLED,
            offset_index=1,
        )

        response = client.get(
            "/api/v1/admin/bookings",
            params={"status": "CANCELLED"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == cancelled.id for item in data["bookings"])
        assert all(item["status"] == "CANCELLED" for item in data["bookings"])

    def test_list_bookings_filter_by_payment_status(self, client, auth_headers_admin, test_booking, db):
        refunded = _create_related_booking(
            db,
            test_booking,
            booking_date=date.today(),
            status=BookingStatus.CANCELLED,
            offset_index=2,
            payment_status="settled",
        )
        refunded.settlement_outcome = "admin_refund"
        db.commit()

        response = client.get(
            "/api/v1/admin/bookings",
            params={"payment_status": "refunded"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == refunded.id for item in data["bookings"])
        assert all(item["payment_status"] == "settled" for item in data["bookings"])

    def test_list_bookings_filter_by_date_range(self, client, auth_headers_admin, test_booking, db):
        past_booking = _create_related_booking(
            db,
            test_booking,
            booking_date=date.today() - timedelta(days=14),
            status=BookingStatus.CONFIRMED,
            offset_index=3,
        )

        response = client.get(
            "/api/v1/admin/bookings",
            params={
                "date_from": (date.today() - timedelta(days=2)).isoformat(),
                "date_to": (date.today() + timedelta(days=2)).isoformat(),
            },
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        ids = {item["id"] for item in data["bookings"]}
        assert test_booking.id in ids
        assert past_booking.id not in ids

    def test_list_bookings_pagination(self, client, auth_headers_admin, test_booking, db):
        _create_related_booking(
            db,
            test_booking,
            booking_date=date.today(),
            status=BookingStatus.CONFIRMED,
            offset_index=200,
        )
        _create_related_booking(
            db,
            test_booking,
            booking_date=date.today(),
            status=BookingStatus.CONFIRMED,
            offset_index=400,
        )

        response = client.get(
            "/api/v1/admin/bookings",
            params={"page": 1, "per_page": 2},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["per_page"] == 2
        assert len(data["bookings"]) == 2
        assert data["total"] >= 3
        assert data["total_pages"] >= 2


class TestAdminBookingDetail:
    """GET /api/v1/admin/bookings/{id}"""

    def test_get_booking_detail(self, client, auth_headers_admin, db, test_booking):
        payment_intent_id = _attach_payment_details(
            db,
            test_booking,
            amount_cents=12000,
            fee_cents=1200,
        )

        response = client.get(
            f"/api/v1/admin/bookings/{test_booking.id}",
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_booking.id
        assert data["payment"]["payment_intent_id"] == payment_intent_id
        assert data["payment"]["total_price"] == float(test_booking.total_price)

    def test_get_booking_not_found(self, client, auth_headers_admin):
        response = client.get(
            f"/api/v1/admin/bookings/{generate_ulid()}",
            headers=auth_headers_admin,
        )
        assert response.status_code == 404

    def test_detail_includes_payment_breakdown(self, client, auth_headers_admin, db, test_booking):
        _attach_payment_details(db, test_booking, amount_cents=15000, fee_cents=2000)

        response = client.get(
            f"/api/v1/admin/bookings/{test_booking.id}",
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        payment = data["payment"]
        assert payment["lesson_price"] == pytest.approx(130.0)
        assert payment["platform_fee"] == pytest.approx(20.0)
        assert payment["instructor_payout"] == pytest.approx(130.0)

    def test_detail_includes_timeline(self, client, auth_headers_admin, db, test_booking):
        _attach_payment_details(db, test_booking, amount_cents=9000, fee_cents=900)

        response = client.get(
            f"/api/v1/admin/bookings/{test_booking.id}",
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        events = {item["event"] for item in data["timeline"]}
        assert "booking_created" in events
        assert "payment_authorized" in events
        assert "payment_captured" in events


class TestAdminBookingStats:
    """GET /api/v1/admin/bookings/stats"""

    def test_get_stats_today(self, client, auth_headers_admin, db, test_student, test_instructor_with_availability):
        today = datetime.now(timezone.utc).date()
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)
        booking = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=today,
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_name="Stats Lesson",
            hourly_rate=100,
            total_price=100,
            duration_minutes=60,
            status=BookingStatus.COMPLETED,
            offset_index=0,
        )
        booking.payment_intent_id = f"pi_{generate_ulid()}"
        db.add(
            PaymentIntent(
                booking_id=booking.id,
                stripe_payment_intent_id=booking.payment_intent_id,
                amount=10000,
                application_fee=1000,
                status="succeeded",
            )
        )
        db.commit()

        response = client.get("/api/v1/admin/bookings/stats", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert data["today"]["booking_count"] == 1
        assert data["today"]["revenue"] == pytest.approx(100.0)

    def test_get_stats_this_week(self, client, auth_headers_admin, db, test_student, test_instructor_with_availability):
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1) if today.weekday() > 0 else today
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)

        booking_today = create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=today,
            start_time=time(11, 0),
            end_time=time(12, 0),
            service_name="Week Lesson",
            hourly_rate=80,
            total_price=80,
            duration_minutes=60,
            status=BookingStatus.COMPLETED,
            offset_index=0,
        )
        create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=yesterday,
            start_time=time(13, 0),
            end_time=time(14, 0),
            service_name="Week Lesson 2",
            hourly_rate=75,
            total_price=75,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=1,
        )

        booking_today.payment_intent_id = f"pi_{generate_ulid()}"
        db.add(
            PaymentIntent(
                booking_id=booking_today.id,
                stripe_payment_intent_id=booking_today.payment_intent_id,
                amount=8000,
                application_fee=800,
                status="succeeded",
            )
        )
        db.commit()

        response = client.get("/api/v1/admin/bookings/stats", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert data["this_week"]["gmv"] == pytest.approx(155.0)
        assert data["this_week"]["platform_revenue"] == pytest.approx(8.0)

    def test_get_stats_needs_action(
        self, client, auth_headers_admin, db, test_student, test_instructor_with_availability
    ):
        yesterday = date.today() - timedelta(days=1)
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)
        create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=yesterday,
            start_time=time(8, 0),
            end_time=time(9, 0),
            service_name="Needs Action Lesson",
            hourly_rate=60,
            total_price=60,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=0,
        )
        db.commit()

        response = client.get("/api/v1/admin/bookings/stats", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert data["needs_action"]["pending_completion"] == 1


class TestAdminAuditLog:
    """GET /api/v1/admin/audit-log"""

    def test_list_audit_log(self, client, auth_headers_admin, db, test_booking, admin_user):
        entry = AuditLog.from_change(
            entity_type="booking",
            entity_id=test_booking.id,
            action="admin_refund",
            actor={"id": admin_user.id, "role": "admin"},
            before={},
            after={"refund": {"amount_cents": 5000, "reason": "dispute"}},
        )
        db.add(entry)
        db.commit()

        response = client.get("/api/v1/admin/audit-log", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(item["action"] == "admin_refund" for item in data["entries"])

    def test_filter_by_action(self, client, auth_headers_admin, db, test_booking, admin_user):
        db.add(
            AuditLog.from_change(
                entity_type="booking",
                entity_id=test_booking.id,
                action="admin_cancel",
                actor={"id": admin_user.id, "role": "admin"},
                before={},
                after={"admin_cancel": {"reason": "ops"}},
            )
        )
        db.add(
            AuditLog.from_change(
                entity_type="booking",
                entity_id=test_booking.id,
                action="status_change",
                actor={"id": admin_user.id, "role": "admin"},
                before={},
                after={"status_change": {"from": "CONFIRMED", "to": "NO_SHOW"}},
            )
        )
        db.commit()

        response = client.get(
            "/api/v1/admin/audit-log",
            params={"action": "admin_cancel"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert all(item["action"] == "admin_cancel" for item in data["entries"])

    def test_filter_by_admin(self, client, auth_headers_admin, db, test_booking, admin_user):
        db.add(
            AuditLog.from_change(
                entity_type="booking",
                entity_id=test_booking.id,
                action="admin_refund",
                actor={"id": admin_user.id, "role": "admin"},
                before={},
                after={"refund": {"amount_cents": 2500}},
            )
        )
        db.add(
            AuditLog.from_change(
                entity_type="booking",
                entity_id=test_booking.id,
                action="admin_refund",
                actor={"id": "system", "role": "system"},
                before={},
                after={"refund": {"amount_cents": 3500}},
            )
        )
        db.commit()

        response = client.get(
            "/api/v1/admin/audit-log",
            params={"admin_id": admin_user.id},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert all(item["admin"]["id"] == admin_user.id for item in data["entries"])

    def test_includes_summary(self, client, auth_headers_admin, db, test_booking, admin_user):
        db.add(
            AuditLog.from_change(
                entity_type="booking",
                entity_id=test_booking.id,
                action="admin_refund",
                actor={"id": admin_user.id, "role": "admin"},
                before={},
                after={"refund": {"amount_cents": 4200}},
            )
        )
        db.add(
            PaymentEvent(
                booking_id=test_booking.id,
                event_type="payment_captured",
                event_data={"amount_captured_cents": 9000},
            )
        )
        db.commit()

        response = client.get("/api/v1/admin/audit-log", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["refunds_count"] == 1
        assert data["summary"]["refunds_total"] == pytest.approx(42.0)
        assert data["summary"]["captures_count"] == 1
        assert data["summary"]["captures_total"] == pytest.approx(90.0)


class TestAdminCancelBooking:
    """POST /api/v1/admin/bookings/{id}/cancel"""

    @patch("app.services.stripe_service.StripeService.refund_payment")
    def test_admin_cancel_with_refund(
        self,
        mock_refund_payment,
        client,
        db,
        test_booking,
        auth_headers_admin,
    ):
        test_booking.payment_intent_id = "pi_cancel"
        test_booking.payment_status = "settled"
        db.commit()

        mock_refund_payment.return_value = {"refund_id": "re_cancel"}

        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/cancel",
            json={"reason": "dispute", "note": "Test cancel", "refund": True},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["refund_issued"] is True
        assert data["refund_id"] == "re_cancel"

        db.refresh(test_booking)
        assert test_booking.status == BookingStatus.CANCELLED
        assert test_booking.payment_status == "settled"
        assert test_booking.settlement_outcome == "admin_refund"

    def test_admin_cancel_without_refund(self, client, db, test_booking, auth_headers_admin):
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/cancel",
            json={"reason": "schedule", "note": "No refund", "refund": False},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["refund_issued"] is False

        db.refresh(test_booking)
        assert test_booking.status == BookingStatus.CANCELLED

    def test_cancel_creates_audit_log(
        self,
        client,
        db,
        test_booking,
        auth_headers_admin,
        admin_user,
    ):
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/cancel",
            json={"reason": "ops", "note": "Cancel audit"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200

        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_id == test_booking.id, AuditLog.action == "admin_cancel")
            .first()
        )
        assert log is not None
        assert log.actor_id == admin_user.id

    def test_cancel_already_cancelled(self, client, db, test_booking, auth_headers_admin):
        test_booking.status = BookingStatus.CANCELLED
        db.commit()

        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/cancel",
            json={"reason": "ops"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 400


class TestAdminCompleteBooking:
    """POST /api/v1/admin/bookings/{id}/complete"""

    def test_mark_complete(self, client, db, test_booking, auth_headers_admin):
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/complete",
            json={"status": "COMPLETED"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        db.refresh(test_booking)
        assert test_booking.status == BookingStatus.COMPLETED

    def test_mark_no_show(self, client, db, test_booking, auth_headers_admin):
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/complete",
            json={"status": "NO_SHOW"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        db.refresh(test_booking)
        assert test_booking.status == BookingStatus.NO_SHOW

    def test_complete_creates_audit_log(self, client, db, test_booking, auth_headers_admin, admin_user):
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/complete",
            json={"status": "COMPLETED", "note": "Completed by admin"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200

        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_id == test_booking.id, AuditLog.action == "status_change")
            .first()
        )
        assert log is not None
        assert log.actor_id == admin_user.id
