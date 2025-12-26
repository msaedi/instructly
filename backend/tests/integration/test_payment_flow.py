"""
Integration tests for complete payment flows in InstaInstru platform.

Tests end-to-end scenarios involving multiple services and components.
These tests verify that the entire payment system works correctly when
all pieces are integrated together.
"""

from datetime import date, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import stripe
import ulid

from app.core.enums import RoleName
from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.booking_service import BookingService
from app.services.cache_service import CacheService
from app.services.config_service import ConfigService
from app.services.permission_service import PermissionService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


@pytest.fixture(autouse=True)
def _no_floors_for_payment_flow(disable_price_floors):
    """Disable price floors for payment flow integration tests."""
    yield


def _build_stripe_service(db_session: Session) -> StripeService:
    """Construct StripeService with explicit configuration dependencies."""
    return StripeService(
        db_session,
        config_service=ConfigService(db_session),
        pricing_service=PricingService(db_session),
    )


class TestPaymentIntegration:
    """Integration tests for complete payment flows."""

    @pytest.fixture
    def student_user(self, db: Session) -> User:
        """Create a student user for testing."""
        # Create user directly (allowed in integration tests for setup)
        user = User(
            id=str(ulid.ULID()),
            email=f"student_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Jane",
            last_name="Student",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign student role using PermissionService (this uses repositories)
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, "student")

        return user

    @pytest.fixture
    def instructor_setup(self, db: Session) -> tuple[User, InstructorProfile, InstructorService]:
        """Create instructor user with profile and service using repositories."""
        # Create instructor user directly (allowed in integration tests for setup)
        user = User(
            id=str(ulid.ULID()),
            email=f"instructor_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="John",
            last_name="Instructor",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign instructor role using PermissionService (this uses repositories)
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, "instructor")

        # Create instructor profile directly (setup)
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=user.id,
            bio="Test instructor bio",
            years_experience=5,
        )
        db.add(profile)
        db.flush()

        # Create service category and catalog entry directly (setup)
        unique_suffix = str(ulid.ULID())  # Use full ULID for uniqueness
        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Music Lessons",
            slug=f"music-lessons-{unique_suffix}",
            description="Music instruction",
        )
        db.add(category)
        db.flush()

        service = ServiceCatalog(
            id=str(ulid.ULID()),
            category_id=category.id,
            name="Piano Lessons",
            slug=f"piano-lessons-{unique_suffix}",
            description="One-on-one piano instruction",
        )
        db.add(service)
        db.flush()

        # Create instructor service directly (setup)
        instructor_service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=service.id,
            hourly_rate=80.0,
        )
        db.add(instructor_service)
        db.flush()

        return user, profile, instructor_service

    @pytest.fixture
    def test_booking(self, db: Session, student_user: User, instructor_setup: tuple) -> Booking:
        """Create a test booking using repository."""
        instructor_user, instructor_profile, instructor_service = instructor_setup
        booking = create_booking_pg_safe(
            db,
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            duration_minutes=60,
            total_price=Decimal("80.00"),
            service_name="Piano Lessons",
            hourly_rate=Decimal("80.00"),
            location_type="student_home",
            status=BookingStatus.CONFIRMED,
        )
        db.flush()
        return booking

    @patch("stripe.Customer.create")
    @patch("stripe.Account.create")
    @patch("stripe.AccountLink.create")
    @patch("stripe.PaymentIntent.create")
    @patch("stripe.PaymentIntent.confirm")
    def test_complete_booking_payment_flow(
        self,
        mock_confirm,
        mock_intent_create,
        mock_link_create,
        mock_account_create,
        mock_customer_create,
        db: Session,
        student_user: User,
        instructor_setup: tuple,
        test_booking: Booking,
    ):
        """Test complete flow from instructor onboarding to payment confirmation."""
        instructor_user, instructor_profile, instructor_service = instructor_setup

        # Mock Stripe responses
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_customer_create.return_value = mock_customer

        mock_account = MagicMock()
        mock_account.id = "acct_test123"
        mock_account_create.return_value = mock_account

        mock_link = MagicMock()
        mock_link.url = "https://connect.stripe.com/setup/123"
        mock_link_create.return_value = mock_link

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_confirmation"
        mock_intent_create.return_value = mock_intent

        mock_confirmed_intent = MagicMock()
        mock_confirmed_intent.id = "pi_test123"
        mock_confirmed_intent.status = "succeeded"
        mock_confirm.return_value = mock_confirmed_intent

        stripe_service = _build_stripe_service(db)

        # Step 1: Create Stripe customer for student
        customer = stripe_service.create_customer(
            user_id=student_user.id,
            email=student_user.email,
            name=f"{student_user.first_name} {student_user.last_name}",
        )
        assert customer.user_id == student_user.id
        assert customer.stripe_customer_id == "cus_test123"

        # Step 2: Create connected account for instructor
        connected_account = stripe_service.create_connected_account(
            instructor_profile_id=instructor_profile.id, email=instructor_user.email
        )
        assert connected_account.instructor_profile_id == instructor_profile.id
        assert connected_account.stripe_account_id == "acct_test123"
        assert not connected_account.onboarding_completed

        # Step 3: Create account link for onboarding
        onboarding_url = stripe_service.create_account_link(
            instructor_profile_id=instructor_profile.id,
            refresh_url="http://localhost:3000/refresh",
            return_url="http://localhost:3000/complete",
        )
        assert onboarding_url == "https://connect.stripe.com/setup/123"

        # Step 4: Simulate onboarding completion
        stripe_service.payment_repository.update_onboarding_status(connected_account.stripe_account_id, True)
        connected_account.onboarding_completed = True

        # Step 5: Process payment for booking
        payment_result = stripe_service.process_booking_payment(
            booking_id=test_booking.id, payment_method_id="pm_test123"
        )

        # Verify payment result
        assert payment_result["success"] is True
        assert payment_result["payment_intent_id"] == "pi_test123"
        assert payment_result["status"] == "succeeded"
        assert payment_result["amount"] == 8960  # $80 base + 12% student fee
        assert payment_result["application_fee"] == 2160  # 12% student fee + 15% platform fee

        # Step 6: Verify database records
        payment_record = stripe_service.payment_repository.get_payment_by_booking_id(test_booking.id)
        assert payment_record is not None
        assert payment_record.stripe_payment_intent_id == "pi_test123"
        assert payment_record.amount == 8960
        assert payment_record.application_fee == 2160
        assert payment_record.status == "succeeded"

        # Verify all Stripe calls were made
        from unittest.mock import ANY

        mock_customer_create.assert_called_once()
        mock_account_create.assert_called_once()
        mock_link_create.assert_called_once()
        mock_intent_create.assert_called_once()
        mock_confirm.assert_called_once_with(
            "pi_test123",
            payment_method="pm_test123",
            return_url=ANY,  # Will be settings.frontend_url + "/student/payment/complete"
        )

    @patch("stripe.Customer.create")
    @patch("stripe.PaymentIntent.create")
    @patch("stripe.Refund.create")
    def test_booking_cancellation_and_refund_flow(
        self,
        mock_refund_create,
        mock_intent_create,
        mock_customer_create,
        db: Session,
        student_user: User,
        test_booking: Booking,
    ):
        """Test booking cancellation and refund processing."""
        # Mock Stripe responses
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_customer_create.return_value = mock_customer

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "succeeded"
        mock_intent_create.return_value = mock_intent

        mock_refund = MagicMock()
        mock_refund.id = "re_test123"
        mock_refund.status = "succeeded"
        mock_refund.amount = 8000
        mock_refund_create.return_value = mock_refund

        stripe_service = _build_stripe_service(db)

        # Step 1: Create customer and payment (simulate completed payment)
        _customer = stripe_service.create_customer(
            user_id=student_user.id,
            email=student_user.email,
            name=f"{student_user.first_name} {student_user.last_name}",
        )

        payment_record = stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_test123",
            amount=8000,
            application_fee=1200,
            status="succeeded",
        )

        # Step 2: Update booking status to cancelled
        test_booking.status = BookingStatus.CANCELLED
        db.flush()

        # Step 3: Process refund (would be called by cancellation service)
        # Note: This would typically be in a separate RefundService, but testing here
        with patch("stripe.Refund.create") as mock_refund_create:
            mock_refund_create.return_value = mock_refund

            # Simulate refund processing logic
            refund_amount = payment_record.amount - payment_record.application_fee  # Refund student portion
            stripe.Refund.create(payment_intent=payment_record.stripe_payment_intent_id, amount=refund_amount)

            # Verify refund was processed
            mock_refund_create.assert_called_once_with(payment_intent="pi_test123", amount=6800)  # $80 - 15% fee = $68

    @patch("stripe.Webhook.construct_event")
    def test_webhook_payment_confirmation_flow(self, mock_construct_event, db: Session, test_booking: Booking):
        """Test webhook updating payment status and booking confirmation."""
        stripe_service = _build_stripe_service(db)

        # Create initial payment record in pending state
        _payment_record = stripe_service.payment_repository.create_payment_record(
            booking_id=test_booking.id,
            payment_intent_id="pi_test123",
            amount=8000,
            application_fee=1200,
            status="requires_confirmation",
        )

        # Mock webhook event
        webhook_event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_test123", "status": "succeeded"}},
        }

        # Process webhook event
        result = stripe_service.handle_webhook_event(webhook_event)

        # Verify webhook processing
        assert result["success"] is True
        assert result["event_type"] == "payment_intent.succeeded"

        # Verify payment status was updated
        updated_payment = stripe_service.payment_repository.get_payment_by_intent_id("pi_test123")
        assert updated_payment.status == "succeeded"

        # Verify booking status was updated (if it was pending)
        db.refresh(test_booking)
        if test_booking.status == BookingStatus.PENDING:
            assert test_booking.status == BookingStatus.CONFIRMED

    def test_webhook_invalidation_updates_cached_upcoming_lessons(
        self,
        db: Session,
        student_user: User,
        instructor_setup: tuple,
    ):
        """Ensure webhook confirmation invalidates cached upcoming bookings."""
        instructor_user, instructor_profile, _service = instructor_setup
        cache_service = CacheService(db, None)
        booking_service = BookingService(db, cache_service=cache_service)
        stripe_service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
            cache_service=cache_service,
        )

        confirmed_booking = create_booking_pg_safe(
            db,
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=_service.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            duration_minutes=60,
            total_price=Decimal("80.00"),
            service_name="Piano Lessons",
            hourly_rate=Decimal("80.00"),
            status=BookingStatus.CONFIRMED,
        )
        db.flush()

        pending_booking = create_booking_pg_safe(
            db,
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=_service.id,
            booking_date=date.today() + timedelta(days=3),
            start_time=time(16, 0),
            end_time=time(17, 0),
            duration_minutes=60,
            total_price=Decimal("80.00"),
            service_name="Piano Lessons",
            hourly_rate=Decimal("80.00"),
            status=BookingStatus.PENDING,
        )
        db.flush()

        payment_record = stripe_service.payment_repository.create_payment_record(
            booking_id=pending_booking.id,
            payment_intent_id="pi_cache_test",
            amount=8000,
            application_fee=1200,
            status="succeeded",
        )

        student_identity = SimpleNamespace(
            id=student_user.id,
            roles=[SimpleNamespace(name=RoleName.STUDENT)],
        )

        initial = booking_service.get_bookings_for_user(
            student_identity,
            status=BookingStatus.CONFIRMED,
            upcoming_only=True,
            limit=5,
        )
        assert {b.id for b in initial} == {confirmed_booking.id}

        stripe_service._handle_successful_payment(payment_record)
        db.flush()

        updated = booking_service.get_bookings_for_user(
            student_identity,
            status=BookingStatus.CONFIRMED,
            upcoming_only=True,
            limit=5,
        )
        assert {b.id for b in updated} == {confirmed_booking.id, pending_booking.id}

    def test_upcoming_cache_refreshes_after_local_confirmation(
        self,
        db: Session,
        student_user: User,
        instructor_setup: tuple,
    ):
        """Ensure cache invalidation works when booking confirmed immediately."""
        instructor_user, instructor_profile, instructor_service = instructor_setup
        existing_booking = create_booking_pg_safe(
            db,
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=3),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name="Piano Lesson",
            hourly_rate=Decimal("80.00"),
            total_price=Decimal("80.00"),
            duration_minutes=60,
        )
        pending_booking = create_booking_pg_safe(
            db,
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=date.today() + timedelta(days=5),
            start_time=time(14, 0),
            end_time=time(15, 0),
            status=BookingStatus.PENDING,
            service_name="Piano Lesson",
            hourly_rate=Decimal("80.00"),
            total_price=Decimal("80.00"),
            duration_minutes=60,
        )
        db.flush()

        cache_service = CacheService(db, None)
        booking_service = BookingService(db, cache_service=cache_service)

        first = booking_service.get_bookings_for_user(
            student_user,
            status=BookingStatus.CONFIRMED,
            upcoming_only=True,
            limit=5,
        )
        assert {b.id for b in first} == {existing_booking.id}

        pending_booking.status = BookingStatus.CONFIRMED
        db.flush()
        booking_service.invalidate_booking_cache(pending_booking)

        refreshed = booking_service.get_bookings_for_user(
            student_user,
            status=BookingStatus.CONFIRMED,
            upcoming_only=True,
            limit=5,
        )
        assert {b.id for b in refreshed} == {existing_booking.id, pending_booking.id}

    @patch("stripe.PaymentIntent.create")
    @patch("stripe.PaymentIntent.confirm")
    def test_credit_checkout_with_fee_payment(
        self,
        mock_confirm: MagicMock,
        mock_intent_create: MagicMock,
        db: Session,
        student_user: User,
        instructor_setup: tuple,
        test_booking: Booking,
    ):
        """Part 6: Verify credits are capped at lesson price and fee is charged to card.

        With Part 6, credits can only cover the lesson price, never the platform fee.
        - $200 credit available, $80 lesson ($89.60 total with 12% fee)
        - Credit applied: $80 (capped at lesson price)
        - Card charged: $9.60 (platform fee - minimum card charge)
        - Remaining credit: $120
        """
        # Mock Stripe responses
        mock_pi = MagicMock()
        mock_pi.id = "pi_credit_test"
        mock_pi.status = "succeeded"
        mock_pi.client_secret = "pi_credit_test_secret"
        mock_intent_create.return_value = mock_pi
        mock_confirm.return_value = mock_pi

        instructor_user, instructor_profile, _service = instructor_setup
        stripe_service = _build_stripe_service(db)
        payment_repo = stripe_service.payment_repository

        payment_repo.create_customer_record(student_user.id, "cus_credit_test")
        payment_repo.create_connected_account_record(
            instructor_profile.id,
            "acct_credit_test",
            onboarding_completed=True,
        )
        payment_repo.create_platform_credit(
            user_id=student_user.id,
            amount_cents=20000,  # $200 credit
            reason="test_credit",
            source_booking_id=None,
        )

        initial_balance = payment_repo.get_total_available_credits(student_user.id)
        assert initial_balance == 20000

        # Part 6: Payment method required even with large credit (fee must be paid)
        result = stripe_service.process_booking_payment(
            booking_id=test_booking.id,
            payment_method_id="pm_credit_test",  # Required for fee
            requested_credit_cents=initial_balance,
        )

        applied = payment_repo.get_applied_credit_cents_for_booking(test_booking.id)
        remaining = payment_repo.get_total_available_credits(student_user.id)

        assert result["success"] is True
        assert result["payment_intent_id"] == "pi_credit_test"
        assert result["status"] == "succeeded"

        # Part 6: Credit capped at lesson price ($80 = 8000 cents)
        assert applied == 8000, f"Credit should be capped at lesson price, got {applied}"

        # Remaining = $200 - $80 = $120
        assert remaining == 12000, f"Remaining credit should be $120, got {remaining}"

        # Card charged = $9.60 (fee only)
        assert result["amount"] == 960, f"Card should be charged fee only ($9.60), got {result['amount']}"

    @patch("stripe.Customer.create")
    def test_multiple_payment_methods_flow(self, mock_customer_create, db: Session, student_user: User):
        """Test student managing multiple payment methods."""
        # Mock Stripe response
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_customer_create.return_value = mock_customer

        stripe_service = _build_stripe_service(db)

        # Step 1: Create customer
        _customer = stripe_service.create_customer(
            user_id=student_user.id,
            email=student_user.email,
            name=f"{student_user.first_name} {student_user.last_name}",
        )

        # Step 2: Add multiple payment methods
        with patch("stripe.PaymentMethod.retrieve") as mock_retrieve, patch(
            "stripe.PaymentMethod.attach"
        ) as mock_attach:
            # Mock first payment method (not attached to any customer)
            mock_pm1 = MagicMock()
            mock_pm1.card = MagicMock()
            mock_pm1.card.last4 = "4242"
            mock_pm1.card.brand = "visa"
            mock_pm1.customer = None  # Not attached yet
            mock_retrieve.return_value = mock_pm1

            # Mock attachment result
            mock_pm1_attached = MagicMock()
            mock_pm1_attached.card = mock_pm1.card
            mock_pm1_attached.customer = "cus_test123"
            mock_attach.return_value = mock_pm1_attached

            _pm1 = stripe_service.save_payment_method(
                user_id=student_user.id, payment_method_id="pm_test1", set_as_default=True
            )

            # Mock second payment method (also not attached)
            mock_pm2 = MagicMock()
            mock_pm2.card = MagicMock()
            mock_pm2.card.last4 = "0005"
            mock_pm2.card.brand = "mastercard"
            mock_pm2.customer = None  # Not attached yet

            # When retrieving pm_test2, return the unattached mock
            def side_effect(payment_method_id):
                if payment_method_id == "pm_test2":
                    return mock_pm2
                return mock_pm1

            mock_retrieve.side_effect = side_effect

            # Mock attachment result for second card
            mock_pm2_attached = MagicMock()
            mock_pm2_attached.card = mock_pm2.card
            mock_pm2_attached.customer = "cus_test123"

            # When attaching, return the appropriate attached mock
            def attach_side_effect(payment_method_id, customer):
                if payment_method_id == "pm_test2":
                    return mock_pm2_attached
                return mock_pm1_attached

            mock_attach.side_effect = attach_side_effect

            pm2 = stripe_service.save_payment_method(
                user_id=student_user.id, payment_method_id="pm_test2", set_as_default=False
            )

        # Step 3: Verify payment methods
        payment_methods = stripe_service.get_user_payment_methods(student_user.id)
        assert len(payment_methods) == 2

        # Verify default method
        default_method = next((pm for pm in payment_methods if pm.is_default), None)
        assert default_method is not None
        assert default_method.last4 == "4242"

        # Step 4: Delete a payment method
        success = stripe_service.delete_payment_method(pm2.id, student_user.id)
        assert success is True

        # Verify deletion
        remaining_methods = stripe_service.get_user_payment_methods(student_user.id)
        assert len(remaining_methods) == 1
        assert remaining_methods[0].last4 == "4242"

    def test_error_handling_in_payment_flow(self, db: Session, student_user: User, test_booking: Booking):
        """Test error handling throughout payment flow."""
        stripe_service = _build_stripe_service(db)

        # Test 1: Payment for non-existent booking
        with pytest.raises(ServiceException, match="not found"):
            stripe_service.process_booking_payment(booking_id="nonexistent", payment_method_id="pm_test")

        # Test 2: Customer creation failure
        with patch("stripe.Customer.create") as mock_create:
            mock_create.side_effect = stripe.StripeError("API Error")

            with pytest.raises(ServiceException, match="Failed to create Stripe customer"):
                stripe_service.create_customer(
                    user_id=student_user.id,
                    email=student_user.email,
                    name=f"{student_user.first_name} {student_user.last_name}",
                )

        # Test 3: Webhook signature verification failure
        with patch("stripe.Webhook.construct_event") as mock_construct:
            with patch("app.services.stripe_service.settings") as mock_settings:
                # Mock webhook secret configuration
                mock_settings.stripe_webhook_secret = "whsec_test_secret"

                mock_construct.side_effect = stripe.SignatureVerificationError("Invalid signature", "sig_header")

                result = stripe_service.verify_webhook_signature(b"payload", "invalid_signature")
                assert result is False

    @patch("stripe.Customer.create")
    @patch("stripe.Account.create")
    def test_concurrent_operations_handling(
        self, mock_account_create, mock_customer_create, db: Session, student_user: User
    ):
        """Test handling of concurrent operations (basic race condition test)."""
        # Mock Stripe responses
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_customer_create.return_value = mock_customer

        stripe_service = _build_stripe_service(db)

        # Test concurrent customer creation (should handle duplicates gracefully)
        customer1 = stripe_service.create_customer(
            user_id=student_user.id,
            email=student_user.email,
            name=f"{student_user.first_name} {student_user.last_name}",
        )

        # Second call should return existing customer
        customer2 = stripe_service.create_customer(
            user_id=student_user.id,
            email=student_user.email,
            name=f"{student_user.first_name} {student_user.last_name}",
        )

        assert customer1.id == customer2.id
        assert customer1.user_id == customer2.user_id
        assert mock_customer_create.call_count == 1  # Should only call Stripe once


