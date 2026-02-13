from __future__ import annotations

from datetime import date, datetime, timezone
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.core.exceptions import ServiceException
from app.models.booking import BookingStatus, PaymentStatus
from app.services import admin_booking_service as admin_module
from app.services.admin_booking_service import AdminBookingService


@pytest.fixture
def service() -> AdminBookingService:
    db = Mock()
    svc = AdminBookingService(db)
    svc.booking_repo = Mock()
    svc.payment_repo = Mock()
    svc.audit_repo = Mock()
    svc.user_repo = Mock()
    return svc


def _make_booking(**overrides: object) -> Mock:
    booking = Mock()
    booking.id = overrides.get("id", "booking-1")
    booking.status = overrides.get("status", BookingStatus.CONFIRMED)
    booking.refunded_to_card_amount = overrides.get("refunded_to_card_amount", 0)
    booking.to_dict.return_value = overrides.get("to_dict", {})
    booking.created_at = overrides.get("created_at", datetime(2024, 1, 1, tzinfo=timezone.utc))
    booking.updated_at = overrides.get("updated_at", None)
    booking.completed_at = overrides.get("completed_at", None)
    booking.cancelled_at = overrides.get("cancelled_at", None)
    booking.service_name = overrides.get("service_name", "Guitar")
    booking.duration_minutes = overrides.get("duration_minutes", 60)
    booking.hourly_rate = overrides.get("hourly_rate", "20")
    booking.total_price = overrides.get("total_price", 30)
    booking.student = overrides.get("student", None)
    booking.instructor = overrides.get("instructor", None)
    booking.booking_date = overrides.get("booking_date", date(2024, 1, 1))
    booking.start_time = overrides.get("start_time", datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc).time())
    booking.end_time = overrides.get("end_time", datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc).time())

    # Payment fields live on the payment_detail satellite
    pd = Mock()
    pd.payment_intent_id = overrides.get("payment_intent_id", "pi_123")
    pd.settlement_outcome = overrides.get("settlement_outcome", None)
    pd.payment_status = overrides.get("payment_status", PaymentStatus.AUTHORIZED.value)
    pd.credits_reserved_cents = overrides.get("credits_reserved_cents", 1000)
    booking.payment_detail = pd
    return booking


