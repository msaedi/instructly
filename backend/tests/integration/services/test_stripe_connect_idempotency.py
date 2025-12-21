"""
Regression tests for Stripe Connect onboarding idempotency.
Ensures duplicate clicks do not create duplicate Stripe account records.
"""

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.repositories.payment_repository import PaymentRepository
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


@patch("stripe.Account.modify")
@patch("stripe.Account.create")
def test_create_connected_account_concurrent_requests_do_not_duplicate(
    mock_account_create: MagicMock,
    mock_account_modify: MagicMock,
    db: Session,
    test_instructor,
    monkeypatch,
) -> None:
    """Concurrent create calls should yield a single connected account record."""
    profile = _get_profile(db, test_instructor.id)

    counter_lock = threading.Lock()
    call_state = {"count": 0}
    barrier = threading.Barrier(5)
    original_get = PaymentRepository.get_connected_account_by_instructor_id

    def _get_with_pause(self, instructor_profile_id: str):
        with counter_lock:
            call_state["count"] += 1
            should_pause = call_state["count"] <= 5
        if should_pause:
            time.sleep(0.05)
        return original_get(self, instructor_profile_id)

    monkeypatch.setattr(
        PaymentRepository,
        "get_connected_account_by_instructor_id",
        _get_with_pause,
    )

    def _create_account_id(index: int) -> MagicMock:
        return MagicMock(id=f"acct_concurrent_{index}")

    mock_account_create.side_effect = [_create_account_id(i) for i in range(5)]
    mock_account_modify.return_value = MagicMock()

    SessionMaker = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    def _worker() -> StripeConnectedAccount:
        session = SessionMaker()
        try:
            service = StripeService(
                session,
                config_service=ConfigService(session),
                pricing_service=PricingService(session),
            )
            try:
                barrier.wait(timeout=10)
            except threading.BrokenBarrierError:
                pass
            return service.create_connected_account(profile.id, test_instructor.email)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = [executor.submit(_worker).result() for _ in range(5)]

    assert all(isinstance(result, StripeConnectedAccount) for result in results)

    db.expire_all()
    records = (
        db.query(StripeConnectedAccount)
        .filter(StripeConnectedAccount.instructor_profile_id == profile.id)
        .all()
    )
    assert len(records) == 1
