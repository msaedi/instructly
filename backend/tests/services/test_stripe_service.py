"""
Tests for StripeService.

Comprehensive test suite for Stripe marketplace payment processing,
including customer management, connected accounts, payment processing,
and webhook handling.
"""

from datetime import datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import stripe
import ulid

from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.stripe_service import ChargeContext, StripeService


class TestStripeService:
    """Test suite for StripeService."""

    @pytest.fixture
    def stripe_service(self, db: Session) -> StripeService:
        """Create StripeService instance."""
        return StripeService(db)

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
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(14, 0),  # 2:00 PM
            end_time=time(15, 0),  # 3:00 PM
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()
        return booking

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
        mock_retrieve.return_value = mock_account

        # Check status
        status = stripe_service.check_account_status(profile.id)

        # Verify result
        assert status["has_account"] is True
        assert status["onboarding_completed"] is True
        assert status["can_accept_payments"] is True
        assert status["details_submitted"] is True

    def test_check_account_status_no_account(self, stripe_service: StripeService, test_instructor: tuple):
        """Test checking account status with no account."""
        _, profile, _ = test_instructor

        status = stripe_service.check_account_status(profile.id)

        assert status["has_account"] is False
        assert status["onboarding_completed"] is False
        assert status["can_accept_payments"] is False

    # ========== Payment Processing Tests ==========

    @patch("app.services.pricing_service.PricingService.compute_booking_pricing")
    def test_build_charge_context_with_requested_credit(
        self,
        mock_pricing,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        """Requested credits should be locked and reflected in the charge context."""

        mock_pricing.return_value = {
            "base_price_cents": 10000,
            "student_fee_cents": 1200,
            "instructor_commission_cents": 1500,
            "target_instructor_payout_cents": 8500,
            "credit_applied_cents": 700,
            "student_pay_cents": 8500,
            "application_fee_cents": 2000,
            "top_up_transfer_cents": 0,
            "instructor_tier_pct": 0.12,
        }

        apply_mock = MagicMock(return_value={"applied_cents": 700})
        stripe_service.payment_repository.apply_credits_for_booking = apply_mock
        stripe_service.payment_repository.get_applied_credit_cents_for_booking = MagicMock()

        context = stripe_service.build_charge_context(
            booking_id=test_booking.id, requested_credit_cents=900
        )

        apply_mock.assert_called_once_with(
            user_id=test_booking.student_id,
            booking_id=test_booking.id,
            amount_cents=900,
        )
        stripe_service.payment_repository.get_applied_credit_cents_for_booking.assert_not_called()
        mock_pricing.assert_called_once_with(
            booking_id=test_booking.id,
            applied_credit_cents=700,
            persist=True,
        )

        assert context.applied_credit_cents == 700
        assert context.application_fee_cents == 2000
        assert context.student_pay_cents == 8500
        assert context.instructor_tier_pct == Decimal("0.12")

    @patch("app.services.pricing_service.PricingService.compute_booking_pricing")
    def test_build_charge_context_without_requested_credit(
        self,
        mock_pricing,
        stripe_service: StripeService,
        test_booking: Booking,
    ) -> None:
        """When credits were already locked, reuse the stored amount."""

        mock_pricing.return_value = {
            "base_price_cents": 9000,
            "student_fee_cents": 1080,
            "instructor_commission_cents": 1200,
            "target_instructor_payout_cents": 7800,
            "credit_applied_cents": 500,
            "student_pay_cents": 9580,
            "application_fee_cents": 1780,
            "top_up_transfer_cents": 250,
            "instructor_tier_pct": 0.1,
        }

        apply_mock = MagicMock()
        stripe_service.payment_repository.apply_credits_for_booking = apply_mock
        stripe_service.payment_repository.get_applied_credit_cents_for_booking = MagicMock(
            return_value=500
        )

        context = stripe_service.build_charge_context(
            booking_id=test_booking.id, requested_credit_cents=None
        )

        apply_mock.assert_not_called()
        stripe_service.payment_repository.get_applied_credit_cents_for_booking.assert_called_once_with(
            test_booking.id
        )
        mock_pricing.assert_called_once_with(
            booking_id=test_booking.id,
            applied_credit_cents=500,
            persist=True,
        )

        assert context.applied_credit_cents == 500
        assert context.top_up_transfer_cents == 250
        assert context.instructor_tier_pct == Decimal("0.1")

    @patch("stripe.PaymentIntent.create")
    def test_create_payment_intent_success(self, mock_create, stripe_service: StripeService, test_booking: Booking):
        """Test successful payment intent creation."""
        context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=2000,
            base_price_cents=10000,
            student_fee_cents=1200,
            instructor_commission_cents=1200,
            target_instructor_payout_cents=8800,
            student_pay_cents=9200,
            application_fee_cents=400,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.12"),
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
        assert call_args["amount"] == 9200
        assert call_args["currency"] == "usd"
        assert call_args["customer"] == "cus_test123"
        assert call_args["transfer_data"]["destination"] == "acct_instructor123"
        assert call_args["application_fee_amount"] == 400
        assert call_args["transfer_group"] == f"booking:{test_booking.id}"

        metadata = call_args["metadata"]
        assert metadata["instructor_tier_pct"] == "0.12"
        assert metadata["base_price_cents"] == "10000"
        assert metadata["student_fee_cents"] == "1200"
        assert metadata["commission_cents"] == "1200"
        assert metadata["applied_credit_cents"] == "2000"
        assert metadata["student_pay_cents"] == "9200"
        assert metadata["application_fee_cents"] == "400"
        assert metadata["target_instructor_payout_cents"] == "8800"

        # Verify database record
        assert payment.booking_id == test_booking.id
        assert payment.stripe_payment_intent_id == "pi_test123"
        assert payment.amount == 9200
        assert payment.application_fee == 400

    @patch("stripe.PaymentIntent.confirm")
    def test_confirm_payment_intent_success(self, mock_confirm, stripe_service: StripeService, test_booking: Booking):
        """Test successful payment intent confirmation."""
        # Create payment record
        _payment = stripe_service.payment_repository.create_payment_record(
            test_booking.id, "pi_test123", 5000, 750, "requires_payment_method"
        )

        # Mock Stripe response
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"
        mock_confirm.return_value = mock_intent

        # Confirm payment
        confirmed_payment = stripe_service.confirm_payment_intent("pi_test123", "pm_card123")

        # Verify Stripe API call - use unittest.mock.ANY for return_url since it's from settings
        from unittest.mock import ANY

        mock_confirm.assert_called_once_with(
            "pi_test123",
            payment_method="pm_card123",
            return_url=ANY,  # Will be settings.frontend_url + "/student/payment/complete"
        )

        # Verify status update
        assert confirmed_payment.status == "succeeded"

    @patch("stripe.PaymentIntent.confirm")
    @patch("stripe.PaymentIntent.create")
    def test_process_booking_payment_success(
        self, mock_create, mock_confirm, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ):
        """Test end-to-end booking payment processing."""
        instructor_user, profile, _ = test_instructor

        # Create customer and connected account
        _customer = stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_student123")
        _connected_account = stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        charge_context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=0,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_commission_cents=0,
            target_instructor_payout_cents=5000,
            student_pay_cents=5000,
            application_fee_cents=750,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.15"),
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
        assert create_kwargs["application_fee_amount"] == 750
        assert create_kwargs["transfer_group"] == f"booking:{test_booking.id}"

        # Verify result
        assert result["success"] is True
        assert result["payment_intent_id"] == "pi_test123"
        assert result["status"] == "succeeded"
        assert result["amount"] == 5000  # $50.00 in cents
        assert result["application_fee"] == 750  # 15% fee

    @patch("stripe.Transfer.create")
    @patch("stripe.PaymentIntent.capture")
    def test_capture_payment_intent_creates_top_up_transfer(
        self,
        mock_capture,
        mock_transfer,
        stripe_service: StripeService,
        test_booking: Booking,
        test_instructor: tuple,
    ) -> None:
        """Top-up transfer is issued exactly once when credits exceed platform share."""

        instructor_user, profile, _ = test_instructor

        # Ensure connected account exists
        stripe_service.payment_repository.create_connected_account_record(
            profile.id, "acct_instructor123", onboarding_completed=True
        )

        # Build a charge context representing a large credit scenario
        top_up_context = ChargeContext(
            booking_id=test_booking.id,
            applied_credit_cents=3000,
            base_price_cents=8000,
            student_fee_cents=960,
            instructor_commission_cents=1200,
            target_instructor_payout_cents=6800,
            student_pay_cents=5960,
            application_fee_cents=0,
            top_up_transfer_cents=840,
            instructor_tier_pct=Decimal("0.15"),
        )

        stripe_service.build_charge_context = MagicMock(return_value=top_up_context)

        # Persist payment record prior to capture
        stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_topup123",
            amount=top_up_context.student_pay_cents,
            application_fee=top_up_context.application_fee_cents,
            status="requires_capture",
        )

        # Stripe capture response mock
        capture_response = {
            "status": "succeeded",
            "charges": {"data": []},
            "amount_received": top_up_context.student_pay_cents,
        }
        mock_capture.return_value = capture_response
        mock_transfer.return_value = {"id": "tr_topup123"}

        stripe_service.capture_payment_intent("pi_topup123")

        mock_transfer.assert_called_once()
        transfer_kwargs = mock_transfer.call_args[1]
        assert transfer_kwargs["amount"] == top_up_context.top_up_transfer_cents
        assert transfer_kwargs["destination"] == "acct_instructor123"
        assert transfer_kwargs["transfer_group"] == f"booking:{test_booking.id}"
        assert transfer_kwargs["metadata"]["payment_intent_id"] == "pi_topup123"

        # Payment event recorded
        events = stripe_service.payment_repository.get_payment_events_for_booking(test_booking.id)
        assert any(evt.event_type == "top_up_transfer_created" for evt in events)

        # Subsequent ensure call should no-op
        mock_transfer.reset_mock()
        stripe_service.ensure_top_up_transfer(
            booking_id=test_booking.id,
            payment_intent_id="pi_topup123",
            destination_account_id="acct_instructor123",
            amount_cents=top_up_context.top_up_transfer_cents,
        )
        mock_transfer.assert_not_called()

    def test_process_booking_payment_booking_not_found(self, stripe_service: StripeService):
        """Test payment processing with non-existent booking."""
        with pytest.raises(ServiceException, match="Booking .* not found"):
            stripe_service.process_booking_payment("nonexistent_booking", "pm_card123")

    def test_process_booking_payment_instructor_not_set_up(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ):
        """Test payment processing when instructor account not set up."""
        instructor_user, profile, _ = test_instructor

        # Create customer but no connected account
        stripe_service.payment_repository.create_customer_record(test_booking.student_id, "cus_student123")

        with pytest.raises(ServiceException, match="Instructor payment account not set up"):
            stripe_service.process_booking_payment(test_booking.id, "pm_card123")

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

    # ========== Webhook Handling Tests ==========

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.settings")
    def test_verify_webhook_signature_valid(self, mock_settings, mock_construct, stripe_service: StripeService):
        """Test valid webhook signature verification."""
        # Mock webhook secret configuration
        mock_settings.stripe_webhook_secret = "whsec_test_secret"

        # Mock successful verification
        mock_construct.return_value = {}

        result = stripe_service.verify_webhook_signature(b"payload", "signature")

        assert result is True
        mock_construct.assert_called_once_with(b"payload", "signature", "whsec_test_secret")

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.settings")
    def test_verify_webhook_signature_invalid(self, mock_settings, mock_construct, stripe_service: StripeService):
        """Test invalid webhook signature verification."""
        # Mock webhook secret configuration
        mock_settings.stripe_webhook_secret = "whsec_test_secret"

        # Mock signature verification error
        mock_construct.side_effect = stripe.SignatureVerificationError("Invalid", "signature")

        result = stripe_service.verify_webhook_signature(b"payload", "signature")

        assert result is False

    def test_handle_payment_intent_webhook_success(self, stripe_service: StripeService, test_booking: Booking):
        """Test handling payment intent webhook."""
        # Create payment record
        _payment = stripe_service.payment_repository.create_payment_record(
            test_booking.id, "pi_test123", 5000, 750, "requires_payment_method"
        )

        # Create webhook event
        event = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test123", "status": "succeeded"}}}

        # Handle webhook
        success = stripe_service.handle_payment_intent_webhook(event)

        assert success is True

        # Verify status update
        updated_payment = stripe_service.payment_repository.get_payment_by_intent_id("pi_test123")
        assert updated_payment.status == "succeeded"

    def test_handle_payment_intent_webhook_not_found(self, stripe_service: StripeService):
        """Test handling webhook for non-existent payment intent."""
        # Create webhook event
        event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_nonexistent", "status": "succeeded"}},
        }

        # Handle webhook
        success = stripe_service.handle_payment_intent_webhook(event)

        assert success is False

    # ========== Analytics Tests ==========

    def test_get_platform_revenue_stats(self, stripe_service: StripeService, test_booking: Booking):
        """Test getting platform revenue statistics."""
        # Create successful payment
        stripe_service.payment_repository.create_payment_record(test_booking.id, "pi_test123", 5000, 750, "succeeded")

        stats = stripe_service.get_platform_revenue_stats()

        assert stats["total_amount"] == 5000
        assert stats["total_fees"] == 750
        assert stats["payment_count"] == 1

    def test_get_instructor_earnings(
        self, stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
    ):
        """Test getting instructor earnings."""
        instructor_user, profile, _ = test_instructor

        # Create successful payment
        stripe_service.payment_repository.create_payment_record(test_booking.id, "pi_test123", 5000, 750, "succeeded")

        earnings = stripe_service.get_instructor_earnings(test_booking.instructor_id)

        assert earnings["total_earned"] == 4250  # 5000 - 750 fee
        assert earnings["total_fees"] == 750
        assert earnings["booking_count"] == 1

    # ========== Error Handling Tests ==========

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