class TestAdminBookingServiceCancel:
    def test_cancel_booking_raises_when_already_refunded(self, service: AdminBookingService) -> None:
        booking = _make_booking(refunded_to_card_amount=1200)
        service.booking_repo.get_booking_with_details.return_value = booking

        with pytest.raises(ServiceException):
            service.cancel_booking(
                booking_id="booking-1",
                reason="admin-test",
                note=None,
                refund=True,
                actor=Mock(id="admin-1"),
            )

    def test_cancel_booking_returns_none_when_missing_after_refund(
        self, service: AdminBookingService
    ) -> None:
        booking = _make_booking()
        service.booking_repo.get_booking_with_details.side_effect = [booking, None]
        service._resolve_full_refund_cents = Mock(return_value=2500)
        service._issue_refund = Mock(return_value={"refund_id": "re_123"})

        result_booking, refund_id = service.cancel_booking(
            booking_id="booking-1",
            reason="admin-test",
            note=None,
            refund=True,
            actor=Mock(id="admin-1"),
        )

        assert result_booking is None
        assert refund_id == "re_123"

    def test_cancel_booking_credit_release_failure_logs_warning(
        self, service: AdminBookingService, monkeypatch
    ) -> None:
        booking = _make_booking(payment_intent_id=None)
        service.booking_repo.get_booking_with_details.return_value = booking
        service.booking_repo.ensure_payment.return_value = booking.payment_detail

        fake_credit_module = ModuleType("app.services.credit_service")

        class FakeCreditService:
            def __init__(self, _db: object) -> None:
                pass

            def release_credits_for_booking(self, *_args: object, **_kwargs: object) -> None:
                raise RuntimeError("credit release failed")

        fake_credit_module.CreditService = FakeCreditService
        monkeypatch.setitem(sys.modules, "app.services.credit_service", fake_credit_module)
        monkeypatch.setattr(admin_module, "AUDIT_ENABLED", False)

        with patch.object(admin_module.logger, "warning") as mock_warning:
            service.cancel_booking(
                booking_id="booking-1",
                reason="admin-test",
                note=None,
                refund=False,
                actor=Mock(id="admin-1"),
            )

        assert mock_warning.called

    def test_cancel_booking_refund_updates_payment_and_audit(
        self, service: AdminBookingService, monkeypatch
    ) -> None:
        booking = _make_booking()
        bp_mock = booking.payment_detail
        service.booking_repo.get_booking_with_details.return_value = booking
        service.booking_repo.ensure_payment.return_value = bp_mock
        service._resolve_full_refund_cents = Mock(return_value=1200)
        service._issue_refund = Mock(return_value={"refund_id": "re_456"})

        fake_credit_module = ModuleType("app.services.credit_service")

        class FakeCreditService:
            def __init__(self, _db: object) -> None:
                pass

            def release_credits_for_booking(self, *_args: object, **_kwargs: object) -> None:
                return None

        fake_credit_module.CreditService = FakeCreditService
        monkeypatch.setitem(sys.modules, "app.services.credit_service", fake_credit_module)
        monkeypatch.setattr(admin_module, "AUDIT_ENABLED", True)

        updated_booking, refund_id = service.cancel_booking(
            booking_id="booking-1",
            reason="admin-test",
            note="note",
            refund=True,
            actor=Mock(id="admin-1"),
        )

        assert updated_booking is booking
        assert refund_id == "re_456"
        assert bp_mock.payment_status == PaymentStatus.SETTLED.value
        assert bp_mock.settlement_outcome == "admin_refund"
        assert booking.refunded_to_card_amount == 1200
        assert service.audit_repo.write.call_count == 2


class TestAdminBookingServiceStatus:
    def test_update_booking_status_returns_none_when_missing(self, service: AdminBookingService) -> None:
        service.booking_repo.get_booking_with_details.return_value = None

        assert (
            service.update_booking_status(
                booking_id="booking-1",
                status=BookingStatus.COMPLETED,
                note=None,
                actor=Mock(id="admin-1"),
            )
            is None
        )

    def test_update_booking_status_logs_audit(self, service: AdminBookingService, monkeypatch) -> None:
        booking = _make_booking()
        booking.complete = Mock()
        service.booking_repo.get_booking_with_details.return_value = booking

        monkeypatch.setattr(admin_module, "AUDIT_ENABLED", True)

        with patch.object(admin_module.AuditLog, "from_change", return_value=Mock()) as _:
            service.update_booking_status(
                booking_id="booking-1",
                status=BookingStatus.COMPLETED,
                note="note",
                actor=Mock(id="admin-1"),
            )

        booking.complete.assert_called_once()
        service.audit_repo.write.assert_called_once()


