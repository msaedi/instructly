"""
Route-level tests for Stripe Connect onboarding endpoints.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount


def _get_profile(db: Session, user_id: str) -> InstructorProfile:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()
    assert profile is not None
    return profile


class TestStripeConnectOnboardRoute:
    """End-to-end tests for /api/v1/payments/connect/onboard."""

    @patch("app.services.stripe_service.stripe.Account.retrieve")
    @patch("app.services.stripe_service.stripe.AccountLink.create")
    @patch("app.services.stripe_service.stripe.Account.create")
    def test_onboard_endpoint_is_idempotent(
        self,
        mock_account_create: MagicMock,
        mock_account_link: MagicMock,
        mock_account_retrieve: MagicMock,
        client: TestClient,
        auth_headers_instructor: dict,
        test_instructor,
        db: Session,
    ) -> None:
        """
        POST /api/v1/payments/connect/onboard twice should not fail
        or create duplicate stripe_connected_accounts rows.
        """
        mock_account_create.return_value = MagicMock(
            id="acct_test_idempotent",
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False,
        )
        mock_account_link.return_value = MagicMock(
            url="https://connect.stripe.com/setup/test123"
        )
        mock_account_retrieve.return_value = MagicMock(
            id="acct_test_idempotent",
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False,
            requirements=MagicMock(currently_due=[], past_due=[], pending_verification=[]),
        )

        endpoint = "/api/v1/payments/connect/onboard"
        params = {"return_to": "/instructor/onboarding/payment-setup"}

        response_one = client.post(endpoint, params=params, headers=auth_headers_instructor)
        assert response_one.status_code == 200, response_one.text

        response_two = client.post(endpoint, params=params, headers=auth_headers_instructor)
        assert response_two.status_code == 200, response_two.text

        profile = _get_profile(db, test_instructor.id)
        records = (
            db.query(StripeConnectedAccount)
            .filter(StripeConnectedAccount.instructor_profile_id == profile.id)
            .all()
        )
        assert len(records) == 1

    @patch("app.services.stripe_service.stripe.AccountLink.create")
    @patch("app.services.stripe_service.stripe.Account.create")
    def test_onboard_endpoint_returns_correct_redirect(
        self,
        mock_account_create: MagicMock,
        mock_account_link: MagicMock,
        client: TestClient,
        auth_headers_instructor: dict,
        test_instructor,
    ) -> None:
        """Return URL should not include /status/payment-setup."""
        mock_account_create.return_value = MagicMock(
            id="acct_test_redirect",
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False,
        )
        mock_account_link.return_value = MagicMock(
            url="https://connect.stripe.com/setup/redirect_test"
        )

        response = client.post(
            "/api/v1/payments/connect/onboard",
            params={"return_to": "/instructor/onboarding/payment-setup"},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200, response.text
        _, kwargs = mock_account_link.call_args
        assert "/status/payment-setup" not in kwargs.get("return_url", "")

    @patch("app.services.stripe_service.stripe.Account.retrieve")
    @patch("app.services.stripe_service.stripe.AccountLink.create")
    @patch("app.services.stripe_service.stripe.Account.create")
    def test_onboard_already_completed_returns_success(
        self,
        mock_account_create: MagicMock,
        mock_account_link: MagicMock,
        mock_account_retrieve: MagicMock,
        client: TestClient,
        auth_headers_instructor: dict,
        test_instructor,
        db: Session,
    ) -> None:
        """
        If onboarding is already completed, the endpoint should succeed
        without creating a new Stripe account.
        """
        profile = _get_profile(db, test_instructor.id)
        db.add(
            StripeConnectedAccount(
                instructor_profile_id=profile.id,
                stripe_account_id="acct_already_complete",
                onboarding_completed=True,
            )
        )
        db.commit()

        mock_account_retrieve.return_value = MagicMock(
            id="acct_already_complete",
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
            requirements=MagicMock(currently_due=[], past_due=[], pending_verification=[]),
        )

        response = client.post(
            "/api/v1/payments/connect/onboard",
            params={"return_to": "/instructor/onboarding/payment-setup"},
            headers=auth_headers_instructor,
        )

        assert response.status_code == 200, response.text
        mock_account_create.assert_not_called()
        mock_account_link.assert_not_called()
