"""
Regression tests for Stripe Connect onboarding idempotency.
Ensures duplicate clicks do not create duplicate Stripe account records.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService


def _get_profile(db: Session, user_id: str) -> InstructorProfile:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()
    assert profile is not None
    return profile


@patch("app.services.stripe_service.StripeService.check_account_status")
@patch("stripe.AccountLink.create")
@patch("stripe.Account.create")
def test_connect_onboard_twice_does_not_fail(
    mock_account_create: MagicMock,
    mock_account_link: MagicMock,
    mock_check_status: MagicMock,
    db: Session,
    test_instructor,
) -> None:
    """
    Clicking connect twice should reuse the existing record and avoid duplicates.
    """
    mock_account_create.return_value = MagicMock(id="acct_test123")
    mock_account_link.return_value = MagicMock(url="https://connect.stripe.com/setup/test")
    mock_check_status.return_value = {"onboarding_completed": False}

    profile = _get_profile(db, test_instructor.id)
    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    response_one = service.start_instructor_onboarding(
        user=test_instructor,
        request_host="app.test",
        request_scheme="https",
        return_to="/instructor/onboarding/payment-setup",
    )
    response_two = service.start_instructor_onboarding(
        user=test_instructor,
        request_host="app.test",
        request_scheme="https",
        return_to="/instructor/onboarding/payment-setup",
    )

    assert response_one.onboarding_url
    assert response_two.onboarding_url
    mock_account_create.assert_called_once()

    records = (
        db.query(StripeConnectedAccount)
        .filter(StripeConnectedAccount.instructor_profile_id == profile.id)
        .all()
    )
    assert len(records) == 1


@patch("stripe.AccountLink.create")
@patch("stripe.Account.create")
def test_stripe_account_id_is_stripe_format(
    mock_account_create: MagicMock,
    mock_account_link: MagicMock,
    db: Session,
    test_instructor,
) -> None:
    """Ensure stripe_account_id comes from Stripe (acct_ prefix)."""
    mock_account_create.return_value = MagicMock(id="acct_test456")
    mock_account_link.return_value = MagicMock(url="https://connect.stripe.com/setup/test")

    profile = _get_profile(db, test_instructor.id)
    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    service.start_instructor_onboarding(
        user=test_instructor,
        request_host="app.test",
        request_scheme="https",
        return_to="/instructor/onboarding/payment-setup",
    )

    record = (
        db.query(StripeConnectedAccount)
        .filter(StripeConnectedAccount.instructor_profile_id == profile.id)
        .first()
    )
    assert record is not None
    assert record.stripe_account_id.startswith("acct_")


@patch("app.services.stripe_service.StripeService.create_account_link")
@patch("stripe.Account.create")
def test_payment_setup_return_url(
    mock_account_create: MagicMock,
    mock_create_link: MagicMock,
    db: Session,
    test_instructor,
) -> None:
    """Return URL for payment-setup should not include /status."""
    mock_account_create.return_value = MagicMock(id="acct_test789")
    mock_create_link.return_value = "https://connect.stripe.com/setup/test"

    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    service.start_instructor_onboarding(
        user=test_instructor,
        request_host="app.test",
        request_scheme="https",
        return_to="/instructor/onboarding/payment-setup",
    )

    _, kwargs = mock_create_link.call_args
    assert kwargs["return_url"].endswith("/instructor/onboarding/payment-setup")


@pytest.mark.parametrize(
    ("origin", "expected_prefix"),
    [
        ("http://beta-local.instainstru.com:3000", "http://beta-local.instainstru.com:3000"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://127.0.0.1:3000", "http://127.0.0.1:3000"),
    ],
)
@patch("app.services.stripe_service.StripeService.create_account_link")
@patch("stripe.Account.create")
def test_return_url_uses_allowed_origin(
    mock_account_create: MagicMock,
    mock_create_link: MagicMock,
    db: Session,
    test_instructor,
    origin: str,
    expected_prefix: str,
) -> None:
    """Allowed origin should be used for Stripe return URLs."""
    mock_account_create.return_value = MagicMock(id="acct_origin_allowed")
    mock_create_link.return_value = "https://connect.stripe.com/setup/test"

    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    service.start_instructor_onboarding(
        user=test_instructor,
        request_host="api.beta.instainstru.com",
        request_scheme="https",
        request_origin=origin,
        return_to="/instructor/onboarding/payment-setup",
    )

    _, kwargs = mock_create_link.call_args
    return_url = kwargs["return_url"]
    assert return_url.startswith(expected_prefix)


@patch("app.services.stripe_service.StripeService.create_account_link")
@patch("stripe.Account.create")
def test_return_url_falls_back_to_settings_when_no_origin(
    mock_account_create: MagicMock,
    mock_create_link: MagicMock,
    db: Session,
    test_instructor,
    monkeypatch,
) -> None:
    """When no origin/referer provided, use settings.frontend_url."""
    mock_account_create.return_value = MagicMock(id="acct_origin_fallback")
    mock_create_link.return_value = "https://connect.stripe.com/setup/test"

    monkeypatch.setattr(settings, "frontend_url", "https://frontend.example.test", raising=False)

    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    service.start_instructor_onboarding(
        user=test_instructor,
        request_host="api.frontend.example.test",
        request_scheme="https",
        request_origin=None,
        request_referer=None,
        return_to="/instructor/onboarding/payment-setup",
    )

    _, kwargs = mock_create_link.call_args
    return_url = kwargs["return_url"]
    assert return_url.startswith("https://frontend.example.test")


@patch("app.services.stripe_service.StripeService.create_account_link")
@patch("stripe.Account.create")
def test_return_url_rejects_disallowed_origin(
    mock_account_create: MagicMock,
    mock_create_link: MagicMock,
    db: Session,
    test_instructor,
    monkeypatch,
) -> None:
    """Disallowed origins should not be used in return URLs."""
    mock_account_create.return_value = MagicMock(id="acct_origin_disallowed")
    mock_create_link.return_value = "https://connect.stripe.com/setup/test"

    monkeypatch.setattr(settings, "frontend_url", "https://frontend.example.test", raising=False)

    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    service.start_instructor_onboarding(
        user=test_instructor,
        request_host="api.frontend.example.test",
        request_scheme="https",
        request_origin="https://evil-site.com",
        request_referer="https://evil-site.com/phishing",
        return_to="/instructor/onboarding/payment-setup",
    )

    _, kwargs = mock_create_link.call_args
    return_url = kwargs["return_url"]
    assert "evil-site.com" not in return_url
    assert return_url.startswith("https://frontend.example.test")