class TestAdminBookingServiceHelpers:
    def test_build_payment_info_sets_stripe_url(self, service: AdminBookingService) -> None:
        booking = _make_booking()
        service._resolve_lesson_price_cents = Mock(return_value=1000)
        service._resolve_platform_fee_cents = Mock(return_value=200)
        service._resolve_instructor_payout_cents = Mock(return_value=800)

        payment_info = service._build_payment_info(booking, payment_intent=None, credits_applied_cents=0)

        assert "stripe.com" in payment_info.stripe_url
        assert booking.payment_detail.payment_intent_id in payment_info.stripe_url

    def test_resolve_payment_intent_handles_exception(self, service: AdminBookingService) -> None:
        booking = _make_booking()
        service.payment_repo.get_payment_by_intent_id.side_effect = RuntimeError("boom")

        assert service._resolve_payment_intent(booking) is None

    def test_resolve_credit_applied_cents_from_event(self, service: AdminBookingService) -> None:
        event = SimpleNamespace(event_type="credits_applied", event_data={"applied_cents": 700})

        assert service._resolve_credit_applied_cents([event]) == 700

    def test_resolve_platform_fee_cents_default(self, service: AdminBookingService) -> None:
        assert service._resolve_platform_fee_cents(payment_intent=None) == 0

    def test_resolve_instructor_payout_from_amount(self, service: AdminBookingService) -> None:
        payment_intent = SimpleNamespace(instructor_payout_cents=None, amount=1500)

        assert service._resolve_instructor_payout_cents(payment_intent, platform_fee_cents=200) == 1300
        assert service._resolve_instructor_payout_cents(None, platform_fee_cents=200) == 0

    def test_resolve_full_refund_cents_paths(self, service: AdminBookingService) -> None:
        booking = _make_booking()
        payment_record = SimpleNamespace(amount=2500)
        service.payment_repo.get_payment_by_intent_id.return_value = payment_record

        assert service._resolve_full_refund_cents(booking) == 2500

        booking.payment_detail.payment_intent_id = "pi_missing"
        service.payment_repo.get_payment_by_intent_id.return_value = None
        booking.total_price = None

        assert service._resolve_full_refund_cents(booking) == 0

    def test_issue_refund_wraps_generic_exception(self, service: AdminBookingService, monkeypatch) -> None:
        booking = _make_booking()

        class FakeStripeService:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def refund_payment(self, **_kwargs: object) -> dict[str, object]:
                raise RuntimeError("stripe down")

        monkeypatch.setattr(admin_module, "StripeService", FakeStripeService)

        with pytest.raises(ServiceException) as exc_info:
            service._issue_refund(booking=booking, amount_cents=1000, reason="reason")

        assert exc_info.value.code == "stripe_error"

    def test_build_audit_summary_sums_refunds_and_captures(self, service: AdminBookingService) -> None:
        refund_entry = SimpleNamespace(
            action="admin_refund",
            after={"refund": {"amount_cents": 1200}},
        )
        bad_refund_entry = SimpleNamespace(
            action="admin_refund",
            after={"refund": {"amount_cents": "bad"}},
        )
        service.audit_repo.list_for_booking_actions.return_value = ([refund_entry, bad_refund_entry], 2)

        capture_event = SimpleNamespace(event_data={"amount_captured_cents": 500})
        service.payment_repo.list_payment_events_by_types.return_value = [capture_event]

        summary = service._build_audit_summary(admin_id=None, date_from=None, date_to=None)

        assert summary.refunds_count == 2
        assert summary.refunds_total == 12.0
        assert summary.captures_count == 1
        assert summary.captures_total == 5.0

    def test_extract_audit_details_status_change(self, service: AdminBookingService) -> None:
        entry = SimpleNamespace(action="status_change", after={"status_change": {"from": "x"}})

        assert service._extract_audit_details(entry) == {"from": "x"}

    def test_build_person_returns_unknown_for_missing_user(self, service: AdminBookingService) -> None:
        person = service._build_person(None, include_phone=True)

        assert person.id == ""
        assert person.name == "Unknown"
        assert person.email == ""

    def test_to_float_handles_none_and_invalid(self, service: AdminBookingService) -> None:
        assert service._to_float(None) == 0.0
        assert service._to_float("not-a-number") == 0.0

    def test_extract_cents_skips_invalid_values(self, service: AdminBookingService) -> None:
        data = {"amount": "bad", "amount_cents": None}
        assert service._extract_cents(data, ("amount", "amount_cents")) is None

    def test_date_range_bounds_sets_timezone(self, service: AdminBookingService) -> None:
        start, end = service._date_range_bounds(date(2024, 1, 1), date(2024, 1, 2))

        assert start is not None
        assert end is not None
        assert start.tzinfo is not None
        assert end.tzinfo is not None
        assert start.tzinfo.utcoffset(start) is not None
        assert end.tzinfo.utcoffset(end) is not None
