from datetime import datetime, timezone

from pydantic import ValidationError
import pytest

from app.schemas.payment_schemas import (
    CreateCheckoutRequest,
    DashboardLinkResponse,
    InstantPayoutResponse,
    SavePaymentMethodRequest,
    WebhookResponse,
)


def test_create_checkout_request_rejects_negative_credit() -> None:
    with pytest.raises(ValidationError):
        CreateCheckoutRequest(
            booking_id="bk_test",
            payment_method_id="pm_test",
            requested_credit_cents=-1,
        )


def test_create_checkout_request_defaults() -> None:
    payload = CreateCheckoutRequest(booking_id="bk_test")
    assert payload.payment_method_id is None
    assert payload.save_payment_method is False
    assert payload.requested_credit_cents is None


def test_save_payment_method_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SavePaymentMethodRequest(
            payment_method_id="pm_test",
            set_as_default=True,
            unexpected=True,
        )


def test_dashboard_link_response_defaults_expiry() -> None:
    payload = DashboardLinkResponse(dashboard_url="https://stripe.test/dashboard")
    assert payload.expires_in_minutes == 5


def test_instant_payout_response_allows_optional_fields() -> None:
    payload = InstantPayoutResponse(ok=True, payout_id=None, status=None)
    assert payload.ok is True
    assert payload.payout_id is None
    assert payload.status is None


def test_webhook_response_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        WebhookResponse(
            status="success",
            event_type="payment_intent.succeeded",
            message="ok",
            extra="nope",
        )


def test_webhook_response_accepts_message() -> None:
    payload = WebhookResponse(
        status="success",
        event_type="payout.created",
        message=f"ok-{datetime.now(timezone.utc).isoformat()}",
    )
    assert payload.status == "success"