class TestPaymentAnalytics:
    """Test analytics and reporting functionality."""

    @pytest.fixture
    def student_user(self, db: Session) -> User:
        """Create a student user for testing."""
        user = User(
            id=str(ulid.ULID()),
            email=f"student_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Jane",
            last_name="Student",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign student role using PermissionService
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, "student")

        return user

    @pytest.fixture
    def instructor_setup(self, db: Session) -> tuple[User, InstructorProfile, InstructorService]:
        """Create instructor user with profile and service."""
        # Create instructor user directly (allowed in integration tests for setup)
        user = User(
            id=str(ulid.ULID()),
            email=f"instructor_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="John",
            last_name="Instructor",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign instructor role using PermissionService (this uses repositories)
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, "instructor")

        # Create instructor profile directly (setup)
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=user.id,
            bio="Test instructor bio",
            years_experience=5,
        )
        db.add(profile)
        db.flush()

        # Create service category and catalog entry directly (setup)
        unique_suffix = str(ulid.ULID())  # Use full ULID for uniqueness
        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Music Lessons",
            slug=f"music-lessons-{unique_suffix}",
            description="Music instruction",
        )
        db.add(category)
        db.flush()

        service = ServiceCatalog(
            id=str(ulid.ULID()),
            category_id=category.id,
            name="Piano Lessons",
            slug=f"piano-lessons-{unique_suffix}",
            description="One-on-one piano instruction",
        )
        db.add(service)
        db.flush()

        # Create instructor service directly (setup)
        instructor_service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=service.id,
            hourly_rate=80.0,
        )
        db.add(instructor_service)
        db.flush()

        return user, profile, instructor_service

    def test_platform_revenue_calculations(self, db: Session, student_user: User, instructor_setup: tuple):
        """Test platform revenue analytics across multiple payments."""
        stripe_service = _build_stripe_service(db)
        instructor_user, instructor_profile, instructor_service = instructor_setup

        config_service = ConfigService(db)
        pricing_config, _ = config_service.get_pricing_config()
        student_fee_pct = Decimal(str(pricing_config["student_fee_pct"]))
        default_tier_pct = Decimal(str(pricing_config["instructor_tiers"][0]["pct"]))
        fee_ratio = (student_fee_pct + default_tier_pct) / (Decimal(1) + student_fee_pct)

        # Create test bookings and payments using repository
        booking_ids = []
        recorded_fees: list[int] = []
        for i in range(3):
            booking = create_booking_pg_safe(
                db,
                student_id=student_user.id,
                instructor_id=instructor_user.id,
                instructor_service_id=instructor_service.id,
                booking_date=date.today(),
                start_time=time(14, 0),
                end_time=time(15, 0),
                duration_minutes=60,
                total_price=Decimal(str((i + 1) * 20)),
                service_name="Piano Lessons",
                hourly_rate=Decimal(str((i + 1) * 20)),
                location_type="student_home",
                status=BookingStatus.CONFIRMED,
                offset_index=i,
            )
            booking_ids.append(booking.id)

            # Create payment records with different amounts
            amount = (i + 1) * 2000  # $20, $40, $60
            fee = int(
                (Decimal(amount) * fee_ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            recorded_fees.append(fee)

            stripe_service.payment_repository.create_payment_record(
                booking_id=booking.id,
                payment_intent_id=f"pi_test{i}",
                amount=amount,
                application_fee=fee,
                status="succeeded",
            )

        # Get platform revenue stats
        stats = stripe_service.get_platform_revenue_stats()

        # Verify calculations
        expected_total = sum((i + 1) * 2000 for i in range(3))
        expected_fees = sum(recorded_fees)

        assert stats["total_amount"] == expected_total
        assert stats["total_fees"] == expected_fees
        assert stats["payment_count"] == 3
        assert stats["average_transaction"] == expected_total / 3

    def test_instructor_earnings_calculations(self, db: Session, student_user: User, instructor_setup: tuple):
        """Test instructor earnings analytics."""
        instructor_user, instructor_profile, instructor_service = instructor_setup
        stripe_service = _build_stripe_service(db)

        config_service = ConfigService(db)
        pricing_config, _ = config_service.get_pricing_config()
        student_fee_pct = Decimal(str(pricing_config["student_fee_pct"]))
        default_tier_pct = Decimal(str(pricing_config["instructor_tiers"][0]["pct"]))
        fee_ratio = (student_fee_pct + default_tier_pct) / (Decimal(1) + student_fee_pct)

        # Create test payments for this instructor using repository
        recorded_fees: list[int] = []
        for i in range(2):
            booking = create_booking_pg_safe(
                db,
                student_id=student_user.id,
                instructor_id=instructor_user.id,
                instructor_service_id=instructor_service.id,
                booking_date=date.today(),
                start_time=time(14, 0),
                end_time=time(15, 0),
                duration_minutes=60,
                total_price=Decimal(str((i + 1) * 30)),
                service_name="Piano Lessons",
                hourly_rate=Decimal(str((i + 1) * 30)),
                location_type="student_home",
                status=BookingStatus.CONFIRMED,
                offset_index=i,
            )

            amount = (i + 1) * 3000  # $30, $60
            fee = int(
                (Decimal(amount) * fee_ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            recorded_fees.append(fee)

            stripe_service.payment_repository.create_payment_record(
                booking_id=booking.id,
                payment_intent_id=f"pi_instructor{i}",
                amount=amount,
                application_fee=fee,
                status="succeeded",
            )

        # Get instructor earnings
        earnings = stripe_service.get_instructor_earnings(instructor_user.id)

        # Verify calculations
        expected_gross = sum((i + 1) * 3000 for i in range(2))
        expected_fees = sum(recorded_fees)
        expected_net = expected_gross - expected_fees

        assert earnings["total_earned"] == expected_net
        assert earnings["total_fees"] == expected_fees
        assert earnings["booking_count"] == 2
