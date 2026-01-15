"""
Tests for StripeService.

Comprehensive test suite for Stripe marketplace payment processing,
including customer management, connected accounts, and payment processing.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
import logging
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import stripe
import ulid

from app.core.config import settings
from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.schemas.payment_schemas import CreateCheckoutRequest
from app.services.cache_service import CacheService, CacheServiceSyncAdapter
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import ChargeContext, StripeService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture(autouse=True)
def _no_floors_for_service_tests(disable_price_floors):
    """Disable price floors for StripeService unit tests."""
    yield


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _default_instructor_pct(stripe_service: StripeService) -> Decimal:
    config, _ = stripe_service.config_service.get_pricing_config()
    pct = config.get("instructor_tiers", [{}])[0].get("pct", 0)
    return Decimal(str(pct)).quantize(Decimal("0.0001"))


def _student_fee_pct(stripe_service: StripeService) -> Decimal:
    config, _ = stripe_service.config_service.get_pricing_config()
    pct = config.get("student_fee_pct", 0)
    return Decimal(str(pct)).quantize(Decimal("0.0001"))


def _booking_service_stub() -> MagicMock:
    booking_service = MagicMock()
    booking_service.repository = MagicMock()
    booking_service.system_message_service = MagicMock()
    booking_service.invalidate_booking_cache = MagicMock()
    return booking_service


class TestStripeService:
    """Test suite for StripeService."""

    @pytest.fixture
    def stripe_service(self, db: Session) -> StripeService:
        """Create StripeService instance."""
        config_service = ConfigService(db)
        pricing_service = PricingService(db)
        return StripeService(
            db,
            config_service=config_service,
            pricing_service=pricing_service,
        )

    @pytest.fixture
    def test_user(self, db: Session) -> User:
        """Create a test user."""
        user = User(
            id=str(ulid.ULID()),
            email=f"test_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="User",
            zip_code="10001",
        )
        db.add(user)
        db.flush()
        return user

    @pytest.fixture
    def test_instructor(self, db: Session) -> tuple[User, InstructorProfile, InstructorService]:
        """Create a test instructor with profile and service."""
        # Create user
        user = User(
            id=str(ulid.ULID()),
            email=f"instructor_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="Instructor",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Create profile
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=user.id,
            bio="Test instructor",
            years_experience=5,
        )
        db.add(profile)
        db.flush()

        # Create service category and catalog item if they don't exist
        category_ulid = str(ulid.ULID())
        category = db.query(ServiceCategory).filter_by(slug=f"test-category-{category_ulid.lower()}").first()
        if not category:
            category = ServiceCategory(
                id=category_ulid,
                name="Test Category",
                slug=f"test-category-{category_ulid.lower()}",
                description="Test category for unit tests",
            )
            db.add(category)
            db.flush()

        service_ulid = str(ulid.ULID())
        catalog = db.query(ServiceCatalog).filter_by(slug=f"test-service-{service_ulid.lower()}").first()
        if not catalog:
            catalog = ServiceCatalog(
                id=service_ulid,
                category_id=category.id,
                name="Test Service",
                slug=f"test-service-{service_ulid.lower()}",
                description="Test service for unit tests",
            )
            db.add(catalog)
            db.flush()

        # Create instructor service
        service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=50.00,
            is_active=True,
        )
        db.add(service)
        db.flush()

        return user, profile, service

    @pytest.fixture
    def test_booking(self, db: Session, test_user: User, test_instructor: tuple) -> Booking:
        """Create a test booking."""
        instructor_user, _, instructor_service = test_instructor
        booking_date = datetime.now().date()
        start_time = time(14, 0)
        end_time = time(15, 0)
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=booking_date,
            start_time=start_time,  # 2:00 PM
            end_time=end_time,  # 3:00 PM
            **booking_timezone_fields(booking_date, start_time, end_time),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()
        return booking

    # ========== Initialization Tests ==========

    def test_init_wraps_cache_service(self, db: Session) -> None:
        cache = CacheService(db)
        service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
            cache_service=cache,
        )

        assert isinstance(service.cache_service, CacheServiceSyncAdapter)

    def test_init_accepts_cache_adapter(self, db: Session) -> None:
        cache = CacheService(db)
        adapter = CacheServiceSyncAdapter(cache)
        service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
            cache_service=adapter,
        )

        assert service.cache_service is adapter

    def test_init_handles_missing_stripe_key(self, db: Session, monkeypatch) -> None:
        monkeypatch.setattr(settings, "stripe_secret_key", None, raising=False)

        service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
        )

        assert service.stripe_configured is False

    def test_init_handles_http_client_error(self, db: Session, monkeypatch) -> None:
        """Test that HTTP client errors during init are handled gracefully.

        Note: Stripe 14.x moved http_client to _http_client (private API).
        Production code and this test both use _http_client for consistency.
        """
        secret = MagicMock()
        secret.get_secret_value = MagicMock(return_value="sk_test")
        monkeypatch.setattr(settings, "stripe_secret_key", secret, raising=False)
        http_client_module = getattr(stripe, "_http_client", None) or getattr(
            stripe, "http_client", None
        )
        assert http_client_module is not None
        monkeypatch.setattr(
            http_client_module,
            "RequestsClient",
            MagicMock(side_effect=Exception("boom")),
        )

        service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
        )

        assert service.stripe_configured is True

    def test_init_handles_stripe_config_exception(self, db: Session, monkeypatch) -> None:
        class BadSecret:
            def get_secret_value(self) -> str:
                raise Exception("bad secret")

        monkeypatch.setattr(settings, "stripe_secret_key", BadSecret(), raising=False)

        service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
        )

        assert service.stripe_configured is False

    # ========== Customer Management Tests ==========

    @patch("stripe.Customer.create")
    def test_create_customer_success(self, mock_stripe_create, stripe_service: StripeService, test_user: User):
        """Test successful customer creation."""
        # Mock Stripe response
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_stripe_create.return_value = mock_customer

        # Create customer
        customer = stripe_service.create_customer(
            user_id=test_user.id, email=test_user.email, name=f"{test_user.first_name} {test_user.last_name}"
        )

        # Verify Stripe API call
        mock_stripe_create.assert_called_once_with(
            email=test_user.email,
            name=f"{test_user.first_name} {test_user.last_name}",
            metadata={"user_id": test_user.id},
        )

        # Verify database record
        assert customer is not None
        assert customer.user_id == test_user.id
        assert customer.stripe_customer_id == "cus_test123"

    @patch("stripe.Customer.create")
    def test_create_customer_already_exists(self, mock_stripe_create, stripe_service: StripeService, test_user: User):
        """Test creating customer when one already exists."""
        # Create existing customer
        existing_customer = stripe_service.payment_repository.create_customer_record(test_user.id, "cus_existing")

        # Try to create again
        customer = stripe_service.create_customer(
            user_id=test_user.id, email=test_user.email, name=f"{test_user.first_name} {test_user.last_name}"
        )

        # Should not call Stripe API
        mock_stripe_create.assert_not_called()

        # Should return existing customer
        assert customer.id == existing_customer.id
        assert customer.stripe_customer_id == "cus_existing"

    @patch("stripe.Customer.create")
    def test_create_customer_stripe_error(self, mock_stripe_create, stripe_service: StripeService, test_user: User):
        """Test handling Stripe error during customer creation."""
        # Mock Stripe error
        mock_stripe_create.side_effect = stripe.StripeError("API Error")

        # Should raise ServiceException
        with pytest.raises(ServiceException, match="Failed to create Stripe customer"):
            stripe_service.create_customer(
                user_id=test_user.id, email=test_user.email, name=f"{test_user.first_name} {test_user.last_name}"
            )

    @patch("stripe.Customer.create")
    def test_create_customer_auth_error_returns_mock(
        self, mock_stripe_create, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.stripe_configured = False
        mock_stripe_create.side_effect = stripe.error.AuthenticationError("No API key provided")

        customer = stripe_service.create_customer(
            user_id=test_user.id,
            email=test_user.email,
            name=f"{test_user.first_name} {test_user.last_name}",
        )

        assert customer.stripe_customer_id == f"mock_cust_{test_user.id}"

    @patch("stripe.Customer.create")
    def test_create_customer_unconfigured_non_auth_error(
        self, mock_stripe_create, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.stripe_configured = False
        mock_stripe_create.side_effect = Exception("stripe down")

        with pytest.raises(ServiceException, match="Failed to create Stripe customer"):
            stripe_service.create_customer(
                user_id=test_user.id,
                email=test_user.email,
                name=f"{test_user.first_name} {test_user.last_name}",
            )

    @patch("stripe.Customer.create")
    def test_get_or_create_customer_existing(self, mock_stripe_create, stripe_service: StripeService, test_user: User):
        """Test get_or_create_customer with existing customer."""
        # Create existing customer
        existing_customer = stripe_service.payment_repository.create_customer_record(test_user.id, "cus_existing")

        # Get or create
        customer = stripe_service.get_or_create_customer(test_user.id)

        # Should not call Stripe API
        mock_stripe_create.assert_not_called()

        # Should return existing customer
        assert customer.id == existing_customer.id

    @patch("stripe.Customer.create")
    def test_get_or_create_customer_new(self, mock_stripe_create, stripe_service: StripeService, test_user: User):
        """Test get_or_create_customer creating new customer."""
        # Mock Stripe response
        mock_customer = MagicMock()
        mock_customer.id = "cus_new123"
        mock_stripe_create.return_value = mock_customer

        # Get or create
        customer = stripe_service.get_or_create_customer(test_user.id)

        # Should call Stripe API
        mock_stripe_create.assert_called_once()

        # Should return new customer
        assert customer.stripe_customer_id == "cus_new123"

    def test_get_or_create_customer_user_not_found(self, stripe_service: StripeService):
        """Test get_or_create_customer with non-existent user."""
        with pytest.raises(ServiceException, match="User .* not found"):
            stripe_service.get_or_create_customer("nonexistent_user_id")

    def test_get_or_create_customer_unexpected_error(
        self, stripe_service: StripeService
    ) -> None:
        with patch.object(stripe_service.user_repository, "get_by_id", side_effect=Exception("db down")):
            with pytest.raises(ServiceException, match="Failed to get or create customer"):
                stripe_service.get_or_create_customer("user_boom")

    # ========== Connected Account Management Tests ==========

    @patch("stripe.Account.create")
    def test_create_connected_account_success(
        self, mock_stripe_create, stripe_service: StripeService, test_instructor: tuple
    ):
        """Test successful connected account creation."""
        instructor_user, profile, _ = test_instructor

        # Mock Stripe response
        mock_account = MagicMock()
        mock_account.id = "acct_test123"
        mock_stripe_create.return_value = mock_account

        # Create connected account
        account = stripe_service.create_connected_account(instructor_profile_id=profile.id, email=instructor_user.email)

        # Verify Stripe API call
        mock_stripe_create.assert_called_once_with(
            type="express",
            email=instructor_user.email,
            capabilities={"transfers": {"requested": True}},
            metadata={"instructor_profile_id": profile.id},
        )

        # Verify database record
        assert account is not None
        assert account.instructor_profile_id == profile.id
        assert account.stripe_account_id == "acct_test123"
        assert account.onboarding_completed is False

    @patch("stripe.Account.create")
    def test_create_connected_account_fallback_when_unconfigured(
        self, mock_stripe_create, stripe_service: StripeService, test_instructor: tuple
    ):
        """Fallback to mock account when Stripe isn't configured."""
        instructor_user, profile, _ = test_instructor
        stripe_service.stripe_configured = False
        mock_stripe_create.side_effect = Exception("stripe unavailable")

        account = stripe_service.create_connected_account(profile.id, instructor_user.email)

        assert account.stripe_account_id == f"mock_acct_{profile.id}"

    @patch("stripe.Account.create")
    def test_create_connected_account_unexpected_error(
        self, mock_stripe_create, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        instructor_user, profile, _ = test_instructor
        stripe_service.stripe_configured = True
        mock_stripe_create.side_effect = Exception("boom")

        with pytest.raises(ServiceException, match="Failed to create connected account"):
            stripe_service.create_connected_account(profile.id, instructor_user.email)

    @patch("stripe.Account.create")
    def test_create_connected_account_stripe_error(
        self, mock_stripe_create, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        instructor_user, profile, _ = test_instructor
        stripe_service.stripe_configured = True
        mock_stripe_create.side_effect = stripe.StripeError("stripe failure")

        with pytest.raises(ServiceException, match="Failed to create connected account"):
            stripe_service.create_connected_account(
                instructor_profile_id=profile.id,
                email=instructor_user.email,
            )

    @patch("stripe.AccountLink.create")
    def test_create_account_link_success(self, mock_link_create, stripe_service: StripeService, test_instructor: tuple):
        """Test successful account link creation."""
        _, profile, _ = test_instructor

        # Create connected account
        _account = stripe_service.payment_repository.create_connected_account_record(profile.id, "acct_test123")

        # Mock Stripe response
        mock_link = MagicMock()
        mock_link.url = "https://connect.stripe.com/setup/test"
        mock_link_create.return_value = mock_link

        # Create account link
        link_url = stripe_service.create_account_link(
            instructor_profile_id=profile.id, refresh_url="https://app.com/refresh", return_url="https://app.com/return"
        )

        # Verify Stripe API call
        mock_link_create.assert_called_once_with(
            account="acct_test123",
            refresh_url="https://app.com/refresh",
            return_url="https://app.com/return",
            type="account_onboarding",
        )

        # Verify result
        assert link_url == "https://connect.stripe.com/setup/test"

    @patch("stripe.AccountLink.create")
    def test_create_account_link_stripe_error(
        self, mock_link_create, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(profile.id, "acct_test123")
        mock_link_create.side_effect = stripe.StripeError("link error")

        with pytest.raises(ServiceException, match="Failed to create account link"):
            stripe_service.create_account_link(
                instructor_profile_id=profile.id,
                refresh_url="https://app.com/refresh",
                return_url="https://app.com/return",
            )

    def test_create_account_link_no_account(self, stripe_service: StripeService, test_instructor: tuple):
        """Test account link creation with no connected account."""
        _, profile, _ = test_instructor

        with pytest.raises(ServiceException, match="No connected account found"):
            stripe_service.create_account_link(
                instructor_profile_id=profile.id,
                refresh_url="https://app.com/refresh",
                return_url="https://app.com/return",
            )

    @patch("stripe.Account.retrieve")
    def test_check_account_status_completed(self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple):
        """Test checking account status for completed onboarding."""
        _, profile, _ = test_instructor

        # Create connected account
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_test123", onboarding_completed=False
        )

        # Mock Stripe response
        mock_account = MagicMock()
        mock_account.charges_enabled = True
        mock_account.details_submitted = True
        mock_account.payouts_enabled = True
        mock_retrieve.return_value = mock_account

        # Check status
        status = stripe_service.check_account_status(profile.id)

        # Verify result
        assert status["has_account"] is True
        assert status["onboarding_completed"] is True
        assert status["charges_enabled"] is True
        assert status["can_accept_payments"] is True
        assert status["payouts_enabled"] is True
        assert status["details_submitted"] is True
        assert status["requirements"] == []

    @patch("stripe.Account.retrieve")
    def test_check_account_status_updates_onboarding_status(
        self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple
    ):
        """Update onboarding status when Stripe reports completion."""
        _, profile, _ = test_instructor

        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_test123", onboarding_completed=False
        )

        mock_account = MagicMock()
        mock_account.charges_enabled = True
        mock_account.details_submitted = True
        mock_account.payouts_enabled = False
        mock_account.requirements = MagicMock(
            currently_due=["legal_entity.verification.document"],
            past_due=[],
            pending_verification=[],
        )
        mock_retrieve.return_value = mock_account

        with patch.object(
            stripe_service.payment_repository, "update_onboarding_status"
        ) as mock_update:
            status = stripe_service.check_account_status(profile.id)

        mock_update.assert_called_once_with("acct_test123", True)
        assert "legal_entity.verification.document" in status["requirements"]

    def test_check_account_status_no_account(self, stripe_service: StripeService, test_instructor: tuple):
        """Test checking account status with no account."""
        _, profile, _ = test_instructor

        status = stripe_service.check_account_status(profile.id)

        assert status["has_account"] is False
        assert status["onboarding_completed"] is False
        assert status["charges_enabled"] is False
        assert status["can_accept_payments"] is False
        assert status["payouts_enabled"] is False
        assert status["details_submitted"] is False
        assert status["requirements"] == []

    @patch("stripe.Account.retrieve")
    def test_check_account_status_handles_requirement_parse_error(
        self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_req_error", onboarding_completed=True
        )

        class BadRequirements:
            @property
            def requirements(self) -> dict:
                raise Exception("bad requirements")

        mock_account = BadRequirements()
        mock_account.charges_enabled = True
        mock_account.details_submitted = True
        mock_account.payouts_enabled = True
        mock_retrieve.return_value = mock_account

        status = stripe_service.check_account_status(profile.id)

        assert status["requirements"] == []

    @patch("stripe.Account.retrieve")
    def test_check_account_status_update_failure(
        self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_update_fail", onboarding_completed=False
        )

        mock_account = MagicMock()
        mock_account.charges_enabled = True
        mock_account.details_submitted = True
        mock_account.payouts_enabled = True
        mock_retrieve.return_value = mock_account

        stripe_service.payment_repository.update_onboarding_status = MagicMock(
            side_effect=Exception("db down")
        )

        status = stripe_service.check_account_status(profile.id)

        assert status["onboarding_completed"] is True

    @patch("stripe.Account.retrieve")
    def test_check_account_status_stripe_error(
        self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_err", onboarding_completed=False
        )
        mock_retrieve.side_effect = stripe.StripeError("boom")

        with pytest.raises(ServiceException, match="Failed to check account status"):
            stripe_service.check_account_status(profile.id)

    @patch("stripe.Account.retrieve")
    def test_check_account_status_unexpected_error(
        self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_err", onboarding_completed=False
        )
        mock_retrieve.side_effect = Exception("boom")

        with pytest.raises(ServiceException, match="Failed to check account status"):
            stripe_service.check_account_status(profile.id)

    @patch("stripe.Account.retrieve")
    def test_get_instructor_onboarding_status_maps_charges_enabled(
        self, mock_retrieve, stripe_service: StripeService, test_instructor: tuple
    ):
        """Ensure /connect/status returns charges_enabled derived from Stripe account."""
        user, profile, _ = test_instructor

        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_test123", onboarding_completed=False
        )

        mock_account = MagicMock()
        mock_account.charges_enabled = True
        mock_account.payouts_enabled = True
        mock_account.details_submitted = True
        # Provide requirements shape to ensure parsing is safe
        mock_account.requirements = MagicMock(currently_due=[], past_due=[], pending_verification=[])
        mock_retrieve.return_value = mock_account

        status = stripe_service.get_instructor_onboarding_status(user=user)

        assert status.has_account is True
        assert status.charges_enabled is True
        assert status.payouts_enabled is True
        assert status.details_submitted is True
        assert status.onboarding_completed is True
        assert status.requirements == []

    def test_get_instructor_onboarding_status_profile_missing(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        with pytest.raises(ServiceException, match="Instructor profile not found"):
            stripe_service.get_instructor_onboarding_status(user=test_user)

    def test_get_instructor_onboarding_status_no_account(
        self, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        user, _, _ = test_instructor
        status = stripe_service.get_instructor_onboarding_status(user=user)

        assert status.has_account is False
        assert status.onboarding_completed is False

    @patch("app.services.stripe_service.StripeService.check_account_status")
    @patch("app.services.stripe_service.StripeService.create_account_link")
    def test_start_instructor_onboarding_reuses_existing_account(
        self,
        mock_create_link,
        mock_check_status,
        stripe_service: StripeService,
        test_instructor: tuple,
        monkeypatch,
    ):
        """Existing Stripe accounts should be reused for onboarding."""
        user, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_test123", onboarding_completed=False
        )
        mock_create_link.return_value = "https://stripe.test/onboard"
        mock_check_status.return_value = {"onboarding_completed": False}
        monkeypatch.setattr(settings, "frontend_url", "https://app.test", raising=False)

        response = stripe_service.start_instructor_onboarding(
            user=user,
            request_host="api.app.test",
            request_scheme="https",
            return_to="/instructor/onboarding/complete",
        )

        assert response.account_id == "acct_test123"
        assert response.onboarding_url == "https://stripe.test/onboard"
        assert response.already_onboarded is False

        _, kwargs = mock_create_link.call_args
        assert kwargs["instructor_profile_id"] == profile.id
        assert kwargs["return_url"].endswith("/instructor/onboarding/status/complete")

    @patch("app.services.stripe_service.StripeService.create_account_link")
    @patch("app.services.stripe_service.StripeService.create_connected_account")
    def test_start_instructor_onboarding_creates_account(
        self,
        mock_create_account,
        mock_create_link,
        stripe_service: StripeService,
        test_instructor: tuple,
        monkeypatch,
    ):
        """Missing accounts should trigger creation before onboarding."""
        user, profile, _ = test_instructor
        mock_create_account.return_value = MagicMock(id="acct_new", stripe_account_id="acct_new")
        mock_create_link.return_value = "https://stripe.test/onboard"
        monkeypatch.setattr(settings, "frontend_url", "https://app.test", raising=False)

        response = stripe_service.start_instructor_onboarding(
            user=user,
            request_host="api.app.test",
            request_scheme="https",
            return_to=None,
        )

        assert response.account_id == "acct_new"
        assert response.onboarding_url == "https://stripe.test/onboard"
        mock_create_account.assert_called_once()

    def test_start_instructor_onboarding_missing_profile(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        with pytest.raises(ServiceException, match="Instructor profile not found"):
            stripe_service.start_instructor_onboarding(
                user=test_user,
                request_host="app.test",
                request_scheme="https",
            )

    @patch("app.services.stripe_service.StripeService.check_account_status")
    @patch("app.services.stripe_service.StripeService.create_account_link")
    def test_start_instructor_onboarding_parses_callback_from_instructor_path(
        self,
        mock_create_link,
        mock_check_status,
        stripe_service: StripeService,
        test_instructor: tuple,
        monkeypatch,
    ) -> None:
        user, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_callback", onboarding_completed=False
        )
        mock_create_link.return_value = "https://stripe.test/onboard"
        mock_check_status.return_value = {"onboarding_completed": False}
        monkeypatch.setattr(settings, "frontend_url", "not-a-url", raising=False)
        monkeypatch.setattr(settings, "local_beta_frontend_origin", "", raising=False)

        response = stripe_service.start_instructor_onboarding(
            user=user,
            request_host="api.example.com",
            request_scheme="https",
            return_to="/instructor/earnings",
        )

        assert response.account_id == "acct_callback"
        _, kwargs = mock_create_link.call_args
        assert kwargs["return_url"].endswith("/instructor/onboarding/status/earnings")

    @patch("app.services.stripe_service.StripeService.check_account_status")
    @patch("app.services.stripe_service.StripeService.create_account_link")
    def test_start_instructor_onboarding_parses_callback_from_last_segment(
        self,
        mock_create_link,
        mock_check_status,
        stripe_service: StripeService,
        test_instructor: tuple,
        monkeypatch,
    ) -> None:
        user, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_callback2", onboarding_completed=False
        )
        mock_create_link.return_value = "https://stripe.test/onboard"
        mock_check_status.return_value = {"onboarding_completed": False}
        monkeypatch.setattr(settings, "frontend_url", "https://app.test", raising=False)

        response = stripe_service.start_instructor_onboarding(
            user=user,
            request_host="app.test",
            request_scheme="https",
            return_to="/foo/bar",
        )

        assert response.account_id == "acct_callback2"
        _, kwargs = mock_create_link.call_args
        assert kwargs["return_url"].endswith("/instructor/onboarding/status/bar")

    @patch("app.services.stripe_service.StripeService.check_account_status")
    @patch("app.services.stripe_service.StripeService.create_account_link")
    def test_start_instructor_onboarding_sanitizes_callback_and_frontend_path(
        self,
        mock_create_link,
        mock_check_status,
        stripe_service: StripeService,
        test_instructor: tuple,
        monkeypatch,
    ) -> None:
        user, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_sanitize", onboarding_completed=False
        )
        mock_create_link.return_value = "https://stripe.test/onboard"
        mock_check_status.return_value = {"onboarding_completed": False}
        monkeypatch.setattr(settings, "frontend_url", "https:///app", raising=False)
        monkeypatch.setattr(settings, "local_beta_frontend_origin", "", raising=False)

        stripe_service.start_instructor_onboarding(
            user=user,
            request_host="api.example.com",
            request_scheme="https",
            return_to="/instructor/onboarding/We!rd",
        )

        _, kwargs = mock_create_link.call_args
        assert kwargs["return_url"].startswith("https:///")
        assert kwargs["return_url"].endswith("/instructor/onboarding/status/werd")

    @patch("stripe.Account.create_login_link")
    def test_get_instructor_dashboard_link_success(
        self, mock_link, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        """Dashboard link should be fetched from Stripe."""
        user, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_dash", onboarding_completed=True
        )
        mock_link.return_value = {"url": "https://stripe.test/dash"}

        response = stripe_service.get_instructor_dashboard_link(user=user)

        assert response.dashboard_url == "https://stripe.test/dash"

    def test_get_instructor_dashboard_link_missing_profile(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        with pytest.raises(ServiceException, match="Instructor profile not found"):
            stripe_service.get_instructor_dashboard_link(user=test_user)

    def test_get_instructor_dashboard_link_not_onboarded(
        self, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        user, _, _ = test_instructor

        with pytest.raises(ServiceException, match="not onboarded"):
            stripe_service.get_instructor_dashboard_link(user=user)

    @patch("stripe.Account.modify")
    def test_set_payout_schedule_for_account_success(
        self, mock_modify, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        """Direct payout schedule updates should return account details."""
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_schedule", onboarding_completed=True
        )
        mock_modify.return_value = MagicMock(settings={"payouts": {"schedule": {"interval": "weekly"}}})

        result = stripe_service.set_payout_schedule_for_account(
            instructor_profile_id=profile.id,
            interval="weekly",
            weekly_anchor="tuesday",
        )

        assert result["account_id"] == "acct_schedule"

    @patch("stripe.Account.modify")
    def test_set_payout_schedule_for_account_handles_settings_error(
        self, mock_modify, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_schedule", onboarding_completed=True
        )

        class BadSettings:
            @property
            def settings(self) -> dict:
                raise Exception("settings broken")

        mock_modify.return_value = BadSettings()

        result = stripe_service.set_payout_schedule_for_account(
            instructor_profile_id=profile.id,
            interval="weekly",
            weekly_anchor="tuesday",
        )

        assert result["settings"] == {}

    @patch("stripe.Account.modify")
    def test_set_payout_schedule_for_account_stripe_error(
        self, mock_modify, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_schedule", onboarding_completed=True
        )
        mock_modify.side_effect = stripe.StripeError("modify failed")

        with pytest.raises(ServiceException, match="Failed to set payout schedule"):
            stripe_service.set_payout_schedule_for_account(
                instructor_profile_id=profile.id,
                interval="weekly",
                weekly_anchor="tuesday",
            )

    def test_set_payout_schedule_for_account_missing_account(
        self, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        """Missing accounts should raise when setting payout schedule."""
        _, profile, _ = test_instructor

        with pytest.raises(ServiceException, match="Connected account not found"):
            stripe_service.set_payout_schedule_for_account(instructor_profile_id=profile.id)

    def test_refresh_instructor_identity_sets_verified_status(
        self, stripe_service: StripeService, test_instructor: tuple
    ) -> None:
        """Identity refresh should reflect account verification state."""
        user, profile, _ = test_instructor
        stripe_service.instructor_repository.update(profile.id, bgc_in_dispute=True)

        with patch.object(
            stripe_service,
            "check_account_status",
            return_value={"charges_enabled": True, "requirements": []},
        ):
            refreshed = stripe_service.refresh_instructor_identity(user=user)

        assert refreshed.verified is True
        assert refreshed.status == "verified"
        updated_profile = stripe_service.instructor_repository.get_by_user_id(user.id)
        assert updated_profile.bgc_in_dispute is False

    def test_refresh_instructor_identity_missing_profile(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        with pytest.raises(ServiceException, match="Instructor profile not found"):
            stripe_service.refresh_instructor_identity(user=test_user)

    # ========== Payment Processing Tests ==========

    @patch("app.services.pricing_service.PricingService.compute_booking_pricing")
    def test_build_charge_context_with_requested_credit(
        self,
        mock_pricing,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        """Requested credits should be locked and reflected in the charge context."""

        base_price_cents = 10000
        config, _ = stripe_service.config_service.get_pricing_config()
        tier_pct = Decimal(str(config["instructor_tiers"][1]["pct"]))
        student_fee_pct = Decimal(str(config["student_fee_pct"]))
        credit_locked = 7 * 100
        student_fee_cents = int(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = int(Decimal(base_price_cents) * tier_pct)
        mock_pricing.return_value = {
            "base_price_cents": base_price_cents,
            "student_fee_cents": student_fee_cents,
            "instructor_platform_fee_cents": instructor_platform_fee_cents,
            "target_instructor_payout_cents": base_price_cents - instructor_platform_fee_cents,
            "credit_applied_cents": credit_locked,
            "student_pay_cents": base_price_cents + student_fee_cents - credit_locked,
            "application_fee_cents": student_fee_cents + instructor_platform_fee_cents - credit_locked,
            "top_up_transfer_cents": 0,
            "instructor_tier_pct": float(tier_pct),
        }

        stripe_service.payment_repository.get_applied_credit_cents_for_booking = MagicMock(
            return_value=0
        )

        with patch(
            "app.services.credit_service.CreditService.reserve_credits_for_booking"
        ) as reserve_mock:
            reserve_mock.return_value = 700
            context = stripe_service.build_charge_context(
                booking_id=test_booking.id, requested_credit_cents=900
            )

        reserve_mock.assert_called_once_with(
            user_id=test_booking.student_id,
            booking_id=test_booking.id,
            max_amount_cents=900,
            use_transaction=False,
        )
        stripe_service.payment_repository.get_applied_credit_cents_for_booking.assert_called_once_with(
            test_booking.id
        )
        mock_pricing.assert_called_once_with(
            booking_id=test_booking.id,
            applied_credit_cents=700,
            persist=True,
        )

        assert context.applied_credit_cents == credit_locked
        assert context.application_fee_cents == (
            student_fee_cents + instructor_platform_fee_cents - credit_locked
        )
        assert context.student_pay_cents == (
            base_price_cents + student_fee_cents - credit_locked
        )
        assert context.instructor_tier_pct == tier_pct

    @patch("app.services.pricing_service.PricingService.compute_booking_pricing")
    def test_build_charge_context_without_requested_credit(
        self,
        mock_pricing,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        """When credits were already locked, reuse the stored amount."""

        base_price_cents = 9000
        config, _ = stripe_service.config_service.get_pricing_config()
        tier_pct = Decimal(str(config["instructor_tiers"][-1]["pct"]))
        student_fee_pct = Decimal(str(config["student_fee_pct"]))
        locked_credit = 5 * 100
        student_fee_cents = int(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = int(Decimal(base_price_cents) * tier_pct)
        mock_pricing.return_value = {
            "base_price_cents": base_price_cents,
            "student_fee_cents": student_fee_cents,
            "instructor_platform_fee_cents": instructor_platform_fee_cents,
            "target_instructor_payout_cents": base_price_cents - instructor_platform_fee_cents,
            "credit_applied_cents": locked_credit,
            "student_pay_cents": base_price_cents + student_fee_cents - locked_credit,
            "application_fee_cents": student_fee_cents + instructor_platform_fee_cents - locked_credit,
            "top_up_transfer_cents": 0,
            "instructor_tier_pct": float(tier_pct),
        }

        stripe_service.payment_repository.get_applied_credit_cents_for_booking = MagicMock(
            return_value=locked_credit
        )

        with patch(
            "app.services.credit_service.CreditService.reserve_credits_for_booking"
        ) as reserve_mock:
            context = stripe_service.build_charge_context(
                booking_id=test_booking.id, requested_credit_cents=None
            )

        reserve_mock.assert_not_called()
        stripe_service.payment_repository.get_applied_credit_cents_for_booking.assert_called_once_with(
            test_booking.id
        )
        mock_pricing.assert_called_once_with(
            booking_id=test_booking.id,
            applied_credit_cents=500,
            persist=True,
        )

        assert context.applied_credit_cents == locked_credit
        assert context.top_up_transfer_cents == 0
        assert context.instructor_tier_pct == tier_pct

    @patch("app.services.pricing_service.PricingService.compute_booking_pricing")
    def test_build_charge_context_ignores_new_requested_credit_after_lock(
        self,
        mock_pricing,
        stripe_service: StripeService,
        test_booking: Booking,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Retries should reuse previously locked credits and log the guardrail."""

        base_price_cents = 9000
        config, _ = stripe_service.config_service.get_pricing_config()
        student_fee_pct = Decimal(str(config["student_fee_pct"]))
        tier_pct = Decimal(str(config["instructor_tiers"][-1]["pct"]))
        student_fee_cents = int(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = int(Decimal(base_price_cents) * tier_pct)
        locked_credit_cents = 12 * 100
        mock_pricing.return_value = {
            "base_price_cents": base_price_cents,
            "student_fee_cents": student_fee_cents,
            "instructor_platform_fee_cents": instructor_platform_fee_cents,
            "target_instructor_payout_cents": base_price_cents - instructor_platform_fee_cents,
            "credit_applied_cents": locked_credit_cents,
            "student_pay_cents": base_price_cents + student_fee_cents - locked_credit_cents,
            "application_fee_cents": student_fee_cents + instructor_platform_fee_cents - locked_credit_cents,
            "top_up_transfer_cents": 0,
            "instructor_tier_pct": float(tier_pct),
        }

        stripe_service.payment_repository.get_applied_credit_cents_for_booking = MagicMock(
            return_value=locked_credit_cents
        )

        with patch(
            "app.services.credit_service.CreditService.reserve_credits_for_booking"
        ) as reserve_mock, caplog.at_level(logging.WARNING):
            context = stripe_service.build_charge_context(
                booking_id=test_booking.id, requested_credit_cents=5000
            )

        reserve_mock.assert_not_called()
        assert context.applied_credit_cents == locked_credit_cents
        assert any(
            record.message == "requested_credit_ignored_due_to_existing_usage"
            for record in caplog.records
        )

    def test_build_charge_context_missing_booking(self, stripe_service: StripeService) -> None:
        with pytest.raises(ServiceException, match="Booking not found for charge context"):
            stripe_service.build_charge_context("missing_booking")

    @patch("app.services.pricing_service.PricingService.compute_booking_pricing")
    def test_build_charge_context_logs_top_up_transfer(
        self,
        mock_pricing,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        base_price_cents = 10000
        student_fee_cents = 1200
        instructor_platform_fee_cents = 1000
        top_up_transfer_cents = 500
        mock_pricing.return_value = {
            "base_price_cents": base_price_cents,
            "student_fee_cents": student_fee_cents,
            "instructor_platform_fee_cents": instructor_platform_fee_cents,
            "target_instructor_payout_cents": base_price_cents - instructor_platform_fee_cents,
            "credit_applied_cents": 0,
            "student_pay_cents": base_price_cents + student_fee_cents,
            "application_fee_cents": student_fee_cents + instructor_platform_fee_cents,
            "top_up_transfer_cents": top_up_transfer_cents,
            "instructor_tier_pct": 0.1,
        }

        stripe_service.payment_repository.get_applied_credit_cents_for_booking = MagicMock(
            return_value=0
        )

        context = stripe_service.build_charge_context(
            booking_id=test_booking.id, requested_credit_cents=None
        )

        assert context.top_up_transfer_cents == top_up_transfer_cents

    def test_build_charge_context_wraps_unexpected_error(
        self, stripe_service: StripeService
    ) -> None:
        with patch.object(
            stripe_service.booking_repository, "get_by_id", side_effect=Exception("db down")
        ):
            with pytest.raises(ServiceException, match="Failed to build charge context"):
                stripe_service.build_charge_context("booking_error")

    def test_get_applied_credit_cents_prefers_used_events(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Repository should count only credit_used amounts when available."""

        repo = stripe_service.payment_repository
        repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"used_cents": 800},
        )
        repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credits_applied",
            event_data={"applied_cents": 800},
        )

        assert repo.get_applied_credit_cents_for_booking(test_booking.id) == 800

    def test_get_applied_credit_cents_falls_back_to_aggregate(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Legacy bookings without credit_used events should still return applied total."""

        repo = stripe_service.payment_repository
        repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credits_applied",
            event_data={"applied_cents": 500},
        )

        assert repo.get_applied_credit_cents_for_booking(test_booking.id) == 500

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_success(self, mock_create, stripe_service: StripeService, test_booking: Booking):
        """Test successful payment intent creation."""
        config, _ = stripe_service.config_service.get_pricing_config()
        tier_pct = Decimal(str(config["instructor_tiers"][1]["pct"]))
        student_fee_pct = Decimal(str(config["student_fee_pct"]))
        base_price_cents = 10000
        credit_applied = 20 * 100
        student_fee_cents = int(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = int(Decimal(base_price_cents) * tier_pct)
        target_payout_cents = base_price_cents - instructor_platform_fee_cents
        student_pay_cents = base_price_cents + student_fee_cents - credit_applied
        application_fee_cents = student_fee_cents + instructor_platform_fee_cents - credit_applied
        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=credit_applied,
            base_price_cents=base_price_cents,
            student_fee_cents=student_fee_cents,
            instructor_platform_fee_cents=instructor_platform_fee_cents,
            target_instructor_payout_cents=target_payout_cents,
            student_pay_cents=student_pay_cents,
            application_fee_cents=application_fee_cents,
            top_up_transfer_cents=max(0, target_payout_cents - student_pay_cents),
            instructor_tier_pct=tier_pct,
        )

        # Mock Stripe response
        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        # Create payment intent
        payment = stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_test123",
            destination_account_id="acct_instructor123",
            charge_context=context,
        )

        # Verify Stripe API call
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["amount"] == student_pay_cents
        assert call_args["currency"] == "usd"
        assert call_args["customer"] == "cus_test123"
        assert call_args["transfer_data"]["destination"] == "acct_instructor123"
        # With transfer_data[amount] architecture, we set transfer amount instead of application fee
        assert call_args["transfer_data"]["amount"] == target_payout_cents
        assert "application_fee_amount" not in call_args
        assert call_args["transfer_group"] == f"booking:{test_booking.id}"

        metadata = call_args["metadata"]
        assert metadata["instructor_tier_pct"] == str(tier_pct)
        assert metadata["base_price_cents"] == str(base_price_cents)
        assert metadata["student_fee_cents"] == str(student_fee_cents)
        assert metadata["platform_fee_cents"] == str(instructor_platform_fee_cents)
        assert metadata["applied_credit_cents"] == str(credit_applied)
        assert metadata["student_pay_cents"] == str(student_pay_cents)
        assert metadata["application_fee_cents"] == str(application_fee_cents)
        assert metadata["target_instructor_payout_cents"] == str(target_payout_cents)

        # Verify database record
        assert payment.booking_id == test_booking.id
        assert payment.stripe_payment_intent_id == "pi_test123"
        assert payment.amount == student_pay_cents
        assert payment.application_fee == application_fee_cents

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_caps_transfer_amount_when_credits_reduce_charge(
        self, mock_create, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Transfer amount should not exceed the actual charge when credits reduce the amount."""
        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=8000,
            base_price_cents=10000,
            student_fee_cents=1200,
            instructor_platform_fee_cents=1500,
            target_instructor_payout_cents=8500,
            student_pay_cents=3200,
            application_fee_cents=0,
            top_up_transfer_cents=5300,
            instructor_tier_pct=Decimal("0.15"),
        )

        mock_intent = MagicMock()
        mock_intent.id = "pi_cap_123"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        payment = stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_cap",
            destination_account_id="acct_cap",
            charge_context=context,
        )

        call_args = mock_create.call_args[1]
        assert call_args["transfer_data"]["amount"] == context.student_pay_cents
        assert payment.application_fee == 0

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_builds_context_for_requested_credit(
        self, mock_create, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=100,
            base_price_cents=2000,
            student_fee_cents=240,
            instructor_platform_fee_cents=200,
            target_instructor_payout_cents=1800,
            student_pay_cents=2140,
            application_fee_cents=340,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)

        mock_intent = MagicMock()
        mock_intent.id = "pi_ctx"
        mock_intent.status = "requires_capture"
        mock_create.return_value = mock_intent

        payment = stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_ctx",
            destination_account_id="acct_ctx",
            requested_credit_cents=100,
        )

        stripe_service.build_charge_context.assert_called_once_with(test_booking.id, 100)
        assert payment.stripe_payment_intent_id == "pi_ctx"

    def test_create_payment_intent_requires_amount_without_context(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """amount_cents is required when no charge context is provided."""
        with pytest.raises(ServiceException, match="amount_cents is required"):
            stripe_service.create_payment_intent(
                booking_id=test_booking.id,
                customer_id="cus_noctx",
                destination_account_id="acct_noctx",
            )

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_without_context_uses_platform_fee(
        self, mock_create, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Fallback metadata should include applied_credit_cents and platform fee."""
        mock_intent = MagicMock()
        mock_intent.id = "pi_noctx"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        amount_cents = 2400
        payment = stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_noctx",
            destination_account_id="acct_noctx",
            amount_cents=amount_cents,
        )

        call_args = mock_create.call_args[1]
        expected_platform_retained = int(amount_cents * stripe_service.platform_fee_percentage)
        expected_transfer_amount = amount_cents - expected_platform_retained
        # With transfer_data[amount] architecture, we set transfer amount instead of application fee
        assert call_args["transfer_data"]["amount"] == expected_transfer_amount
        assert "application_fee_amount" not in call_args
        assert call_args["capture_method"] == "manual"
        assert call_args["metadata"]["booking_id"] == test_booking.id
        assert call_args["metadata"]["applied_credit_cents"] == "0"
        assert payment.stripe_payment_intent_id == "pi_noctx"

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_parity_parse_error_does_not_fail(
        self,
        mock_create,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        stripe_service.stripe_configured = True
        mock_intent = MagicMock()
        mock_intent.id = "pi_parse"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=Decimal("100.5"),
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=100,
            student_pay_cents=Decimal("10.5"),
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.1"),
        )

        payment = stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_parse",
            destination_account_id="acct_parse",
            charge_context=context,
        )

        assert payment.stripe_payment_intent_id == "pi_parse"

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_stripe_error(
        self, mock_create, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        stripe_service.stripe_configured = True
        mock_create.side_effect = stripe.StripeError("pi error")

        with pytest.raises(ServiceException, match="Failed to create payment intent"):
            stripe_service.create_payment_intent(
                booking_id=test_booking.id,
                customer_id="cus_fail",
                destination_account_id="acct_fail",
                amount_cents=1200,
            )

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_fallback_when_unconfigured(
        self, mock_create, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Return mock intent when Stripe is not configured."""
        stripe_service.stripe_configured = False
        mock_create.side_effect = Exception("stripe offline")

        payment = stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_noctx",
            destination_account_id="acct_noctx",
            amount_cents=1200,
        )

        assert payment.stripe_payment_intent_id == f"mock_pi_{test_booking.id}"
        assert payment.status == "requires_payment_method"

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_skips_parity_assertions_in_production(
        self,
        mock_create,
        stripe_service: StripeService,
        test_booking: Booking,
        monkeypatch,
    ):
        """Parity assertions should be disabled in production environment."""

        monkeypatch.setattr(settings, "environment", "production", raising=False)
        debug_spy = MagicMock()
        monkeypatch.setattr(stripe_service.logger, "debug", debug_spy)

        base_price_cents = 12000
        tier_pct = Decimal("0.12")
        student_fee_pct = Decimal("0.12")
        student_fee_cents = _round_cents(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = _round_cents(Decimal(base_price_cents) * tier_pct)
        credit_applied = 0
        student_pay_cents = base_price_cents + student_fee_cents - credit_applied
        application_fee_cents = student_fee_cents + instructor_platform_fee_cents - credit_applied
        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=credit_applied,
            base_price_cents=base_price_cents,
            student_fee_cents=student_fee_cents,
            instructor_platform_fee_cents=instructor_platform_fee_cents,
            target_instructor_payout_cents=base_price_cents - instructor_platform_fee_cents,
            student_pay_cents=student_pay_cents,
            application_fee_cents=application_fee_cents,
            top_up_transfer_cents=0,
            instructor_tier_pct=tier_pct,
        )

        mock_intent = MagicMock()
        mock_intent.id = "pi_prod123"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        stripe_service.create_payment_intent(
            booking_id=test_booking.id,
            customer_id="cus_prod123",
            destination_account_id="acct_prod123",
            charge_context=context,
        )

        assert all(
            "stripe.pi.preview_parity" not in str(call.args[0]) if call.args else True
            for call in debug_spy.call_args_list
        )

    @patch("stripe.PaymentIntent.create")
    def test_create_or_retry_booking_payment_intent(
        self,
        mock_create,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        """Adapter should build context and create manual capture PI."""

        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_student123"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        config, _ = stripe_service.config_service.get_pricing_config()
        tier_pct = Decimal(str(config["instructor_tiers"][1]["pct"]))
        student_fee_pct = Decimal(str(config["student_fee_pct"]))
        base_price_cents = 10000
        credit_applied = 15 * 100
        student_fee_cents = int(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = int(Decimal(base_price_cents) * tier_pct)
        target_payout_cents = base_price_cents - instructor_platform_fee_cents
        student_pay_cents = base_price_cents + student_fee_cents - credit_applied
        application_fee_cents = student_fee_cents + instructor_platform_fee_cents - credit_applied
        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=credit_applied,
            base_price_cents=base_price_cents,
            student_fee_cents=student_fee_cents,
            instructor_platform_fee_cents=instructor_platform_fee_cents,
            target_instructor_payout_cents=target_payout_cents,
            student_pay_cents=student_pay_cents,
            application_fee_cents=application_fee_cents,
            top_up_transfer_cents=max(0, target_payout_cents - student_pay_cents),
            instructor_tier_pct=tier_pct,
        )

        stripe_service.build_charge_context = MagicMock(return_value=context)

        mock_intent = MagicMock()
        mock_intent.id = "pi_ctx123"
        mock_intent.status = "requires_capture"
        mock_create.return_value = mock_intent

        result = stripe_service.create_or_retry_booking_payment_intent(
            booking_id=test_booking.id,
            payment_method_id="pm_card123",
        )

        assert result is mock_intent

        mock_create.assert_called_once()
        kwargs = mock_create.call_args[1]
        assert kwargs["amount"] == context.student_pay_cents
        # With transfer_data[amount] architecture, we set transfer amount instead of application fee
        assert kwargs["transfer_data"]["amount"] == context.target_instructor_payout_cents
        assert "application_fee_amount" not in kwargs
        assert kwargs["transfer_group"] == f"booking:{test_booking.id}"
        assert kwargs["capture_method"] == "manual"
        assert kwargs["payment_method"] == "pm_card123"

    @patch("stripe.PaymentIntent.create")
    def test_create_or_retry_booking_payment_intent_caps_transfer_amount(
        self,
        mock_create,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        """Transfer amount should be capped when credits reduce student charge."""
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_student123"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=8000,
            base_price_cents=10000,
            student_fee_cents=1200,
            instructor_platform_fee_cents=1500,
            target_instructor_payout_cents=8500,
            student_pay_cents=3200,
            application_fee_cents=0,
            top_up_transfer_cents=5300,
            instructor_tier_pct=Decimal("0.15"),
        )

        stripe_service.build_charge_context = MagicMock(return_value=context)

        mock_intent = MagicMock()
        mock_intent.id = "pi_ctx_cap"
        mock_intent.status = "requires_capture"
        mock_create.return_value = mock_intent

        stripe_service.create_or_retry_booking_payment_intent(
            booking_id=test_booking.id,
            payment_method_id="pm_card123",
        )

        kwargs = mock_create.call_args[1]
        assert kwargs["transfer_data"]["amount"] == context.student_pay_cents
        assert kwargs["confirm"] is True
        assert kwargs["off_session"] is True

        metadata = kwargs["metadata"]
        assert metadata["applied_credit_cents"] == str(context.applied_credit_cents)
        assert metadata["base_price_cents"] == str(context.base_price_cents)

    @patch("stripe.PaymentIntent.create")
    def test_create_or_retry_booking_payment_intent_fallback_when_unconfigured(
        self,
        mock_create,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        """Unconfigured Stripe should fall back to a local payment intent record."""
        _, profile, _ = test_instructor
        stripe_service.stripe_configured = False

        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_student_fallback"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_fallback", onboarding_completed=True
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=500,
            target_instructor_payout_cents=4500,
            student_pay_cents=5000,
            application_fee_cents=500,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)
        mock_create.side_effect = Exception("stripe down")

        result = stripe_service.create_or_retry_booking_payment_intent(
            booking_id=test_booking.id,
            payment_method_id=None,
        )

        assert result.id == f"mock_pi_{test_booking.id}"
        assert result.status == "requires_payment_method"
        record = stripe_service.payment_repository.get_payment_by_intent_id(
            f"mock_pi_{test_booking.id}"
        )
        assert record is not None
        assert test_booking.payment_intent_id == f"mock_pi_{test_booking.id}"
        assert test_booking.payment_status == "authorized"

    def test_create_or_retry_booking_payment_intent_missing_booking(
        self, stripe_service: StripeService
    ) -> None:
        with pytest.raises(ServiceException, match="Booking .* not found"):
            stripe_service.create_or_retry_booking_payment_intent(booking_id="missing_booking")

    def test_create_or_retry_booking_payment_intent_missing_customer(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        with pytest.raises(ServiceException, match="No Stripe customer"):
            stripe_service.create_or_retry_booking_payment_intent(
                booking_id=test_booking.id, payment_method_id=None
            )

    def test_create_or_retry_booking_payment_intent_missing_instructor_profile(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_missing_profile"
        )

        with patch.object(
            stripe_service.instructor_repository, "get_by_user_id", return_value=None
        ):
            with pytest.raises(ServiceException, match="Instructor profile not found"):
                stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=test_booking.id,
                    payment_method_id=None,
                )

    def test_create_or_retry_booking_payment_intent_missing_connected_account(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_no_acct"
        )

        with patch.object(
            stripe_service.payment_repository,
            "get_connected_account_by_instructor_id",
            return_value=None,
        ):
            with pytest.raises(ServiceException, match="payment account not set up"):
                stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=test_booking.id, payment_method_id=None
                )

    def test_create_or_retry_booking_payment_intent_zero_amount(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_zero_charge"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_zero_charge", onboarding_completed=True
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=100,
            base_price_cents=100,
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=100,
            student_pay_cents=0,
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)

        with pytest.raises(ServiceException, match="Charge amount is zero"):
            stripe_service.create_or_retry_booking_payment_intent(
                booking_id=test_booking.id,
                payment_method_id=None,
            )

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_requires_action(
        self, mock_create, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        """Manual authorization should return action requirements when Stripe demands it."""
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_manual123"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_manual123", onboarding_completed=True
        )

        mock_pi = MagicMock()
        mock_pi.id = "pi_manual_action"
        mock_pi.status = "requires_action"
        mock_pi.client_secret = "secret_123"
        mock_create.return_value = mock_pi

        result = stripe_service.create_and_confirm_manual_authorization(
            booking_id=test_booking.id,
            customer_id="cus_manual123",
            destination_account_id="acct_manual123",
            payment_method_id="pm_manual123",
            amount_cents=1500,
        )

        assert result["requires_action"] is True
        assert result["client_secret"] == "secret_123"
        assert result["status"] == "requires_action"
        record = stripe_service.payment_repository.get_payment_by_intent_id("pi_manual_action")
        assert record is not None

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_success(
        self, mock_create, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        """Manual authorization should persist non-action statuses."""
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_manual456"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_manual456", onboarding_completed=True
        )

        mock_pi = MagicMock()
        mock_pi.id = "pi_manual_ok"
        mock_pi.status = "requires_capture"
        mock_create.return_value = mock_pi

        result = stripe_service.create_and_confirm_manual_authorization(
            booking_id=test_booking.id,
            customer_id="cus_manual456",
            destination_account_id="acct_manual456",
            payment_method_id="pm_manual456",
            amount_cents=2000,
        )

        assert result["requires_action"] is False
        assert result["client_secret"] is None
        assert result["status"] == "requires_capture"
        record = stripe_service.payment_repository.get_payment_by_intent_id("pi_manual_ok")
        assert record is not None

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_uses_upsert(
        self, mock_create, stripe_service: StripeService, monkeypatch
    ) -> None:
        mock_pi = MagicMock()
        mock_pi.id = "pi_upsert"
        mock_pi.status = "requires_capture"
        mock_create.return_value = mock_pi

        upsert = MagicMock()
        monkeypatch.setattr(
            stripe_service.payment_repository, "upsert_payment_record", upsert, raising=False
        )

        result = stripe_service.create_and_confirm_manual_authorization(
            booking_id="booking_upsert",
            customer_id="cus_upsert",
            destination_account_id="acct_upsert",
            payment_method_id="pm_upsert",
            amount_cents=1200,
        )

        assert result["status"] == "requires_capture"
        upsert.assert_called_once()

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_fallback_creates_record(
        self, mock_create, stripe_service: StripeService, monkeypatch
    ) -> None:
        mock_pi = MagicMock()
        mock_pi.id = "pi_fallback"
        mock_pi.status = "requires_capture"
        mock_create.return_value = mock_pi

        monkeypatch.setattr(
            stripe_service.payment_repository, "upsert_payment_record", None, raising=False
        )
        stripe_service.payment_repository.get_payment_by_intent_id = MagicMock(return_value=None)
        stripe_service.payment_repository.create_payment_record = MagicMock()

        stripe_service.create_and_confirm_manual_authorization(
            booking_id="booking_fallback",
            customer_id="cus_fallback",
            destination_account_id="acct_fallback",
            payment_method_id="pm_fallback",
            amount_cents=1100,
        )

        stripe_service.payment_repository.create_payment_record.assert_called_once()

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_ignores_persistence_error(
        self, mock_create, stripe_service: StripeService, monkeypatch
    ) -> None:
        mock_pi = MagicMock()
        mock_pi.id = "pi_persist_fail"
        mock_pi.status = "requires_capture"
        mock_create.return_value = mock_pi

        monkeypatch.setattr(
            stripe_service.payment_repository, "upsert_payment_record", None, raising=False
        )
        stripe_service.payment_repository.get_payment_by_intent_id = MagicMock(
            side_effect=Exception("db down")
        )

        result = stripe_service.create_and_confirm_manual_authorization(
            booking_id="booking_persist_fail",
            customer_id="cus_persist_fail",
            destination_account_id="acct_persist_fail",
            payment_method_id="pm_persist_fail",
            amount_cents=1000,
        )

        assert result["status"] == "requires_capture"

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_stripe_error(
        self, mock_create, stripe_service: StripeService
    ) -> None:
        mock_create.side_effect = stripe.StripeError("stripe down")

        with pytest.raises(ServiceException, match="Failed to authorize payment"):
            stripe_service.create_and_confirm_manual_authorization(
                booking_id="booking_stripe_err",
                customer_id="cus_stripe_err",
                destination_account_id="acct_stripe_err",
                payment_method_id="pm_stripe_err",
                amount_cents=1000,
            )

    @patch("stripe.PaymentIntent.create")
    def test_create_and_confirm_manual_authorization_unexpected_error(
        self, mock_create, stripe_service: StripeService
    ) -> None:
        mock_create.side_effect = Exception("boom")

        with pytest.raises(ServiceException, match="Failed to authorize payment"):
            stripe_service.create_and_confirm_manual_authorization(
                booking_id="booking_err",
                customer_id="cus_err",
                destination_account_id="acct_err",
                payment_method_id="pm_err",
                amount_cents=1000,
            )

    @patch("stripe.Transfer.create")
    @patch("stripe.PaymentIntent.capture")
    @patch("stripe.PaymentIntent.retrieve")
    def test_capture_booking_payment_intent_wrapper(
        self,
        mock_retrieve,
        mock_capture,
        mock_transfer,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        """Wrapper should pass through capture and trigger top-up once."""

        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_student123"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        base_price_cents = 8000
        applied_credit_cents = 3000
        instructor_pct = _default_instructor_pct(stripe_service)
        student_fee_pct = _student_fee_pct(stripe_service)
        student_fee_cents = _round_cents(Decimal(base_price_cents) * student_fee_pct)
        instructor_platform_fee_cents = _round_cents(Decimal(base_price_cents) * instructor_pct)
        target_instructor_payout_cents = base_price_cents - instructor_platform_fee_cents
        subtotal_cents = base_price_cents + student_fee_cents
        student_pay_cents = max(0, subtotal_cents - applied_credit_cents)
        application_fee_cents = max(0, student_fee_cents + instructor_platform_fee_cents - applied_credit_cents)
        top_up_transfer_cents = (
            target_instructor_payout_cents - student_pay_cents
            if application_fee_cents == 0 and student_pay_cents < target_instructor_payout_cents
            else 0
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=applied_credit_cents,
            base_price_cents=base_price_cents,
            student_fee_cents=student_fee_cents,
            instructor_platform_fee_cents=instructor_platform_fee_cents,
            target_instructor_payout_cents=target_instructor_payout_cents,
            student_pay_cents=student_pay_cents,
            application_fee_cents=application_fee_cents,
            top_up_transfer_cents=top_up_transfer_cents,
            instructor_tier_pct=instructor_pct,
        )

        stripe_service.build_charge_context = MagicMock(return_value=context)

        stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_capture123",
            amount=context.student_pay_cents,
            application_fee=context.application_fee_cents,
            status="requires_capture",
        )

        capture_response = {
            "id": "pi_capture123",
            "status": "succeeded",
            "charges": {"data": []},
            "amount_received": context.student_pay_cents,
        }
        mock_capture.return_value = capture_response
        mock_retrieve.return_value = capture_response
        mock_transfer.return_value = {"id": "tr_topup123"}

        result = stripe_service.capture_booking_payment_intent(
            booking_id=test_booking.id,
            payment_intent_id="pi_capture123",
        )

        assert result["payment_intent"] == capture_response
        assert result["amount_received"] == context.student_pay_cents
        assert result["top_up_transfer_cents"] == context.top_up_transfer_cents
        mock_transfer.assert_called_once()
        transfer_kwargs = mock_transfer.call_args[1]
        assert transfer_kwargs["amount"] == context.top_up_transfer_cents
        assert transfer_kwargs["destination"] == "acct_instructor123"

        events = stripe_service.payment_repository.get_payment_events_for_booking(test_booking.id)
        assert any(evt.event_type == "top_up_transfer_created" for evt in events)

    @patch("stripe.Transfer.create")
    @patch("stripe.PaymentIntent.capture")
    @patch("stripe.PaymentIntent.retrieve")
    def test_capture_top_up_prefers_metadata_over_config_drift(
        self,
        mock_retrieve,
        mock_capture,
        mock_transfer,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        """Top-up computation should prefer metadata and remain idempotent across retries."""

        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_student123"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        instructor_pct = _default_instructor_pct(stripe_service)
        pi_metadata = {
            "booking_id": test_booking.id,
            "base_price_cents": "8000",
            "student_fee_cents": "960",
            "platform_fee_cents": "800",
            "applied_credit_cents": "2000",
            "student_pay_cents": "6960",
            "application_fee_cents": "0",
            "target_instructor_payout_cents": "7200",
            "instructor_tier_pct": str(instructor_pct),
        }

        capture_template = {
            "id": "pi_topup_meta",
            "status": "succeeded",
            "amount": 6960,
            "amount_received": 6960,
            "metadata": pi_metadata,
            "charges": {"data": []},
        }

        def _capture_side_effect(*_, **__):
            return {**capture_template, "metadata": dict(pi_metadata)}

        mock_capture.side_effect = _capture_side_effect
        mock_retrieve.side_effect = _capture_side_effect

        drift_context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=2000,
            base_price_cents=8000,
            student_fee_cents=1120,
            instructor_platform_fee_cents=800,
            target_instructor_payout_cents=7200,
            student_pay_cents=7120,
            application_fee_cents=80,
            top_up_transfer_cents=80,
            instructor_tier_pct=instructor_pct,
        )

        stripe_service.build_charge_context = MagicMock(return_value=drift_context)

        stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_topup_meta",
            amount=drift_context.student_pay_cents,
            application_fee=drift_context.application_fee_cents,
            status="requires_capture",
        )

        mock_transfer.return_value = {"id": "tr_topup_meta"}

        first_capture = stripe_service.capture_booking_payment_intent(
            booking_id=test_booking.id,
            payment_intent_id="pi_topup_meta",
        )

        expected_top_up = int(pi_metadata["target_instructor_payout_cents"]) - int(
            pi_metadata["student_pay_cents"]
        )
        assert first_capture["top_up_transfer_cents"] == expected_top_up
        assert first_capture["amount_received"] == 6960
        mock_transfer.assert_called_once()
        transfer_kwargs = mock_transfer.call_args[1]
        assert transfer_kwargs["amount"] == expected_top_up

        mock_transfer.reset_mock()

        second_capture = stripe_service.capture_booking_payment_intent(
            booking_id=test_booking.id,
            payment_intent_id="pi_topup_meta",
        )

        assert second_capture["top_up_transfer_cents"] == expected_top_up
        mock_transfer.assert_not_called()

    @patch("stripe.PaymentIntent.retrieve")
    def test_capture_booking_payment_intent_handles_retrieve_and_context_errors(
        self,
        mock_retrieve,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        stripe_service.stripe_configured = True
        mock_retrieve.side_effect = Exception("stripe retrieve failed")

        capture_result = {"payment_intent": None, "amount_received": 100}

        with (
            patch.object(stripe_service, "capture_payment_intent", return_value=capture_result),
            patch.object(stripe_service, "build_charge_context", side_effect=Exception("pricing fail")),
            patch.object(
                stripe_service.booking_repository, "get_by_id", side_effect=Exception("db down")
            ),
        ):
            result = stripe_service.capture_booking_payment_intent(
                booking_id=test_booking.id,
                payment_intent_id="pi_err",
            )

        assert result["payment_intent"] is None
        assert result["top_up_transfer_cents"] == 0

    def test_capture_booking_payment_intent_fallback_uses_dict_amount(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        stripe_service.stripe_configured = False
        _, profile, _ = test_instructor
        connected_account = MagicMock(stripe_account_id="acct_topup")

        payment_intent = {
            "id": "pi_fallback_dict",
            "amount": "1000",
            "metadata": {},
            "charges": {"data": []},
        }
        capture_result = {"payment_intent": payment_intent}

        ctx = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=1500,
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=1500,
            student_pay_cents=1000,
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )

        with (
            patch.object(stripe_service, "capture_payment_intent", return_value=capture_result),
            patch.object(stripe_service, "build_charge_context", return_value=ctx),
            patch.object(stripe_service.booking_repository, "get_by_id", return_value=test_booking),
            patch.object(stripe_service.instructor_repository, "get_by_user_id", return_value=profile),
            patch.object(
                stripe_service.payment_repository,
                "get_connected_account_by_instructor_id",
                return_value=connected_account,
            ),
            patch.object(stripe_service, "ensure_top_up_transfer") as mock_top_up,
        ):
            result = stripe_service.capture_booking_payment_intent(
                booking_id=test_booking.id,
                payment_intent_id="pi_fallback_dict",
            )

        assert result["top_up_transfer_cents"] == 500
        mock_top_up.assert_called_once()

    def test_capture_booking_payment_intent_handles_instructor_lookup_error(
        self,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        stripe_service.stripe_configured = False
        payment_intent = {
            "metadata": {
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "0",
            },
            "amount": 8500,
        }

        capture_result = {"payment_intent": payment_intent}

        with (
            patch.object(stripe_service, "capture_payment_intent", return_value=capture_result),
            patch.object(stripe_service.booking_repository, "get_by_id", return_value=test_booking),
            patch.object(
                stripe_service.instructor_repository,
                "get_by_user_id",
                side_effect=Exception("instructor lookup failed"),
            ),
        ):
            result = stripe_service.capture_booking_payment_intent(
                booking_id=test_booking.id,
                payment_intent_id="pi_instructor_err",
            )

        assert result["top_up_transfer_cents"] == 0

    def test_capture_booking_payment_intent_handles_connected_account_error(
        self,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        stripe_service.stripe_configured = False
        _, profile, _ = test_instructor
        payment_intent = {
            "metadata": {
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "0",
            },
            "amount": 8500,
        }

        capture_result = {"payment_intent": payment_intent}

        with (
            patch.object(stripe_service, "capture_payment_intent", return_value=capture_result),
            patch.object(stripe_service.booking_repository, "get_by_id", return_value=test_booking),
            patch.object(stripe_service.instructor_repository, "get_by_user_id", return_value=profile),
            patch.object(
                stripe_service.payment_repository,
                "get_connected_account_by_instructor_id",
                side_effect=Exception("acct lookup failed"),
            ),
        ):
            result = stripe_service.capture_booking_payment_intent(
                booking_id=test_booking.id,
                payment_intent_id="pi_account_err",
            )

        assert result["top_up_transfer_cents"] == 0

    def test_capture_booking_payment_intent_handles_top_up_transfer_error(
        self,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        stripe_service.stripe_configured = False
        _, profile, _ = test_instructor
        payment_intent = {
            "metadata": {
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "2000",
            },
            "amount": 5000,
        }

        capture_result = {"payment_intent": payment_intent}
        connected_account = MagicMock(stripe_account_id="acct_topup")

        with (
            patch.object(stripe_service, "capture_payment_intent", return_value=capture_result),
            patch.object(stripe_service.booking_repository, "get_by_id", return_value=test_booking),
            patch.object(stripe_service.instructor_repository, "get_by_user_id", return_value=profile),
            patch.object(
                stripe_service.payment_repository,
                "get_connected_account_by_instructor_id",
                return_value=connected_account,
            ),
            patch.object(stripe_service, "ensure_top_up_transfer", side_effect=Exception("boom")),
        ):
            result = stripe_service.capture_booking_payment_intent(
                booking_id=test_booking.id,
                payment_intent_id="pi_topup_err",
            )

        assert result["top_up_transfer_cents"] == 3500

    def test_ensure_top_up_transfer_noop_when_amount_zero(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Zero top-up amounts should short-circuit."""
        result = stripe_service.ensure_top_up_transfer(
            booking_id=test_booking.id,
            payment_intent_id="pi_zero",
            destination_account_id="acct_zero",
            amount_cents=0,
        )
        assert result is None

    @patch("stripe.Transfer.create")
    def test_ensure_top_up_transfer_noop_when_duplicate(
        self, mock_transfer, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Duplicate top-up events should not create another transfer."""
        stripe_service.payment_repository.create_payment_event(
            booking_id=test_booking.id,
            event_type="top_up_transfer_created",
            event_data={"payment_intent_id": "pi_dup", "amount_cents": 250},
        )

        result = stripe_service.ensure_top_up_transfer(
            booking_id=test_booking.id,
            payment_intent_id="pi_dup",
            destination_account_id="acct_dup",
            amount_cents=250,
        )

        assert result is None
        mock_transfer.assert_not_called()

    @patch("stripe.Transfer.create")
    def test_ensure_top_up_transfer_skips_when_latest_event_matches(
        self, mock_transfer, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        latest_event = MagicMock(
            event_data={"payment_intent_id": "pi_latest", "amount_cents": 500}
        )
        stripe_service.payment_repository.get_latest_payment_event = MagicMock(
            return_value=latest_event
        )

        result = stripe_service.ensure_top_up_transfer(
            booking_id=test_booking.id,
            payment_intent_id="pi_latest",
            destination_account_id="acct_latest",
            amount_cents=500,
        )

        assert result is None
        mock_transfer.assert_not_called()

    @patch("stripe.Transfer.create")
    def test_ensure_top_up_transfer_ignores_event_persist_error(
        self, mock_transfer, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        stripe_service.payment_repository.get_latest_payment_event = MagicMock(return_value=None)
        stripe_service.payment_repository.create_payment_event = MagicMock(
            side_effect=Exception("db down")
        )
        mock_transfer.return_value = {"id": "tr_topup"}

        result = stripe_service.ensure_top_up_transfer(
            booking_id=test_booking.id,
            payment_intent_id="pi_event_err",
            destination_account_id="acct_event_err",
            amount_cents=300,
        )

        assert result == {"id": "tr_topup"}

    @patch("stripe.Transfer.create")
    def test_ensure_top_up_transfer_stripe_error(
        self, mock_transfer, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Stripe transfer errors should surface as ServiceException."""
        mock_transfer.side_effect = stripe.StripeError("transfer failed")

        with pytest.raises(ServiceException, match="Failed to create top-up transfer"):
            stripe_service.ensure_top_up_transfer(
                booking_id=test_booking.id,
                payment_intent_id="pi_fail",
                destination_account_id="acct_fail",
                amount_cents=100,
            )

    @patch("stripe.PaymentIntent.confirm")
    def test_confirm_payment_intent_success(self, mock_confirm, stripe_service: StripeService, test_booking: Booking):
        """Test successful payment intent confirmation."""
        # Create payment record
        context = stripe_service.build_charge_context(test_booking.id)
        _payment = stripe_service.payment_repository.create_payment_record(
            test_booking.id,
            "pi_test123",
            context.student_pay_cents,
            context.application_fee_cents,
            "requires_payment_method",
        )

        # Mock Stripe response
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_confirm.return_value = mock_intent

        # Confirm payment
        confirmed_payment = stripe_service.confirm_payment_intent("pi_test123", "pm_card123")

        mock_confirm.assert_called_once_with(
            "pi_test123",
            payment_method="pm_card123",
            return_url=ANY,  # Will be settings.frontend_url + "/student/payment/complete"
        )

        # Verify status update
        assert confirmed_payment.status == "succeeded"

    @patch("stripe.PaymentIntent.confirm")
    def test_confirm_payment_intent_missing_record(
        self, mock_confirm, stripe_service: StripeService
    ) -> None:
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_confirm.return_value = mock_intent

        with patch.object(
            stripe_service.payment_repository, "update_payment_status", return_value=None
        ):
            with pytest.raises(ServiceException, match="Payment record not found"):
                stripe_service.confirm_payment_intent("pi_missing", "pm_card")

    @patch("stripe.PaymentIntent.confirm")
    def test_confirm_payment_intent_stripe_error(
        self, mock_confirm, stripe_service: StripeService
    ) -> None:
        mock_confirm.side_effect = stripe.StripeError("confirm failed")

        with pytest.raises(ServiceException, match="Failed to confirm payment"):
            stripe_service.confirm_payment_intent("pi_error", "pm_card")

    @patch("stripe.PaymentIntent.confirm")
    @patch("stripe.PaymentIntent.create")
    def test_process_booking_payment_success(
        self, mock_create, mock_confirm, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ):
        """Test end-to-end booking payment processing."""
        _, profile, _ = test_instructor

        # Create customer and connected account
        _customer = stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_student123")
        _connected_account = stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        base_price_cents = 5000
        applied_credit_cents = 0
        instructor_pct = _default_instructor_pct(stripe_service)
        student_fee_cents = 0
        instructor_platform_fee_cents = _round_cents(Decimal(base_price_cents) * instructor_pct)
        target_instructor_payout_cents = base_price_cents - instructor_platform_fee_cents
        student_pay_cents = base_price_cents
        application_fee_cents = instructor_platform_fee_cents
        charge_context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=applied_credit_cents,
            base_price_cents=base_price_cents,
            student_fee_cents=student_fee_cents,
            instructor_platform_fee_cents=instructor_platform_fee_cents,
            target_instructor_payout_cents=target_instructor_payout_cents,
            student_pay_cents=student_pay_cents,
            application_fee_cents=application_fee_cents,
            top_up_transfer_cents=0,
            instructor_tier_pct=instructor_pct,
        )

        stripe_service.build_charge_context = MagicMock(return_value=charge_context)

        # Mock Stripe responses
        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        mock_confirmed = MagicMock()
        mock_confirmed.status = "succeeded"
        mock_confirm.return_value = mock_confirmed

        # Process payment
        result = stripe_service.process_booking_payment(test_booking.id, "pm_card123")

        stripe_service.build_charge_context.assert_called_once_with(
            booking_id=test_booking.id, requested_credit_cents=None
        )
        create_kwargs = mock_create.call_args[1]
        assert create_kwargs["amount"] == 5000
        # With transfer_data[amount] architecture, we set transfer amount instead of application fee
        assert create_kwargs["transfer_data"]["amount"] == target_instructor_payout_cents
        assert "application_fee_amount" not in create_kwargs
        assert create_kwargs["transfer_group"] == f"booking:{test_booking.id}"

        # Verify result
        assert result["success"] is True
        assert result["payment_intent_id"] == "pi_test123"
        assert result["status"] == "succeeded"
        assert result["amount"] == 5000  # $50.00 in cents
        # Platform retained amount stored in application_fee field
        assert result["application_fee"] == application_fee_cents

    @patch("stripe.PaymentIntent.confirm")
    @patch("stripe.PaymentIntent.create")
    def test_process_booking_payment_scheduled_auth(
        self, mock_create, mock_confirm, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ):
        """Bookings >=24h away should schedule authorization without confirming."""
        _, profile, _ = test_instructor

        stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_sched123")
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_sched123", onboarding_completed=True
        )

        start_at = (datetime.now(timezone.utc) + timedelta(hours=48)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        end_at = start_at + timedelta(hours=1)
        test_booking.booking_date = start_at.date()
        test_booking.start_time = start_at.time().replace(tzinfo=None)
        test_booking.end_time = end_at.time().replace(tzinfo=None)
        test_booking.booking_start_utc = start_at
        test_booking.booking_end_utc = end_at

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=5000,
            student_pay_cents=5000,
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)

        mock_intent = MagicMock()
        mock_intent.id = "pi_sched123"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        result = stripe_service.process_booking_payment(test_booking.id, "pm_card123")

        assert result["success"] is True
        assert result["status"] == "scheduled"
        assert test_booking.payment_status == "scheduled"
        assert test_booking.auth_scheduled_for == start_at - timedelta(hours=24)
        mock_confirm.assert_not_called()

    def test_process_booking_payment_credit_only(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        """Credits covering the full amount should skip Stripe charge."""
        _, profile, _ = test_instructor

        stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_credit123")
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_credit123", onboarding_completed=True
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=5000,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=5000,
            student_pay_cents=0,
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)

        result = stripe_service.process_booking_payment(
            booking_id=test_booking.id, payment_method_id=None
        )

        assert result["status"] == "succeeded"
        assert result["payment_intent_id"] == "credit_only"
        assert test_booking.payment_status == "authorized"

        events = stripe_service.payment_repository.get_payment_events_for_booking(test_booking.id)
        assert any(evt.event_type == "auth_succeeded_credits_only" for evt in events)

    def test_process_booking_payment_requires_payment_method(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        """Missing payment methods should raise when balance remains."""
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_missing_pm")
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_missing_pm", onboarding_completed=True
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=500,
            target_instructor_payout_cents=4500,
            student_pay_cents=5000,
            application_fee_cents=500,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)

        with pytest.raises(ServiceException, match="Payment method required"):
            stripe_service.process_booking_payment(booking_id=test_booking.id, payment_method_id=None)

    @patch("stripe.PaymentIntent.confirm")
    @patch("stripe.PaymentIntent.create")
    def test_process_booking_payment_requires_action(
        self, mock_create, mock_confirm, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        """3DS-required payments should return client_secret."""
        _, profile, _ = test_instructor

        stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_action123")
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_action123", onboarding_completed=True
        )

        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=500,
            target_instructor_payout_cents=4500,
            student_pay_cents=5000,
            application_fee_cents=500,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=context)

        mock_intent = MagicMock()
        mock_intent.id = "pi_action123"
        mock_intent.status = "requires_payment_method"
        mock_create.return_value = mock_intent

        mock_confirmed = MagicMock()
        mock_confirmed.status = "requires_action"
        mock_confirmed.client_secret = "secret_action"
        mock_confirm.return_value = mock_confirmed

        result = stripe_service.process_booking_payment(test_booking.id, "pm_action")

        assert result["status"] == "requires_action"
        assert result["client_secret"] == "secret_action"
        assert test_booking.payment_status != "authorized"

    @patch("stripe.Transfer.create")
    @patch("stripe.PaymentIntent.capture")
    def test_capture_payment_intent_returns_capture_details_without_top_up(
        self,
        mock_capture,
        mock_transfer,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        """Direct capture should return capture data but defer top-up to booking wrapper."""

        capture_payload = {
            "id": "pi_direct123",
            "status": "succeeded",
            "charges": {
                "data": [
                    {
                        "id": "ch_123",
                        "amount": 5960,
                        "transfer": "tr_primary",
                    }
                ]
            },
            "amount_received": 5960,
        }

        mock_capture.return_value = capture_payload

        # Mock Transfer.retrieve to return the transfer amount
        with patch("stripe.Transfer.retrieve") as mock_transfer_retrieve:
            # Create a mock that behaves like a Stripe object
            # The code uses: transfer.get("amount") if hasattr(transfer, "get") else ...
            mock_transfer_obj = MagicMock()
            mock_transfer_obj.get.side_effect = lambda key: 5230 if key == "amount" else None
            mock_transfer_obj.amount = 5230  # Instructor payout (5960 - 12% fee)
            mock_transfer_retrieve.return_value = mock_transfer_obj

            result = stripe_service.capture_payment_intent("pi_direct123")

        assert result["payment_intent"] == capture_payload
        assert result["amount_received"] == 5960
        assert result["transfer_id"] == "tr_primary"
        assert result["transfer_amount"] == 5230  # Instructor payout
        mock_transfer.assert_not_called()

    @patch("stripe.Transfer.retrieve")
    @patch("stripe.PaymentIntent.capture")
    def test_capture_payment_intent_returns_transfer_amount(
        self,
        mock_capture,
        mock_transfer_retrieve,
        stripe_service: StripeService,
    ) -> None:
        """Capture should return transfer_amount for 12-24h reversal correctness."""
        # With transfer_data[amount] architecture:
        # - amount_received: Total charge to student (e.g., $134.40 = 13440 cents)
        # - transfer_amount: Amount to instructor (e.g., $105.60 = 10560 cents)
        capture_payload = {
            "id": "pi_transfer_amount_test",
            "status": "succeeded",
            "charges": {
                "data": [
                    {
                        "id": "ch_456",
                        "amount": 13440,  # Total charge
                        "transfer": "tr_instructor",
                    }
                ]
            },
            "amount_received": 13440,
            "metadata": {"target_instructor_payout_cents": "10560"},
        }
        mock_capture.return_value = capture_payload

        # Transfer has the correct instructor payout
        # The code uses: transfer.get("amount") if hasattr(transfer, "get") else ...
        mock_transfer_obj = MagicMock()
        mock_transfer_obj.get.side_effect = lambda key: 10560 if key == "amount" else None
        mock_transfer_obj.amount = 10560
        mock_transfer_retrieve.return_value = mock_transfer_obj

        result = stripe_service.capture_payment_intent("pi_transfer_amount_test")

        assert result["amount_received"] == 13440  # Total charge
        assert result["transfer_amount"] == 10560  # Instructor payout
        assert result["transfer_id"] == "tr_instructor"

        # This is critical for 12-24h cancellation:
        # We should reverse transfer_amount (10560), NOT amount_received (13440)
        assert result["transfer_amount"] != result["amount_received"]

    @patch("stripe.PaymentIntent.capture")
    def test_capture_payment_intent_falls_back_to_amount(
        self, mock_capture, stripe_service: StripeService
    ) -> None:
        """Fallback to amount when amount_received is missing."""
        mock_capture.return_value = {
            "id": "pi_fallback",
            "status": "succeeded",
            "amount": 1234,
            "charges": {"data": []},
        }

        result = stripe_service.capture_payment_intent("pi_fallback")

        assert result["amount_received"] == 1234

    @patch("stripe.PaymentIntent.capture")
    def test_capture_payment_intent_stripe_error(
        self, mock_capture, stripe_service: StripeService
    ) -> None:
        """Stripe capture errors should raise ServiceException."""
        mock_capture.side_effect = stripe.error.InvalidRequestError(
            "This PaymentIntent has already been captured", param=None
        )

        with pytest.raises(ServiceException, match="Failed to capture payment"):
            stripe_service.capture_payment_intent("pi_already_captured")

    @patch("stripe.PaymentIntent.cancel")
    def test_cancel_payment_intent_updates_status(
        self, mock_cancel, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Cancel should update stored payment status when possible."""
        stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_cancel",
            amount=1000,
            application_fee=100,
            status="requires_capture",
        )

        mock_pi = MagicMock()
        mock_pi.status = "canceled"
        mock_cancel.return_value = mock_pi

        result = stripe_service.cancel_payment_intent("pi_cancel")

        assert result["payment_intent"] == mock_pi
        updated = stripe_service.payment_repository.get_payment_by_intent_id("pi_cancel")
        assert updated.status == "canceled"

    @patch("stripe.PaymentIntent.cancel")
    def test_cancel_payment_intent_stripe_error(
        self, mock_cancel, stripe_service: StripeService
    ) -> None:
        """Cancel errors should surface as ServiceException."""
        mock_cancel.side_effect = stripe.StripeError("cancel failed")

        with pytest.raises(ServiceException, match="Failed to cancel payment intent"):
            stripe_service.cancel_payment_intent("pi_missing")

    @patch("stripe.PaymentIntent.cancel")
    def test_cancel_payment_intent_update_status_failure(
        self, mock_cancel, stripe_service: StripeService
    ) -> None:
        mock_pi = MagicMock()
        mock_pi.status = "canceled"
        mock_cancel.return_value = mock_pi

        stripe_service.payment_repository.update_payment_status = MagicMock(
            side_effect=Exception("db down")
        )

        result = stripe_service.cancel_payment_intent("pi_cancel_err")

        assert result["payment_intent"] == mock_pi

    @patch("stripe.PaymentIntent.cancel")
    def test_cancel_payment_intent_unexpected_error(
        self, mock_cancel, stripe_service: StripeService
    ) -> None:
        mock_cancel.side_effect = Exception("boom")

        with pytest.raises(ServiceException, match="Failed to cancel payment intent"):
            stripe_service.cancel_payment_intent("pi_cancel_boom")

    # ========== refund_payment tests ==========

    @patch("stripe.Refund.create")
    def test_refund_payment_full_refund(
        self, mock_refund_create, stripe_service: StripeService
    ) -> None:
        """Full refund with reverse_transfer=True should work correctly."""
        mock_refund = MagicMock()
        mock_refund.id = "re_full_123"
        mock_refund.status = "succeeded"
        mock_refund.amount = 13440  # Full amount
        mock_refund_create.return_value = mock_refund

        result = stripe_service.refund_payment(
            payment_intent_id="pi_captured_123",
            reason="requested_by_customer",
            idempotency_key="refund_full_123",
        )

        assert result["refund_id"] == "re_full_123"
        assert result["status"] == "succeeded"
        assert result["amount_refunded"] == 13440
        assert result["payment_intent_id"] == "pi_captured_123"

        # Verify Stripe was called with correct params
        call_kwargs = mock_refund_create.call_args.kwargs
        assert call_kwargs["payment_intent"] == "pi_captured_123"
        assert call_kwargs["reverse_transfer"] is True
        assert call_kwargs["reason"] == "requested_by_customer"
        assert call_kwargs["idempotency_key"] == "refund_full_123"
        assert "amount" not in call_kwargs  # Full refund = no amount specified

    @patch("stripe.Refund.create")
    def test_refund_payment_partial_refund(
        self, mock_refund_create, stripe_service: StripeService
    ) -> None:
        """Partial refund should proportionally reverse transfer."""
        mock_refund = MagicMock()
        mock_refund.id = "re_partial_123"
        mock_refund.status = "succeeded"
        mock_refund.amount = 6720  # 50% refund
        mock_refund_create.return_value = mock_refund

        result = stripe_service.refund_payment(
            payment_intent_id="pi_captured_123",
            amount_cents=6720,
            reason="duplicate",
        )

        assert result["refund_id"] == "re_partial_123"
        assert result["amount_refunded"] == 6720

        # Verify amount was passed for partial refund
        call_kwargs = mock_refund_create.call_args.kwargs
        assert call_kwargs["amount"] == 6720

    @patch("stripe.Refund.create")
    def test_refund_payment_no_reverse_transfer(
        self, mock_refund_create, stripe_service: StripeService
    ) -> None:
        """Refund without reverse_transfer (platform absorbs)."""
        mock_refund = MagicMock()
        mock_refund.id = "re_no_reverse_123"
        mock_refund.status = "succeeded"
        mock_refund.amount = 5000
        mock_refund_create.return_value = mock_refund

        stripe_service.refund_payment(
            payment_intent_id="pi_no_reverse_123",
            amount_cents=5000,
            reverse_transfer=False,  # Platform absorbs the cost
        )

        call_kwargs = mock_refund_create.call_args.kwargs
        assert call_kwargs["reverse_transfer"] is False

    @patch("stripe.Refund.create")
    def test_refund_payment_invalid_reason_ignored(
        self, mock_refund_create, stripe_service: StripeService
    ) -> None:
        """Invalid reason should be ignored, not passed to Stripe."""
        mock_refund = MagicMock()
        mock_refund.id = "re_invalid_reason"
        mock_refund.status = "succeeded"
        mock_refund.amount = 5000
        mock_refund_create.return_value = mock_refund

        stripe_service.refund_payment(
            payment_intent_id="pi_invalid_reason",
            reason="invalid_reason_not_allowed",
        )

        call_kwargs = mock_refund_create.call_args.kwargs
        # Invalid reason should NOT be passed
        assert "reason" not in call_kwargs

    @patch("stripe.Refund.create")
    def test_refund_payment_stripe_error(
        self, mock_refund_create, stripe_service: StripeService
    ) -> None:
        """Stripe refund errors should raise ServiceException."""
        mock_refund_create.side_effect = stripe.StripeError("Refund failed")

        with pytest.raises(ServiceException, match="Failed to create refund"):
            stripe_service.refund_payment(payment_intent_id="pi_fail_refund")

    @patch("stripe.Refund.create")
    def test_refund_payment_unexpected_error(
        self, mock_refund_create, stripe_service: StripeService
    ) -> None:
        """Unexpected errors should raise ServiceException."""
        mock_refund_create.side_effect = Exception("Unexpected boom")

        with pytest.raises(ServiceException, match="Failed to create refund"):
            stripe_service.refund_payment(payment_intent_id="pi_boom_refund")

    # ========== end refund_payment tests ==========

    @patch("stripe.Transfer.create_reversal")
    def test_reverse_transfer_partial_reversal(
        self, mock_reversal, stripe_service: StripeService
    ) -> None:
        """Partial reversals should return without raising."""
        reversal = MagicMock()
        reversal.amount_reversed = 50
        reversal.failure_code = "balance_insufficient"
        mock_reversal.return_value = reversal

        result = stripe_service.reverse_transfer(
            transfer_id="tr_partial",
            amount_cents=100,
            reason="test",
            idempotency_key="rev_tr_partial",
        )

        assert result["reversal"] == reversal

    @patch("stripe.Transfer.create_reversal")
    def test_reverse_transfer_handles_metrics_error(
        self, mock_reversal, stripe_service: StripeService
    ) -> None:
        class BadReversal:
            @property
            def amount_reversed(self) -> int:
                raise Exception("metrics boom")

        mock_reversal.return_value = BadReversal()

        result = stripe_service.reverse_transfer(transfer_id="tr_metrics")

        assert "reversal" in result

    @patch("stripe.Transfer.create_reversal")
    def test_reverse_transfer_stripe_error(
        self, mock_reversal, stripe_service: StripeService
    ) -> None:
        """Stripe reversal errors should raise ServiceException."""
        mock_reversal.side_effect = stripe.StripeError("reversal failed")

        with pytest.raises(ServiceException, match="Failed to reverse transfer"):
            stripe_service.reverse_transfer(transfer_id="tr_fail", amount_cents=100)

    def test_process_booking_payment_booking_not_found(self, stripe_service: StripeService):
        """Test payment processing with non-existent booking."""
        with pytest.raises(ServiceException, match="Booking .* not found"):
            stripe_service.process_booking_payment("nonexistent_booking", "pm_card123")

    def test_process_booking_payment_instructor_not_set_up(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ):
        """Test payment processing when instructor account not set up."""
        _, profile, _ = test_instructor

        # Create customer but no connected account
        stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_student123")

        with pytest.raises(ServiceException, match="Instructor payment account not set up"):
            stripe_service.process_booking_payment(test_booking.id, "pm_card123")

    def test_process_booking_payment_missing_instructor_profile(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_missing_instructor"
        )

        with patch.object(
            stripe_service.instructor_repository, "get_by_user_id", return_value=None
        ):
            with pytest.raises(ServiceException, match="Instructor profile not found"):
                stripe_service.process_booking_payment(test_booking.id, "pm_card123")

    def test_process_booking_payment_credit_only_event_error(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_credit_only"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_credit_only", onboarding_completed=True
        )

        credit_context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=5000,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=5000,
            student_pay_cents=0,
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.10"),
        )
        stripe_service.build_charge_context = MagicMock(return_value=credit_context)
        stripe_service.payment_repository.create_payment_event = MagicMock(
            side_effect=Exception("event write failed")
        )

        result = stripe_service.process_booking_payment(test_booking.id, payment_method_id=None)

        assert result["status"] == "succeeded"
        assert test_booking.payment_status == "authorized"

    def test_process_booking_payment_card_error(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_card_error"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_card_error", onboarding_completed=True
        )

        stripe_service.create_payment_intent = MagicMock(
            return_value=MagicMock(
                stripe_payment_intent_id="pi_card_error", amount=5000, application_fee=500
            )
        )
        card_error = stripe.error.CardError(
            "Card declined",
            param="payment_method",
            code="card_declined",
            json_body={"error": {"message": "Card declined"}},
        )
        with patch("stripe.PaymentIntent.confirm", side_effect=card_error):
            result = stripe_service.process_booking_payment(test_booking.id, "pm_declined")

        assert result["success"] is False
        assert result["status"] == "auth_failed"
        assert test_booking.payment_status == "payment_method_required"

    def test_process_booking_payment_update_status_failure(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ) -> None:
        _, profile, _ = test_instructor
        stripe_service.payment_repository.create_customer_record(
            test_booking.student_id, "cus_status_fail"
        )
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_status_fail", onboarding_completed=True
        )

        stripe_service.create_payment_intent = MagicMock(
            return_value=MagicMock(
                stripe_payment_intent_id="pi_status_fail",
                amount=5000,
                application_fee=500,
            )
        )
        stripe_service.payment_repository.update_payment_status = MagicMock(
            side_effect=Exception("db down")
        )
        mock_confirmed = MagicMock(status="requires_capture", client_secret=None)

        with patch("stripe.PaymentIntent.confirm", return_value=mock_confirmed):
            result = stripe_service.process_booking_payment(test_booking.id, "pm_ok")

        assert result["status"] == "requires_capture"
        assert test_booking.payment_status == "authorized"

    def test_process_booking_payment_unexpected_exception(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        with patch.object(
            stripe_service.booking_repository, "get_by_id", side_effect=Exception("db down")
        ):
            with pytest.raises(ServiceException, match="Failed to process payment"):
                stripe_service.process_booking_payment(test_booking.id, "pm_any")

    # ========== Checkout Tests ==========

    def test_create_booking_checkout_requires_student(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_any",
            save_payment_method=False,
        )

        test_user._cached_is_student = False

        with pytest.raises(ServiceException, match="Only students can pay for bookings"):
            stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=_booking_service_stub(),
            )

    def test_create_booking_checkout_booking_not_found(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        payload = CreateCheckoutRequest(
            booking_id="missing_booking",
            payment_method_id="pm_any",
            save_payment_method=False,
        )

        test_user._cached_is_student = True

        with pytest.raises(ServiceException, match="Booking not found"):
            stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=_booking_service_stub(),
            )

    def test_create_booking_checkout_wrong_student(
        self, stripe_service: StripeService, test_booking: Booking, db: Session
    ) -> None:
        other_user = User(
            id=str(ulid.ULID()),
            email=f"other_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Other",
            last_name="Student",
            zip_code="10001",
        )
        db.add(other_user)
        db.flush()
        other_user._cached_is_student = True

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_any",
            save_payment_method=False,
        )

        with pytest.raises(ServiceException, match="only pay for your own bookings"):
            stripe_service.create_booking_checkout(
                current_user=other_user,
                payload=payload,
                booking_service=_booking_service_stub(),
            )

    def test_create_booking_checkout_invalid_status(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.CANCELLED

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_any",
            save_payment_method=False,
        )

        with pytest.raises(ServiceException, match="Cannot process payment for booking with status"):
            stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=_booking_service_stub(),
            )

    def test_create_booking_checkout_already_paid(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_paid",
            amount=5000,
            application_fee=500,
            status="succeeded",
        )

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_any",
            save_payment_method=False,
        )

        with pytest.raises(ServiceException, match="already been paid"):
            stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=_booking_service_stub(),
            )

    def test_create_booking_checkout_save_payment_method_requires_id(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id=None,
            save_payment_method=True,
        )

        with pytest.raises(ServiceException, match="Payment method is required"):
            stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=_booking_service_stub(),
            )

    def test_create_booking_checkout_success_requires_capture(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.PENDING
        booking_service = _booking_service_stub()

        payment_result = {
            "success": True,
            "payment_intent_id": "pi_capture",
            "status": "requires_capture",
            "amount": 5000,
            "application_fee": 500,
            "client_secret": None,
        }

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_capture",
            save_payment_method=True,
            requested_credit_cents=0,
        )

        with (
            patch.object(stripe_service, "process_booking_payment", return_value=payment_result) as mock_process,
            patch.object(stripe_service, "save_payment_method") as mock_save,
        ):
            response = stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=booking_service,
            )

        mock_save.assert_called_once_with(
            user_id=test_user.id,
            payment_method_id="pm_capture",
            set_as_default=False,
        )
        mock_process.assert_called_once_with(
            test_booking.id,
            "pm_capture",
            0,
        )

        assert response.success is True
        assert response.status == "requires_capture"
        assert response.requires_action is False
        assert response.client_secret is None
        assert test_booking.status == "CONFIRMED"
        assert test_booking.payment_status == "authorized"

        booking_service.repository.flush.assert_called_once()
        booking_service.invalidate_booking_cache.assert_called_once_with(test_booking)
        booking_service.system_message_service.create_booking_created_message.assert_called_once()

        _, message_kwargs = booking_service.system_message_service.create_booking_created_message.call_args
        assert message_kwargs["service_name"] == test_booking.instructor_service.name

    def test_create_booking_checkout_sets_scheduled_payment_status(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.PENDING
        booking_service = _booking_service_stub()

        payment_result = {
            "success": True,
            "payment_intent_id": "pi_scheduled",
            "status": "scheduled",
            "amount": 5000,
            "application_fee": 500,
            "client_secret": None,
        }

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_scheduled",
            save_payment_method=False,
        )

        with (
            patch.object(stripe_service, "process_booking_payment", return_value=payment_result),
            patch.object(
                stripe_service.booking_repository,
                "get_by_id_for_update",
                return_value=test_booking,
            ),
        ):
            response = stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=booking_service,
            )

        assert response.status == "scheduled"
        assert test_booking.payment_status == PaymentStatus.SCHEDULED.value

    def test_create_booking_checkout_invalid_state_after_payment_refund(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.PENDING
        booking_service = _booking_service_stub()

        payment_result = {
            "success": True,
            "payment_intent_id": "pi_capture",
            "status": "requires_capture",
            "amount": 5000,
            "application_fee": 500,
            "client_secret": None,
        }

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_capture",
            save_payment_method=False,
        )

        invalid_booking = MagicMock(spec=Booking)
        invalid_booking.status = BookingStatus.COMPLETED.value

        with (
            patch.object(stripe_service, "process_booking_payment", return_value=payment_result),
            patch.object(
                stripe_service.booking_repository,
                "get_by_id_for_update",
                return_value=invalid_booking,
            ),
            patch.object(stripe_service, "_void_or_refund_payment") as mock_void,
        ):
            with pytest.raises(ServiceException, match="unexpected state"):
                stripe_service.create_booking_checkout(
                    current_user=test_user,
                    payload=payload,
                    booking_service=booking_service,
                )

        mock_void.assert_called_once_with("pi_capture")

    def test_create_booking_checkout_suppresses_notification_errors(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.PENDING
        booking_service = _booking_service_stub()
        booking_service.invalidate_booking_cache.side_effect = Exception("cache down")
        booking_service.system_message_service.create_booking_created_message.side_effect = Exception(
            "message fail"
        )

        payment_result = {
            "success": True,
            "payment_intent_id": "pi_capture",
            "status": "requires_capture",
            "amount": 5000,
            "application_fee": 500,
            "client_secret": None,
        }

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_capture",
            save_payment_method=False,
        )

        with patch.object(stripe_service, "process_booking_payment", return_value=payment_result):
            response = stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=booking_service,
            )

        assert response.success is True
        booking_service.invalidate_booking_cache.assert_called_once_with(test_booking)
        booking_service.system_message_service.create_booking_created_message.assert_called_once()

    def test_create_booking_checkout_requires_action_returns_client_secret(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.PENDING
        booking_service = _booking_service_stub()

        payment_result = {
            "success": True,
            "payment_intent_id": "pi_action",
            "status": "requires_action",
            "amount": 5000,
            "application_fee": 500,
            "client_secret": "secret_action",
        }

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_action",
            save_payment_method=False,
        )

        with patch.object(stripe_service, "process_booking_payment", return_value=payment_result):
            response = stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=booking_service,
            )

        assert response.requires_action is True
        assert response.client_secret == "secret_action"
        assert test_booking.status == BookingStatus.PENDING
        booking_service.repository.flush.assert_not_called()
        booking_service.system_message_service.create_booking_created_message.assert_not_called()

    def test_create_booking_checkout_notification_error_suppressed(
        self, stripe_service: StripeService, test_booking: Booking, test_user: User
    ) -> None:
        test_user._cached_is_student = True
        test_booking.status = BookingStatus.PENDING.value
        booking_service = _booking_service_stub()
        booking_service.send_booking_notifications_after_confirmation.side_effect = Exception(
            "notify failed"
        )

        payment_result = {
            "success": True,
            "payment_intent_id": "pi_capture",
            "status": "requires_capture",
            "amount": 5000,
            "application_fee": 500,
            "client_secret": None,
        }

        payload = CreateCheckoutRequest(
            booking_id=test_booking.id,
            payment_method_id="pm_capture",
            save_payment_method=False,
        )

        with (
            patch.object(stripe_service, "process_booking_payment", return_value=payment_result),
            patch.object(
                stripe_service.booking_repository,
                "get_by_id_for_update",
                return_value=test_booking,
            ),
        ):
            response = stripe_service.create_booking_checkout(
                current_user=test_user,
                payload=payload,
                booking_service=booking_service,
            )

        assert response.success is True
        booking_service.send_booking_notifications_after_confirmation.assert_called_once_with(
            test_booking.id
        )

    # ========== Payment Method Management Tests ==========

    @patch("stripe.PaymentMethod.attach")
    @patch("stripe.PaymentMethod.retrieve")
    def test_save_payment_method_success(
        self, mock_retrieve, mock_attach, stripe_service: StripeService, test_user: User
    ):
        """Test saving payment method."""
        # Create customer first
        stripe_service.payment_repository.create_customer_record(test_user.id, "cus_test123")

        # Mock Stripe response - payment method not attached yet
        mock_pm = MagicMock()
        mock_pm.card.last4 = "4242"
        mock_pm.card.brand = "visa"
        mock_pm.customer = None  # Not attached to any customer
        mock_retrieve.return_value = mock_pm

        # Mock attachment result
        mock_pm_attached = MagicMock()
        mock_pm_attached.card = mock_pm.card
        mock_pm_attached.customer = "cus_test123"
        mock_attach.return_value = mock_pm_attached

        # Save payment method
        payment_method = stripe_service.save_payment_method(
            user_id=test_user.id, payment_method_id="pm_test123", set_as_default=True
        )

        # Verify Stripe API calls
        mock_retrieve.assert_called_once_with("pm_test123")
        mock_attach.assert_called_once_with("pm_test123", customer="cus_test123")

        # Verify database record
        assert payment_method.user_id == test_user.id
        assert payment_method.stripe_payment_method_id == "pm_test123"
        assert payment_method.last4 == "4242"
        assert payment_method.brand == "visa"
        assert payment_method.is_default is True

    @patch("stripe.PaymentMethod.retrieve")
    def test_save_payment_method_different_customer(
        self, mock_retrieve, stripe_service: StripeService, test_user: User
    ) -> None:
        """Saving a payment method from another customer should fail."""
        stripe_service.payment_repository.create_customer_record(test_user.id, "cus_local")

        mock_pm = MagicMock()
        mock_pm.customer = "cus_other"
        mock_pm.card.last4 = "4242"
        mock_pm.card.brand = "visa"
        mock_retrieve.return_value = mock_pm

        with pytest.raises(ServiceException, match="already in use by another account"):
            stripe_service.save_payment_method(
                user_id=test_user.id,
                payment_method_id="pm_other",
                set_as_default=False,
            )

    @patch("stripe.PaymentMethod.retrieve")
    def test_save_payment_method_card_error(
        self, mock_retrieve, stripe_service: StripeService, test_user: User
    ) -> None:
        """Card errors should surface as ServiceException."""
        stripe_service.payment_repository.create_customer_record(test_user.id, "cus_card_error")

        card_error = stripe.error.CardError(
            "Card declined",
            param="payment_method",
            code="card_declined",
            json_body={"error": {"message": "Card declined"}},
        )
        mock_retrieve.side_effect = card_error

        with pytest.raises(ServiceException, match="Card declined"):
            stripe_service.save_payment_method(
                user_id=test_user.id,
                payment_method_id="pm_declined",
                set_as_default=False,
            )

    def test_save_payment_method_existing_sets_default(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        existing = stripe_service.payment_repository.save_payment_method(
            test_user.id, "pm_existing", "4242", "visa", is_default=False
        )

        stripe_service.payment_repository.set_default_payment_method = MagicMock()

        payment_method = stripe_service.save_payment_method(
            user_id=test_user.id, payment_method_id="pm_existing", set_as_default=True
        )

        stripe_service.payment_repository.set_default_payment_method.assert_called_once_with(
            existing.id, test_user.id
        )
        assert payment_method.id == existing.id

    @patch("stripe.PaymentMethod.retrieve")
    def test_save_payment_method_already_attached(
        self, mock_retrieve, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.payment_repository.create_customer_record(test_user.id, "cus_attached")

        mock_pm = MagicMock()
        mock_pm.customer = "cus_attached"
        mock_pm.card.last4 = "1111"
        mock_pm.card.brand = "visa"
        mock_retrieve.return_value = mock_pm

        with patch("stripe.PaymentMethod.attach") as mock_attach:
            payment_method = stripe_service.save_payment_method(
                user_id=test_user.id,
                payment_method_id="pm_attached",
                set_as_default=False,
            )

        mock_attach.assert_not_called()
        assert payment_method.stripe_payment_method_id == "pm_attached"

    @patch("stripe.PaymentMethod.retrieve")
    def test_save_payment_method_stripe_error(
        self, mock_retrieve, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.payment_repository.create_customer_record(test_user.id, "cus_stripe_error")
        mock_retrieve.side_effect = stripe.StripeError("stripe down")

        with pytest.raises(ServiceException, match="Failed to save payment method"):
            stripe_service.save_payment_method(
                user_id=test_user.id,
                payment_method_id="pm_fail",
                set_as_default=False,
            )

    def test_save_payment_method_unexpected_error(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        with patch.object(
            stripe_service, "get_or_create_customer", side_effect=Exception("boom")
        ):
            with pytest.raises(ServiceException, match="Failed to save payment method"):
                stripe_service.save_payment_method(
                    user_id=test_user.id,
                    payment_method_id="pm_boom",
                    set_as_default=False,
                )

    def test_get_user_payment_methods(self, stripe_service: StripeService, test_user: User):
        """Test getting user payment methods."""
        # Create payment methods
        stripe_service.payment_repository.save_payment_method(test_user.id, "pm_test1", "4242", "visa", is_default=True)
        stripe_service.payment_repository.save_payment_method(
            test_user.id, "pm_test2", "5555", "mastercard", is_default=False
        )

        # Get methods
        methods = stripe_service.get_user_payment_methods(test_user.id)

        assert len(methods) == 2
        # Default should be first
        assert methods[0].is_default is True
        assert methods[0].brand == "visa"

    def test_get_user_payment_methods_error(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.payment_repository.get_payment_methods_by_user = MagicMock(
            side_effect=Exception("db down")
        )

        with pytest.raises(ServiceException, match="Failed to get payment methods"):
            stripe_service.get_user_payment_methods(test_user.id)

    def test_delete_payment_method_success(self, stripe_service: StripeService, test_user: User):
        """Test deleting payment method."""
        # Create payment method
        method = stripe_service.payment_repository.save_payment_method(test_user.id, "pm_test123", "4242", "visa")

        # Delete method
        success = stripe_service.delete_payment_method(method.id, test_user.id)

        assert success is True

        # Verify deletion
        methods = stripe_service.get_user_payment_methods(test_user.id)
        assert len(methods) == 0

    @patch("stripe.PaymentMethod.detach")
    def test_delete_payment_method_detach_error(
        self, mock_detach, stripe_service: StripeService, test_user: User
    ) -> None:
        mock_detach.side_effect = stripe.StripeError("detach failed")
        stripe_service.payment_repository.save_payment_method(
            test_user.id, "pm_detach_err", "4242", "visa"
        )

        success = stripe_service.delete_payment_method("pm_detach_err", test_user.id)

        assert success is True

    def test_delete_payment_method_error(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.payment_repository.delete_payment_method = MagicMock(
            side_effect=Exception("db down")
        )

        with pytest.raises(ServiceException, match="Failed to delete payment method"):
            stripe_service.delete_payment_method("pm_missing", test_user.id)

    # ========== Identity & Credits Tests ==========

    @patch("stripe.identity.VerificationSession.create")
    def test_create_identity_verification_session_success(
        self, mock_create, stripe_service: StripeService, test_user: User
    ) -> None:
        """Identity session should return client secret and ID."""
        stripe_service.stripe_configured = True
        mock_session = MagicMock()
        mock_session.id = "vs_123"
        mock_session.client_secret = "secret_123"
        mock_create.return_value = mock_session

        result = stripe_service.create_identity_verification_session(
            user_id=test_user.id, return_url="https://app.test/return"
        )

        assert result["verification_session_id"] == "vs_123"
        assert result["client_secret"] == "secret_123"

    @patch("stripe.identity.VerificationSession.create")
    def test_create_identity_verification_session_stripe_error(
        self, mock_create, stripe_service: StripeService, test_user: User
    ) -> None:
        """Stripe errors should surface as ServiceException."""
        stripe_service.stripe_configured = True
        mock_create.side_effect = stripe.error.APIConnectionError("network down")

        with pytest.raises(ServiceException, match="Failed to start identity verification"):
            stripe_service.create_identity_verification_session(
                user_id=test_user.id, return_url="https://app.test/return"
            )

    def test_create_identity_verification_session_user_not_found(
        self, stripe_service: StripeService
    ) -> None:
        stripe_service.stripe_configured = True

        with pytest.raises(ServiceException, match="User not found for identity verification"):
            stripe_service.create_identity_verification_session(
                user_id="missing_user", return_url="https://app.test/return"
            )

    @patch("stripe.identity.VerificationSession.create")
    def test_create_identity_verification_session_missing_client_secret(
        self, mock_create, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.stripe_configured = True
        mock_session = MagicMock()
        mock_session.id = "vs_missing_secret"
        mock_session.client_secret = None
        mock_create.return_value = mock_session

        with pytest.raises(ServiceException, match="Failed to create identity verification session"):
            stripe_service.create_identity_verification_session(
                user_id=test_user.id, return_url="https://app.test/return"
            )

    def test_create_identity_verification_session_unexpected_error(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.stripe_configured = True

        with patch.object(
            stripe_service.user_repository, "get_by_id", side_effect=Exception("db down")
        ):
            with pytest.raises(ServiceException, match="Failed to start identity verification"):
                stripe_service.create_identity_verification_session(
                    user_id=test_user.id, return_url="https://app.test/return"
                )

    @patch("stripe.identity.VerificationSession.list")
    def test_get_latest_identity_status_found(
        self, mock_list, stripe_service: StripeService, test_user: User
    ) -> None:
        """Return the latest identity session for a user."""
        stripe_service.stripe_configured = True
        session_old = MagicMock()
        session_old.id = "vs_old"
        session_old.status = "processing"
        session_old.created = 10
        session_old.metadata = {"user_id": test_user.id}

        session_new = MagicMock()
        session_new.id = "vs_new"
        session_new.status = "verified"
        session_new.created = 20
        session_new.metadata = {"user_id": test_user.id}

        mock_list.return_value = {"data": [session_old, session_new]}

        result = stripe_service.get_latest_identity_status(test_user.id)

        assert result["status"] == "verified"
        assert result["id"] == "vs_new"
        assert result["created"] == 20

    @patch("stripe.identity.VerificationSession.list")
    def test_get_latest_identity_status_not_found(
        self, mock_list, stripe_service: StripeService
    ) -> None:
        stripe_service.stripe_configured = True
        mock_list.return_value = {"data": []}

        result = stripe_service.get_latest_identity_status("user_missing")

        assert result["status"] == "not_found"

    @patch("stripe.identity.VerificationSession.list")
    def test_get_latest_identity_status_skips_bad_metadata(
        self, mock_list, stripe_service: StripeService
    ) -> None:
        stripe_service.stripe_configured = True

        class BadSession:
            @property
            def metadata(self) -> dict:
                raise Exception("metadata boom")

        mock_list.return_value = {"data": [BadSession()]}

        result = stripe_service.get_latest_identity_status("user_missing")

        assert result["status"] == "not_found"

    @patch("stripe.identity.VerificationSession.list")
    def test_get_latest_identity_status_stripe_error(
        self, mock_list, stripe_service: StripeService
    ) -> None:
        stripe_service.stripe_configured = True
        mock_list.side_effect = stripe.StripeError("stripe down")

        with pytest.raises(ServiceException, match="Failed to get identity status"):
            stripe_service.get_latest_identity_status("user_missing")

    @patch("stripe.identity.VerificationSession.list")
    def test_get_latest_identity_status_unexpected_error(
        self, mock_list, stripe_service: StripeService
    ) -> None:
        stripe_service.stripe_configured = True
        mock_list.side_effect = Exception("boom")

        with pytest.raises(ServiceException, match="Failed to get identity status"):
            stripe_service.get_latest_identity_status("user_missing")

    def test_get_user_credit_balance_returns_earliest_expiry(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        """Earliest credit expiration should be surfaced in the balance."""
        now = datetime.now(timezone.utc)
        stripe_service.payment_repository.create_platform_credit(
            user_id=test_user.id,
            amount_cents=500,
            reason="test",
            expires_at=now + timedelta(days=10),
        )
        stripe_service.payment_repository.create_platform_credit(
            user_id=test_user.id,
            amount_cents=700,
            reason="test",
            expires_at=now + timedelta(days=5),
        )

        balance = stripe_service.get_user_credit_balance(user=test_user)

        assert balance.available == pytest.approx(12.0)
        assert balance.expires_at is not None

    def test_get_user_credit_balance_handles_lookup_error(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        stripe_service.payment_repository.get_available_credits = MagicMock(
            side_effect=Exception("db down")
        )

        balance = stripe_service.get_user_credit_balance(user=test_user)

        assert balance.expires_at is None

    def test_get_user_transaction_history_includes_summary_fields(
        self, stripe_service: StripeService, test_booking: Booking
    ) -> None:
        """Transaction history should include pricing summary fields."""
        stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_hist",
            amount=6000,
            application_fee=600,
            status="succeeded",
        )

        student = stripe_service.user_repository.get_by_id(test_booking.student_id)
        assert student is not None
        history = stripe_service.get_user_transaction_history(user=student, limit=10, offset=0)

        assert len(history) == 1
        entry = history[0]
        assert entry.booking_id == test_booking.id
        assert entry.status == "succeeded"
        assert entry.total_paid >= entry.lesson_amount

    def test_get_user_transaction_history_skips_missing_and_limits(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        booking = SimpleNamespace(
            id="booking_hist",
            service_name="History Lesson",
            booking_date=datetime.now().date(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            duration_minutes=60,
            hourly_rate=50.0,
            instructor=SimpleNamespace(first_name="Ingrid", last_name=""),
        )
        payment_missing = MagicMock(booking=None)
        payment_valid = MagicMock(
            booking=booking,
            id="pay_1",
            status="succeeded",
            created_at=datetime.now(timezone.utc),
        )
        payment_duplicate = MagicMock(
            booking=booking,
            id="pay_2",
            status="succeeded",
            created_at=datetime.now(timezone.utc),
        )

        stripe_service.payment_repository.get_user_payment_history = MagicMock(
            return_value=[payment_missing, payment_valid, payment_duplicate]
        )
        summary = SimpleNamespace(
            lesson_amount=50.0,
            service_fee=5.0,
            credit_applied=0.0,
            tip_amount=0.0,
            tip_paid=0.0,
            tip_status="none",
            total_paid=55.0,
        )

        with patch("app.services.stripe_service.build_student_payment_summary", return_value=summary):
            history = stripe_service.get_user_transaction_history(user=test_user, limit=1, offset=0)

        assert len(history) == 1
        assert history[0].instructor_name == "Ingrid"

    def test_get_user_transaction_history_skips_failed_summary(
        self, stripe_service: StripeService
    ) -> None:
        student = MagicMock(id="student_1")
        instructor = MagicMock(first_name="Alex", last_name="")
        bad_booking = MagicMock(
            id="bk_bad",
            service_name="Service",
            booking_date=datetime.now().date(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            duration_minutes=60,
            hourly_rate=50.0,
            instructor=instructor,
        )
        good_booking = MagicMock(
            id="bk_good",
            service_name="Service",
            booking_date=datetime.now().date(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            duration_minutes=60,
            hourly_rate=50.0,
            instructor=instructor,
        )
        bad_payment = MagicMock(
            id="pi_bad",
            booking=bad_booking,
            status="succeeded",
            created_at=datetime.now(timezone.utc),
        )
        good_payment = MagicMock(
            id="pi_good",
            booking=good_booking,
            status="succeeded",
            created_at=datetime.now(timezone.utc),
        )
        summary = MagicMock(
            lesson_amount=50.0,
            service_fee=0.0,
            credit_applied=0.0,
            tip_amount=0.0,
            tip_paid=0.0,
            tip_status=None,
            total_paid=50.0,
        )

        with (
            patch.object(
                stripe_service.payment_repository,
                "get_user_payment_history",
                return_value=[bad_payment, good_payment],
            ),
            patch(
                "app.services.stripe_service.build_student_payment_summary",
                side_effect=[Exception("boom"), summary],
            ),
        ):
            history = stripe_service.get_user_transaction_history(
                user=student, limit=10, offset=0
            )

        assert len(history) == 1
        assert history[0].instructor_name == "Alex"

    def test_mock_payment_response(self, stripe_service: StripeService) -> None:
        result = stripe_service._mock_payment_response("booking_mock", 1200)

        assert result["payment_intent_id"] == "mock_pi_booking_mock"
        assert result["amount"] == 12.0

    def test_top_up_from_pi_metadata_returns_top_up(self) -> None:
        pi = SimpleNamespace(
            metadata={
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "2000",
            },
            amount=5000,
        )

        assert StripeService._top_up_from_pi_metadata(pi) == 3500

    def test_top_up_from_pi_metadata_returns_zero_when_no_top_up(self) -> None:
        pi = SimpleNamespace(
            metadata={
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "0",
            },
            amount=8500,
        )

        assert StripeService._top_up_from_pi_metadata(pi) == 0

    def test_top_up_from_pi_metadata_returns_none_without_metadata(self) -> None:
        pi = SimpleNamespace(metadata=None, amount=5000)

        assert StripeService._top_up_from_pi_metadata(pi) is None

    def test_top_up_from_pi_metadata_returns_none_on_negative_credit(self) -> None:
        pi = SimpleNamespace(
            metadata={
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "-100",
            },
            amount=5000,
        )

        assert StripeService._top_up_from_pi_metadata(pi) is None

    def test_top_up_from_pi_metadata_returns_none_when_amount_missing(self) -> None:
        pi = SimpleNamespace(
            metadata={
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "0",
            },
            amount=None,
        )

        assert StripeService._top_up_from_pi_metadata(pi) is None

    def test_top_up_from_pi_metadata_returns_none_on_invalid_metadata(self) -> None:
        pi = SimpleNamespace(
            metadata={
                "base_price_cents": "not-a-number",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "0",
            },
            amount=5000,
        )

        assert StripeService._top_up_from_pi_metadata(pi) is None

    def test_top_up_from_pi_metadata_returns_none_on_invalid_amount(self) -> None:
        pi = SimpleNamespace(
            metadata={
                "base_price_cents": "10000",
                "platform_fee_cents": "1500",
                "student_fee_cents": "1200",
                "applied_credit_cents": "0",
            },
            amount="not-a-number",
        )

        assert StripeService._top_up_from_pi_metadata(pi) is None

    # ========== Error Handling Tests ==========

    def test_check_stripe_configured_raises_when_missing(
        self, stripe_service: StripeService
    ) -> None:
        stripe_service.stripe_configured = False

        with pytest.raises(ServiceException, match="Stripe service not configured"):
            stripe_service._check_stripe_configured()

    @patch("stripe.Customer.create")
    def test_create_customer_auth_error_uses_mock(
        self, mock_create, stripe_service: StripeService, test_user: User
    ) -> None:
        """Authentication errors should fall back to mock customers when unconfigured."""
        stripe_service.stripe_configured = False
        mock_create.side_effect = stripe.error.AuthenticationError("No API key provided")

        customer = stripe_service.create_customer(
            user_id=test_user.id,
            email=test_user.email,
            name=f"{test_user.first_name} {test_user.last_name}",
        )

        assert customer.stripe_customer_id == f"mock_cust_{test_user.id}"

    @patch("stripe.PaymentIntent.capture")
    def test_capture_payment_intent_rate_limit_error(
        self, mock_capture, stripe_service: StripeService
    ) -> None:
        """Rate limit errors should raise ServiceException."""
        mock_capture.side_effect = stripe.error.RateLimitError("rate limited")

        with pytest.raises(ServiceException, match="Failed to capture payment"):
            stripe_service.capture_payment_intent("pi_rate_limited")

    @patch("stripe.Customer.create")
    def test_service_exception_handling(self, mock_create, stripe_service: StripeService, test_user: User):
        """Test service exception handling."""
        # Mock database error by using invalid user ID
        mock_create.side_effect = Exception("Database error")

        with pytest.raises(ServiceException):
            stripe_service.create_customer(user_id="invalid_user_id", email=test_user.email, name="Test User")

    def test_transaction_rollback_on_error(self, stripe_service: StripeService, test_user: User):
        """Test transaction rollback on service errors."""
        # This test verifies that database changes are rolled back on errors
        initial_count = len(stripe_service.payment_repository.get_payment_methods_by_user(test_user.id))

        with pytest.raises(ServiceException):
            with stripe_service.transaction():
                # Create a payment method
                stripe_service.payment_repository.save_payment_method(test_user.id, "pm_test123", "4242", "visa")
                # Force an error
                raise ServiceException("Test error")

        # Verify no payment method was saved due to rollback
        final_count = len(stripe_service.payment_repository.get_payment_methods_by_user(test_user.id))
        assert final_count == initial_count

    def test_earnings_export_uses_founding_rate(
        self,
        stripe_service: StripeService,
        db: Session,
        test_instructor: tuple[User, InstructorProfile, InstructorService],
        monkeypatch,
    ) -> None:
        """Founding instructors should use the founding rate in earnings exports."""
        instructor_user, profile, _service = test_instructor
        profile.is_founding_instructor = True
        db.flush()

        rows = [
            {
                "lesson_date": datetime.now(timezone.utc).date(),
                "student_name": "Student",
                "service_name": "Lesson",
                "duration_minutes": 60,
                "hourly_rate": Decimal("100.00"),
                "payment_amount_cents": 10000,
                "application_fee_cents": 800,
                "status": "succeeded",
                "payment_id": "pay_123",
            }
        ]

        monkeypatch.setattr(
            stripe_service.payment_repository,
            "get_instructor_earnings_for_export",
            lambda instructor_id, start_date=None, end_date=None: rows,
        )

        result = stripe_service._build_earnings_export_rows(
            instructor_id=instructor_user.id,
            start_date=None,
            end_date=None,
        )

        assert result[0]["platform_fee_cents"] == 800

    def test_earnings_export_missing_profile_raises(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        with patch.object(
            stripe_service.instructor_repository, "get_by_user_id", return_value=None
        ):
            with pytest.raises(ServiceException, match="Instructor profile not found"):
                stripe_service._build_earnings_export_rows(
                    instructor_id=test_user.id,
                    start_date=None,
                    end_date=None,
                )

    def test_generate_earnings_csv_formats_rows(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        rows = [
            {
                "lesson_date": date.today(),
                "student_name": "Student A",
                "service_name": "Lesson",
                "duration_minutes": 60,
                "lesson_price_cents": 10000,
                "platform_fee_cents": 1500,
                "net_earnings_cents": 8500,
                "status": "Paid",
                "payment_id": "pay_123",
            }
        ]

        with patch.object(
            stripe_service, "_build_earnings_export_rows", return_value=rows
        ):
            csv_data = stripe_service.generate_earnings_csv(instructor_id=test_user.id)

        assert "Lesson Price" in csv_data
        assert "Student A" in csv_data
        assert "pay_123" in csv_data

    def test_generate_earnings_pdf_outputs_bytes(
        self, stripe_service: StripeService, test_user: User
    ) -> None:
        rows = [
            {
                "lesson_date": date.today(),
                "student_name": "Student A",
                "service_name": "Lesson",
                "duration_minutes": 60,
                "lesson_price_cents": 10000,
                "platform_fee_cents": 1500,
                "net_earnings_cents": 8500,
                "status": "Paid",
                "payment_id": "pay_123",
            }
        ]

        with patch.object(
            stripe_service, "_build_earnings_export_rows", return_value=rows
        ):
            pdf_bytes = stripe_service.generate_earnings_pdf(
                instructor_id=test_user.id,
                start_date=date.today(),
                end_date=date.today(),
            )

        assert pdf_bytes.startswith(b"%PDF-")
        assert b"Earnings Report" in pdf_bytes

    def test_generate_earnings_pdf_no_rows(self, stripe_service: StripeService, test_user: User) -> None:
        with patch.object(
            stripe_service, "_build_earnings_export_rows", return_value=[]
        ):
            pdf_bytes = stripe_service.generate_earnings_pdf(instructor_id=test_user.id)

        assert b"No earnings found" in pdf_bytes
