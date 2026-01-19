"""Additional coverage tests for Stripe service helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe

from app.core.exceptions import ServiceException
import app.services.stripe_service as stripe_service
from app.services.stripe_service import PRICING_DEFAULTS, StripeService


def _make_service() -> StripeService:
    service = StripeService.__new__(StripeService)
    service.db = MagicMock()
    service.instructor_repository = MagicMock()
    service.payment_repository = MagicMock()
    service.config_service = MagicMock()
    service.logger = MagicMock()
    return service


def _make_booking(*, hourly_rate: object) -> SimpleNamespace:
    return SimpleNamespace(
        id="booking_1",
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        service_name="Guitar Lessons",
        duration_minutes=60,
        hourly_rate=hourly_rate,
        student=SimpleNamespace(first_name="Alex", last_name="Rivera"),
    )


def test_get_instructor_earnings_summary_founding_rate_fallback():
    service = _make_service()
    profile = SimpleNamespace(id="inst_1", is_founding_instructor=True, current_tier_pct=None)
    service.instructor_repository.get_by_user_id.return_value = profile
    service.get_instructor_earnings = MagicMock(
        return_value={
            "total_earned": 100,
            "total_fees": 10,
            "booking_count": 1,
            "average_earning": 100.0,
            "period_start": None,
            "period_end": None,
        }
    )
    service.config_service.get_pricing_config.return_value = (
        {"founding_instructor_rate_pct": "bad", "student_fee_pct": 0.05},
        None,
    )

    booking = _make_booking(hourly_rate=object())
    payment = SimpleNamespace(
        booking=booking,
        amount=10000,
        application_fee=1000,
        status="succeeded",
        created_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        base_price_cents=None,
        instructor_tier_pct=None,
        instructor_payout_cents=None,
    )
    service.payment_repository.get_instructor_payment_history.return_value = [payment]

    with patch.object(
        stripe_service.RepositoryFactory,
        "create_review_tip_repository",
        return_value=MagicMock(),
    ):
        with patch.object(
            stripe_service, "build_student_payment_summary", side_effect=Exception("boom")
        ):
            result = service.get_instructor_earnings_summary(
                user=SimpleNamespace(id="user_1")
            )

    assert result.total_lesson_value == 0
    assert result.total_tips == 0
    assert result.invoices[0].lesson_price_cents == 0
    assert result.invoices[0].platform_fee_rate == float(
        PRICING_DEFAULTS["founding_instructor_rate_pct"]
    )


def test_get_instructor_earnings_summary_uses_current_tier_pct_percent_value():
    service = _make_service()
    profile = SimpleNamespace(id="inst_2", is_founding_instructor=False, current_tier_pct=15)
    service.instructor_repository.get_by_user_id.return_value = profile
    service.get_instructor_earnings = MagicMock(
        return_value={
            "total_earned": 12000,
            "total_fees": 1000,
            "booking_count": 1,
            "average_earning": 12000.0,
            "period_start": None,
            "period_end": None,
        }
    )
    service.config_service.get_pricing_config.return_value = (
        {"student_fee_pct": 0.05, "instructor_tiers": [{"min": 0, "pct": 0.2}]},
        None,
    )

    booking = _make_booking(hourly_rate=120)
    payment = SimpleNamespace(
        booking=booking,
        amount=12000,
        application_fee=0,
        status="succeeded",
        created_at=datetime(2030, 1, 2, tzinfo=timezone.utc),
        base_price_cents=12000,
        instructor_tier_pct=None,
        instructor_payout_cents=9000,
    )
    service.payment_repository.get_instructor_payment_history.return_value = [payment]

    with patch.object(
        stripe_service.RepositoryFactory,
        "create_review_tip_repository",
        return_value=MagicMock(),
    ):
        with patch.object(
            stripe_service,
            "build_student_payment_summary",
            return_value=SimpleNamespace(tip_paid=2.5),
        ):
            result = service.get_instructor_earnings_summary(
                user=SimpleNamespace(id="user_2")
            )

    assert result.total_tips == 250
    assert result.invoices[0].instructor_share_cents == 9000
    assert result.invoices[0].platform_fee_rate == 0.15


def test_build_earnings_export_rows_handles_outliers():
    service = _make_service()
    profile = SimpleNamespace(id="inst_3", is_founding_instructor=False, current_tier_pct=None)
    service.instructor_repository.get_by_user_id.return_value = profile
    service.config_service.get_pricing_config.return_value = (
        {"instructor_tiers": [{"min": 0, "pct": 0.1}]},
        None,
    )
    service.payment_repository.get_instructor_earnings_for_export.return_value = [
        {
            "lesson_date": date(2030, 2, 1),
            "student_name": "Sam",
            "service_name": "Piano",
            "duration_minutes": 60,
            "hourly_rate": 100,
            "payment_amount_cents": 0,
            "application_fee_cents": 0,
            "status": "succeeded",
            "payment_id": "pay_1",
        },
        {
            "lesson_date": date(2030, 2, 2),
            "student_name": "Lee",
            "service_name": "Voice",
            "duration_minutes": 60,
            "hourly_rate": 100,
            "payment_amount_cents": 15000,
            "application_fee_cents": 0,
            "status": "succeeded",
            "payment_id": "pay_2",
        },
        {
            "lesson_date": date(2030, 2, 3),
            "student_name": "Kai",
            "service_name": "Drums",
            "duration_minutes": 45,
            "hourly_rate": object(),
            "payment_amount_cents": 5000,
            "application_fee_cents": 1000,
            "status": "failed",
            "payment_id": "pay_3",
        },
    ]

    rows = service._build_earnings_export_rows(
        instructor_id="inst_3",
        start_date=None,
        end_date=None,
    )

    assert rows[0]["platform_fee_cents"] == 10000
    assert rows[1]["platform_fee_cents"] == 0
    assert rows[2]["lesson_price_cents"] == 0


def test_generate_earnings_pdf_builds_document():
    service = _make_service()
    row = {
        "lesson_date": date(2030, 3, 1),
        "student_name": "Student Name",
        "service_name": "Long Service Name",
        "duration_minutes": 90,
        "lesson_price_cents": 10000,
        "platform_fee_cents": 1000,
        "net_earnings_cents": 9000,
        "status": "Paid",
        "payment_id": "pay_123",
    }

    with patch.object(service, "_build_earnings_export_rows", return_value=[row]):
        pdf_bytes = service.generate_earnings_pdf(
            instructor_id="inst_4",
            start_date=None,
            end_date=None,
        )

    assert pdf_bytes.startswith(b"%PDF")


def test_start_instructor_onboarding_uses_origin_and_callback(monkeypatch):
    service = _make_service()
    profile = SimpleNamespace(id="inst_5")
    service.instructor_repository.get_by_user_id.return_value = profile
    service.payment_repository.get_connected_account_by_instructor_id.return_value = None
    service.create_connected_account = MagicMock(
        return_value=SimpleNamespace(stripe_account_id="acct_123")
    )
    service.create_account_link = MagicMock(return_value="onboard_link")

    monkeypatch.setattr(stripe_service.settings, "frontend_url", "https://app.example.com")
    monkeypatch.setattr(stripe_service.settings, "local_beta_frontend_origin", "")
    monkeypatch.setattr(stripe_service, "origin_from_header", lambda value: value)
    monkeypatch.setattr(stripe_service, "is_allowed_origin", lambda value: True)

    response = StripeService.start_instructor_onboarding(
        service,
        user=SimpleNamespace(id="user_3", email="user@example.com"),
        request_host="api.example.com",
        request_scheme="https",
        request_origin="https://header.example.com/path",
        request_referer=None,
        return_to="/instructor/onboarding/payment-setup",
    )

    assert response.account_id == "acct_123"
    assert response.onboarding_url == "onboard_link"
    create_kwargs = service.create_account_link.call_args.kwargs
    assert create_kwargs["refresh_url"] == "https://header.example.com/instructor/onboarding/start"
    assert (
        create_kwargs["return_url"]
        == "https://header.example.com/instructor/onboarding/payment-setup"
    )


def test_delete_payment_method_detach_and_delete_success():
    service = _make_service()
    service.payment_repository.delete_payment_method.return_value = True

    with patch.object(stripe.PaymentMethod, "detach", return_value=None) as detach_mock:
        result = StripeService.delete_payment_method(service, "pm_123", "user_1")

    assert result is True
    detach_mock.assert_called_once_with("pm_123")
    service.payment_repository.delete_payment_method.assert_called_once()


def test_delete_payment_method_detach_stripe_error():
    service = _make_service()
    service.payment_repository.delete_payment_method.return_value = True

    with patch.object(
        stripe.PaymentMethod,
        "detach",
        side_effect=stripe.error.StripeError(message="boom"),
    ):
        result = StripeService.delete_payment_method(service, "pm_123", "user_1")

    assert result is True
    service.payment_repository.delete_payment_method.assert_called_once()


def test_verify_webhook_signature_missing_secret(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(stripe_service, "settings", SimpleNamespace(stripe_webhook_secret=None))

    with pytest.raises(ServiceException):
        StripeService.verify_webhook_signature(service, b"payload", "sig")


def test_verify_webhook_signature_invalid(monkeypatch):
    service = _make_service()
    secret = SimpleNamespace(get_secret_value=lambda: "secret")
    monkeypatch.setattr(stripe_service, "settings", SimpleNamespace(stripe_webhook_secret=secret))

    with patch.object(
        stripe.Webhook,
        "construct_event",
        side_effect=stripe.SignatureVerificationError("bad", "sig"),
    ):
        result = StripeService.verify_webhook_signature(service, b"payload", "sig")

    assert result is False


def test_verify_webhook_signature_success(monkeypatch):
    service = _make_service()
    secret = SimpleNamespace(get_secret_value=lambda: "secret")
    monkeypatch.setattr(stripe_service, "settings", SimpleNamespace(stripe_webhook_secret=secret))

    with patch.object(stripe.Webhook, "construct_event", return_value={}):
        result = StripeService.verify_webhook_signature(service, b"payload", "sig")

    assert result is True


@pytest.mark.parametrize(
    ("event_type", "handler_name"),
    [
        ("payment_intent.succeeded", "handle_payment_intent_webhook"),
        ("account.updated", "_handle_account_webhook"),
        ("transfer.created", "_handle_transfer_webhook"),
        ("charge.succeeded", "_handle_charge_webhook"),
        ("payout.paid", "_handle_payout_webhook"),
        ("identity.verification_session.verified", "_handle_identity_webhook"),
    ],
)
def test_handle_webhook_event_routes(event_type: str, handler_name: str):
    service = _make_service()
    handler = MagicMock(return_value=True)
    setattr(service, handler_name, handler)

    result = StripeService.handle_webhook_event(service, {"type": event_type})

    assert result == {"success": True, "event_type": event_type}
    handler.assert_called_once()


def test_handle_webhook_event_unhandled():
    service = _make_service()
    result = StripeService.handle_webhook_event(service, {"type": "unknown.event"})

    assert result["handled"] is False


def test_top_up_from_pi_metadata_valid_and_zero():
    pi = SimpleNamespace(
        amount=8000,
        metadata={
            "base_price_cents": "10000",
            "platform_fee_cents": "1000",
            "student_fee_cents": "500",
            "applied_credit_cents": "0",
        },
    )
    assert StripeService._top_up_from_pi_metadata(pi) == 1000

    pi.amount = 9500
    assert StripeService._top_up_from_pi_metadata(pi) == 0


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"base_price_cents": "bad"},
        {
            "base_price_cents": "100",
            "platform_fee_cents": "10",
            "student_fee_cents": "5",
        },
        {
            "base_price_cents": "100",
            "platform_fee_cents": "10",
            "student_fee_cents": "5",
            "applied_credit_cents": "-1",
        },
    ],
)
def test_top_up_from_pi_metadata_invalid(metadata):
    pi = SimpleNamespace(amount=100, metadata=metadata)

    assert StripeService._top_up_from_pi_metadata(pi) is None
