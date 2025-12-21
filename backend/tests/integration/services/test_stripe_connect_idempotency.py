"""
Regression tests for Stripe Connect onboarding idempotency.
Ensures duplicate clicks do not create duplicate Stripe account records.
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

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
