"""
Integration tests for no-show reporting, dispute, and resolution flows.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import status

from app.core.ulid_helper import generate_ulid
from app.models.booking import BookingStatus
from app.models.booking_no_show import BookingNoShow
from app.models.booking_payment import BookingPayment
from app.models.payment import PaymentIntent, PlatformCredit
from app.services.booking_service import BookingService
from app.tasks.payment_tasks import resolve_undisputed_no_shows


@contextmanager
def _lock_acquired(*_args, **_kwargs):
    yield True


def _set_booking_times(booking, start_utc: datetime, duration_minutes: int = 60) -> None:
    end_utc = start_utc + timedelta(minutes=duration_minutes)
    booking.booking_start_utc = start_utc
    booking.booking_end_utc = end_utc
    booking.booking_date = start_utc.date()
    booking.start_time = start_utc.time().replace(microsecond=0)
    booking.end_time = end_utc.time().replace(microsecond=0)


def _safe_recent_start(now: datetime) -> datetime:
    start_utc = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    if start_utc.hour >= 23:
        start_utc = start_utc - timedelta(hours=2)
    return start_utc


def _create_reserved_credit(db, booking, amount_cents: int = 6000) -> PlatformCredit:
    credit = PlatformCredit(
        id=generate_ulid(),
        user_id=booking.student_id,
        amount_cents=amount_cents,
        reason="Test reserved credit",
        source_type="promo",
        reserved_amount_cents=amount_cents,
        reserved_for_booking_id=booking.id,
        reserved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        status="reserved",
    )
    db.add(credit)
    db.commit()
    return credit


def _get_no_show(db, booking_id: str) -> BookingNoShow | None:
    return db.query(BookingNoShow).filter(BookingNoShow.booking_id == booking_id).one_or_none()


def _ensure_payment_detail(db, booking, **fields) -> BookingPayment:
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).one_or_none()
    if bp is None:
        bp = BookingPayment(id=generate_ulid(), booking_id=booking.id)
        db.add(bp)
    for key, value in fields.items():
        setattr(bp, key, value)
    db.flush()
    booking.payment_detail = bp
    return bp


def _upsert_no_show(db, booking, **fields) -> BookingNoShow:
    no_show = _get_no_show(db, booking.id)
    if no_show is None:
        no_show = BookingNoShow(booking_id=booking.id)
        db.add(no_show)
    for key, value in fields.items():
        setattr(no_show, key, value)
    return no_show


class TestNoShowReporting:
    def test_student_can_report_instructor_no_show(
        self, client, db, test_booking, auth_headers_student
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show",
            json={"no_show_type": "instructor", "reason": "Instructor did not show"},
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["no_show_type"] == "instructor"

        db.refresh(test_booking)
        bp = db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none()
        no_show = _get_no_show(db, test_booking.id)
        assert bp is not None
        assert bp.payment_status == "manual_review"
        assert no_show is not None
        assert no_show.no_show_type == "instructor"

    def test_admin_can_report_any_no_show(
        self, client, db, test_booking, auth_headers_admin
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show",
            json={"no_show_type": "student", "reason": "Student did not attend"},
            headers=auth_headers_admin,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["no_show_type"] == "student"

    def test_instructor_cannot_report_student_no_show(
        self, client, db, test_booking, auth_headers_instructor
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show",
            json={"no_show_type": "student", "reason": "Student did not show"},
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_report_outside_window(
        self, client, db, test_booking, auth_headers_student
    ):
        past_start = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        _set_booking_times(test_booking, past_start)
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show",
            json={"no_show_type": "instructor", "reason": "Late report"},
            headers=auth_headers_student,
        )

        assert response.status_code == 422

    def test_cannot_report_for_cancelled_booking(
        self, client, db, test_booking, auth_headers_student
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        test_booking.status = BookingStatus.CANCELLED
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show",
            json={"no_show_type": "instructor", "reason": "Cancelled booking"},
            headers=auth_headers_student,
        )

        assert response.status_code == 422


class TestNoShowDispute:
    def test_accused_can_dispute_within_24h(
        self, client, db, test_booking, auth_headers_instructor
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=1),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        _ensure_payment_detail(db, test_booking, payment_status="manual_review")
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show/dispute",
            json={"reason": "I was present for the lesson."},
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_200_OK
        db.refresh(test_booking)
        no_show = _get_no_show(db, test_booking.id)
        assert no_show is not None
        assert no_show.no_show_disputed is True

    def test_cannot_dispute_after_24h(
        self, client, db, test_booking, auth_headers_instructor
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=25),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        _ensure_payment_detail(db, test_booking, payment_status="manual_review")
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show/dispute",
            json={"reason": "Dispute after window."},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 422

    def test_only_accused_can_dispute(
        self, client, db, test_booking, auth_headers_student
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=1),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        _ensure_payment_detail(db, test_booking, payment_status="manual_review")
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show/dispute",
            json={"reason": "Student should not dispute instructor no-show."},
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_dispute_twice(
        self, client, db, test_booking, auth_headers_instructor
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=1),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
            no_show_disputed=True,
            no_show_disputed_at=now - timedelta(minutes=30),
        )
        _ensure_payment_detail(db, test_booking, payment_status="manual_review")
        db.commit()

        response = client.post(
            f"/api/v1/bookings/{test_booking.id}/no-show/dispute",
            json={"reason": "Second dispute attempt."},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 422


class TestNoShowAutoResolution:
    def test_auto_resolve_undisputed_after_24h(self, db, test_booking):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=25),
            no_show_reported_by=test_booking.student_id,
            no_show_type="student",
        )
        pi_id = f"pi_{generate_ulid()}"
        _ensure_payment_detail(db, test_booking, payment_status="manual_review", payment_intent_id=pi_id)
        db.add(
            PaymentIntent(
                id=generate_ulid(),
                booking_id=test_booking.id,
                stripe_payment_intent_id=pi_id,
                amount=12000,
                application_fee=1200,
                status="requires_capture",
            )
        )
        db.commit()

        stripe_service_instance = MagicMock()
        stripe_service_instance.capture_payment_intent.return_value = {
            "payment_intent": {"id": "pi_test"},
            "amount_received": 12000,
        }

        with patch("app.tasks.payment_tasks.booking_lock_sync", _lock_acquired), patch(
            "app.services.stripe_service.StripeService",
            return_value=stripe_service_instance,
        ):
            results = resolve_undisputed_no_shows()

        assert results["resolved"] == 1
        db.refresh(test_booking)
        bp = db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none()
        no_show = _get_no_show(db, test_booking.id)
        assert no_show is not None
        assert no_show.no_show_resolution == "confirmed_no_dispute"
        assert bp is not None
        assert bp.payment_status == "settled"

    def test_disputed_not_auto_resolved(self, db, test_booking):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=25),
            no_show_reported_by=test_booking.student_id,
            no_show_type="student",
            no_show_disputed=True,
        )
        _ensure_payment_detail(db, test_booking, payment_status="manual_review")
        db.commit()

        with patch("app.tasks.payment_tasks.booking_lock_sync", _lock_acquired):
            results = resolve_undisputed_no_shows()

        assert results["resolved"] == 0
        db.refresh(test_booking)
        no_show = _get_no_show(db, test_booking.id)
        assert no_show is not None
        assert no_show.no_show_resolved_at is None


class TestNoShowAdminResolution:
    def test_admin_can_confirm_no_show(
        self, client, db, test_booking, auth_headers_admin
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=1),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        pi_id = f"pi_{generate_ulid()}"
        _ensure_payment_detail(db, test_booking, payment_status="settled", payment_intent_id=pi_id)
        db.commit()

        stripe_service_instance = MagicMock()
        stripe_service_instance.refund_payment.return_value = {"amount_refunded": 13440}

        with patch(
            "app.services.stripe_service.StripeService", return_value=stripe_service_instance
        ):
            response = client.post(
                f"/api/v1/admin/bookings/{test_booking.id}/no-show/resolve",
                json={"resolution": "confirmed_after_review", "admin_notes": "Verified"},
                headers=auth_headers_admin,
            )

        assert response.status_code == status.HTTP_200_OK
        db.refresh(test_booking)
        bp = db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none()
        assert bp is not None
        assert bp.settlement_outcome == "instructor_no_show_full_refund"
        assert bp.payment_status == "settled"

    def test_admin_can_uphold_dispute(
        self, client, db, test_booking, auth_headers_admin
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=2),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        pi_id = f"pi_{generate_ulid()}"
        _ensure_payment_detail(db, test_booking, payment_status="authorized", payment_intent_id=pi_id)
        db.commit()

        stripe_service_instance = MagicMock()
        stripe_service_instance.capture_payment_intent.return_value = {
            "payment_intent": {"id": "pi_test"},
            "amount_received": 12000,
        }

        with patch(
            "app.services.stripe_service.StripeService", return_value=stripe_service_instance
        ):
            response = client.post(
                f"/api/v1/admin/bookings/{test_booking.id}/no-show/resolve",
                json={"resolution": "dispute_upheld", "admin_notes": "Dispute upheld"},
                headers=auth_headers_admin,
            )

        assert response.status_code == status.HTTP_200_OK
        db.refresh(test_booking)
        bp = db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none()
        assert test_booking.status == BookingStatus.COMPLETED
        assert bp is not None
        assert bp.payment_status == "settled"

    def test_admin_can_cancel_report(
        self, client, db, test_booking, auth_headers_admin
    ):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=2),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        pi_id = f"pi_{generate_ulid()}"
        _ensure_payment_detail(db, test_booking, payment_status="manual_review", payment_intent_id=pi_id)
        db.add(
            PaymentIntent(
                id=generate_ulid(),
                booking_id=test_booking.id,
                stripe_payment_intent_id=pi_id,
                amount=12000,
                application_fee=1200,
                status="requires_capture",
            )
        )
        db.commit()

        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/no-show/resolve",
            json={"resolution": "cancelled", "admin_notes": "Invalid report"},
            headers=auth_headers_admin,
        )

        assert response.status_code == status.HTTP_200_OK
        db.refresh(test_booking)
        bp = db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none()
        no_show = _get_no_show(db, test_booking.id)
        assert no_show is not None
        assert no_show.no_show_resolution == "cancelled"
        assert bp is not None
        assert bp.payment_status == "authorized"


class TestNoShowSettlement:
    def test_instructor_no_show_releases_credits(self, db, test_booking):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=1),
            no_show_reported_by=test_booking.student_id,
            no_show_type="instructor",
        )
        pi_id = f"pi_{generate_ulid()}"
        _ensure_payment_detail(db, test_booking, payment_status="settled", payment_intent_id=pi_id)
        db.commit()

        credit = _create_reserved_credit(db, test_booking)

        stripe_service_instance = MagicMock()
        stripe_service_instance.refund_payment.return_value = {"amount_refunded": 13440}

        with patch(
            "app.services.stripe_service.StripeService", return_value=stripe_service_instance
        ):
            BookingService(db).resolve_no_show(
                booking_id=test_booking.id,
                resolution="confirmed_after_review",
                resolved_by=None,
                admin_notes=None,
            )

        db.refresh(credit)
        assert credit.status == "available"
        assert credit.reserved_amount_cents == 0

    def test_student_no_show_forfeits_credits(self, db, test_booking):
        now = datetime.now(timezone.utc)
        _set_booking_times(test_booking, _safe_recent_start(now))
        _upsert_no_show(
            db,
            test_booking,
            no_show_reported_at=now - timedelta(hours=1),
            no_show_reported_by=test_booking.student_id,
            no_show_type="student",
        )
        pi_id = f"pi_{generate_ulid()}"
        _ensure_payment_detail(db, test_booking, payment_status="authorized", payment_intent_id=pi_id)
        db.add(
            PaymentIntent(
                id=generate_ulid(),
                booking_id=test_booking.id,
                stripe_payment_intent_id=pi_id,
                amount=12000,
                application_fee=1200,
                status="requires_capture",
            )
        )
        db.commit()

        credit = _create_reserved_credit(db, test_booking)

        stripe_service_instance = MagicMock()
        stripe_service_instance.capture_payment_intent.return_value = {
            "payment_intent": {"id": "pi_test"},
            "amount_received": 12000,
        }

        with patch(
            "app.services.stripe_service.StripeService", return_value=stripe_service_instance
        ):
            BookingService(db).resolve_no_show(
                booking_id=test_booking.id,
                resolution="confirmed_after_review",
                resolved_by=None,
                admin_notes=None,
            )

        db.refresh(credit)
        db.refresh(test_booking)
        bp = db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none()
        assert credit.status == "forfeited"
        assert credit.reserved_amount_cents == 0
        assert bp is not None
        assert bp.settlement_outcome == "student_no_show_full_payout"
