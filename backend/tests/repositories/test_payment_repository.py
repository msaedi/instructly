"""
Tests for PaymentRepository.

Verifies all payment-related database operations including:
- Customer record management
- Connected account management
- Payment intent tracking
- Payment method management
- Analytics calculations
"""

from datetime import datetime, time, timedelta

import pytest
import ulid
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentIntent, PaymentMethod, StripeConnectedAccount, StripeCustomer
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.repositories.payment_repository import PaymentRepository


class TestPaymentRepository:
    """Test suite for PaymentRepository."""

    @pytest.fixture
    def payment_repo(self, db: Session) -> PaymentRepository:
        """Create PaymentRepository instance."""
        return RepositoryFactory.create_payment_repository(db)

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
        category = db.query(ServiceCategory).filter_by(name="Test Category").first()
        if not category:
            category = ServiceCategory(
                id=str(ulid.ULID()),
                name="Test Category",
                slug="test-category",
                description="Test category for unit tests",
            )
            db.add(category)
            db.flush()

        catalog = db.query(ServiceCatalog).filter_by(name="Test Service").first()
        if not catalog:
            catalog = ServiceCatalog(
                id=str(ulid.ULID()),
                category_id=category.id,
                name="Test Service",
                slug="test-service",
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
            instructor_service_id=instructor_service.id,  # Use real service ID
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

    def test_create_customer_record(self, payment_repo: PaymentRepository, test_user: User):
        """Test creating a Stripe customer record."""
        stripe_customer_id = f"cus_{ulid.ULID()}"
        customer = payment_repo.create_customer_record(test_user.id, stripe_customer_id)

        assert customer is not None
        assert customer.user_id == test_user.id
        assert customer.stripe_customer_id == stripe_customer_id
        assert len(customer.id) == 26  # ULID length

    def test_get_customer_by_user_id(self, payment_repo: PaymentRepository, test_user: User):
        """Test retrieving customer by user ID."""
        stripe_customer_id = f"cus_{ulid.ULID()}"
        payment_repo.create_customer_record(test_user.id, stripe_customer_id)

        customer = payment_repo.get_customer_by_user_id(test_user.id)
        assert customer is not None
        assert customer.user_id == test_user.id
        assert customer.stripe_customer_id == stripe_customer_id

    def test_get_customer_by_stripe_id(self, payment_repo: PaymentRepository, test_user: User):
        """Test retrieving customer by Stripe ID."""
        stripe_customer_id = f"cus_{ulid.ULID()}"
        payment_repo.create_customer_record(test_user.id, stripe_customer_id)

        customer = payment_repo.get_customer_by_stripe_id(stripe_customer_id)
        assert customer is not None
        assert customer.user_id == test_user.id
        assert customer.stripe_customer_id == stripe_customer_id

    def test_get_nonexistent_customer(self, payment_repo: PaymentRepository):
        """Test retrieving non-existent customer returns None."""
        customer = payment_repo.get_customer_by_user_id("nonexistent")
        assert customer is None

    # ========== Connected Account Management Tests ==========

    def test_create_connected_account_record(self, payment_repo: PaymentRepository, test_instructor: tuple):
        """Test creating a Stripe connected account."""
        _, profile, _ = test_instructor
        stripe_account_id = f"acct_{ulid.ULID()}"

        account = payment_repo.create_connected_account_record(
            profile.id, stripe_account_id, onboarding_completed=False
        )

        assert account is not None
        assert account.instructor_profile_id == profile.id
        assert account.stripe_account_id == stripe_account_id
        assert account.onboarding_completed is False
        assert len(account.id) == 26

    def test_get_connected_account_by_instructor_id(self, payment_repo: PaymentRepository, test_instructor: tuple):
        """Test retrieving connected account by instructor ID."""
        _, profile, _ = test_instructor
        stripe_account_id = f"acct_{ulid.ULID()}"
        payment_repo.create_connected_account_record(profile.id, stripe_account_id)

        account = payment_repo.get_connected_account_by_instructor_id(profile.id)
        assert account is not None
        assert account.instructor_profile_id == profile.id
        assert account.stripe_account_id == stripe_account_id

    def test_update_onboarding_status(self, payment_repo: PaymentRepository, test_instructor: tuple):
        """Test updating onboarding status."""
        _, profile, _ = test_instructor
        stripe_account_id = f"acct_{ulid.ULID()}"
        payment_repo.create_connected_account_record(profile.id, stripe_account_id, onboarding_completed=False)

        updated = payment_repo.update_onboarding_status(stripe_account_id, True)
        assert updated is not None
        assert updated.onboarding_completed is True

    def test_update_nonexistent_account(self, payment_repo: PaymentRepository):
        """Test updating non-existent account returns None."""
        result = payment_repo.update_onboarding_status("nonexistent", True)
        assert result is None

    # ========== Payment Intent Management Tests ==========

    def test_create_payment_record(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test creating a payment intent record."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        amount = 5000  # $50.00 in cents
        fee = 500  # $5.00 platform fee

        payment = payment_repo.create_payment_record(
            test_booking.id, payment_intent_id, amount, fee, status="requires_payment_method"
        )

        assert payment is not None
        assert payment.booking_id == test_booking.id
        assert payment.stripe_payment_intent_id == payment_intent_id
        assert payment.amount == amount
        assert payment.application_fee == fee
        assert payment.status == "requires_payment_method"
        assert len(payment.id) == 26

    def test_update_payment_status(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test updating payment status."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        payment_repo.create_payment_record(test_booking.id, payment_intent_id, 5000, 500, "requires_payment_method")

        updated = payment_repo.update_payment_status(payment_intent_id, "succeeded")
        assert updated is not None
        assert updated.status == "succeeded"

    def test_get_payment_by_intent_id(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test retrieving payment by intent ID."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        payment_repo.create_payment_record(test_booking.id, payment_intent_id, 5000, 500)

        payment = payment_repo.get_payment_by_intent_id(payment_intent_id)
        assert payment is not None
        assert payment.stripe_payment_intent_id == payment_intent_id

    def test_get_payment_by_booking_id(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test retrieving payment by booking ID."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        payment_repo.create_payment_record(test_booking.id, payment_intent_id, 5000, 500)

        payment = payment_repo.get_payment_by_booking_id(test_booking.id)
        assert payment is not None
        assert payment.booking_id == test_booking.id

    # ========== Payment Method Management Tests ==========

    def test_save_payment_method(self, payment_repo: PaymentRepository, test_user: User):
        """Test saving a payment method."""
        method = payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "4242", "visa", is_default=True)

        assert method is not None
        assert method.user_id == test_user.id
        assert method.last4 == "4242"
        assert method.brand == "visa"
        assert method.is_default is True
        assert len(method.id) == 26

    def test_save_multiple_payment_methods_default_handling(self, payment_repo: PaymentRepository, test_user: User):
        """Test that setting a new default unsets the old one."""
        # Create first default method
        method1 = payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "4242", "visa", is_default=True)

        # Create second default method (should unset first)
        method2 = payment_repo.save_payment_method(
            test_user.id, f"pm_{ulid.ULID()}", "5555", "mastercard", is_default=True
        )

        # Refresh first method
        payment_repo.db.refresh(method1)

        assert method1.is_default is False
        assert method2.is_default is True

    def test_get_payment_methods_by_user(self, payment_repo: PaymentRepository, test_user: User):
        """Test retrieving all payment methods for a user."""
        # Create multiple methods
        payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "4242", "visa", is_default=False)
        payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "5555", "mastercard", is_default=True)
        payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "3737", "amex", is_default=False)

        methods = payment_repo.get_payment_methods_by_user(test_user.id)
        assert len(methods) == 3
        # Default should be first due to ordering
        assert methods[0].is_default is True
        assert methods[0].brand == "mastercard"

    def test_get_default_payment_method(self, payment_repo: PaymentRepository, test_user: User):
        """Test retrieving default payment method."""
        # Create non-default method
        payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "4242", "visa", is_default=False)
        # Create default method
        payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "5555", "mastercard", is_default=True)

        default = payment_repo.get_default_payment_method(test_user.id)
        assert default is not None
        assert default.is_default is True
        assert default.brand == "mastercard"

    def test_delete_payment_method(self, payment_repo: PaymentRepository, test_user: User):
        """Test deleting a payment method."""
        method = payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "4242", "visa")

        # Delete should succeed
        result = payment_repo.delete_payment_method(method.id, test_user.id)
        assert result is True

        # Verify it's deleted
        methods = payment_repo.get_payment_methods_by_user(test_user.id)
        assert len(methods) == 0

    def test_delete_payment_method_wrong_user(self, payment_repo: PaymentRepository, test_user: User):
        """Test that deleting with wrong user ID fails."""
        method = payment_repo.save_payment_method(test_user.id, f"pm_{ulid.ULID()}", "4242", "visa")

        # Delete with wrong user ID should fail
        result = payment_repo.delete_payment_method(method.id, "wrong_user_id")
        assert result is False

        # Verify it's not deleted
        methods = payment_repo.get_payment_methods_by_user(test_user.id)
        assert len(methods) == 1

    # ========== Analytics Tests ==========

    def test_get_platform_revenue_stats_empty(self, payment_repo: PaymentRepository):
        """Test platform revenue stats with no data."""
        stats = payment_repo.get_platform_revenue_stats()

        assert stats["total_amount"] == 0
        assert stats["total_fees"] == 0
        assert stats["payment_count"] == 0
        assert stats["average_transaction"] == 0

    def test_get_platform_revenue_stats_with_data(
        self, payment_repo: PaymentRepository, test_booking: Booking, db: Session
    ):
        """Test platform revenue stats with successful payments."""
        # Create multiple successful payments
        for i in range(3):
            booking = Booking(
                id=str(ulid.ULID()),
                student_id=test_booking.student_id,
                instructor_id=test_booking.instructor_id,
                instructor_service_id=test_booking.instructor_service_id,  # Use the same service ID
                booking_date=datetime.now().date(),
                start_time=datetime.now().time(),
                end_time=(datetime.now() + timedelta(hours=1)).time(),
                service_name="Test Service",
                hourly_rate=50.00,
                total_price=50.00,
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
            )
            db.add(booking)
            db.flush()

            payment_repo.create_payment_record(
                booking.id, f"pi_{ulid.ULID()}", 5000 + (i * 1000), 500 + (i * 100), "succeeded"
            )

        stats = payment_repo.get_platform_revenue_stats()

        assert stats["total_amount"] == 18000  # 5000 + 6000 + 7000
        assert stats["total_fees"] == 1800  # 500 + 600 + 700
        assert stats["payment_count"] == 3
        assert stats["average_transaction"] == 6000.0

    def test_get_platform_revenue_stats_date_filter(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test platform revenue stats with date filtering."""
        # Create payment
        payment_repo.create_payment_record(test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded")

        # Stats with future date range should be empty
        future_start = datetime.now() + timedelta(days=1)
        stats = payment_repo.get_platform_revenue_stats(start_date=future_start)

        assert stats["payment_count"] == 0

        # Stats with past date range should include payment
        past_start = datetime.now() - timedelta(days=1)
        stats = payment_repo.get_platform_revenue_stats(start_date=past_start)

        assert stats["payment_count"] == 1

    def test_get_instructor_earnings(
        self, payment_repo: PaymentRepository, test_booking: Booking, test_instructor: tuple
    ):
        """Test instructor earnings calculation."""
        _, profile, _ = test_instructor

        # Create successful payment
        payment_repo.create_payment_record(test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded")

        # Get earnings (using instructor user ID as proxy for profile ID in this test)
        earnings = payment_repo.get_instructor_earnings(test_booking.instructor_id)

        assert earnings["total_earned"] == 4500  # 5000 - 500 fee
        assert earnings["total_fees"] == 500
        assert earnings["booking_count"] == 1
        assert earnings["average_earning"] == 4500.0

    def test_get_instructor_earnings_multiple_bookings(
        self, payment_repo: PaymentRepository, test_instructor: tuple, db: Session, test_user: User
    ):
        """Test instructor earnings with multiple bookings."""
        instructor_user, profile, instructor_service = test_instructor

        # Create multiple bookings and payments
        for i in range(3):
            booking = Booking(
                id=str(ulid.ULID()),
                student_id=test_user.id,
                instructor_id=instructor_user.id,
                instructor_service_id=instructor_service.id,  # Use real service ID
                booking_date=datetime.now().date(),
                start_time=datetime.now().time(),
                end_time=(datetime.now() + timedelta(hours=1)).time(),
                service_name="Test Service",
                hourly_rate=50.00,
                total_price=50.00,
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
            )
            db.add(booking)
            db.flush()

            payment_repo.create_payment_record(booking.id, f"pi_{ulid.ULID()}", 5000 + (i * 1000), 500, "succeeded")

        earnings = payment_repo.get_instructor_earnings(instructor_user.id)

        assert earnings["total_earned"] == 16500  # (5000-500) + (6000-500) + (7000-500)
        assert earnings["total_fees"] == 1500  # 500 * 3
        assert earnings["booking_count"] == 3
        assert earnings["average_earning"] == 5500.0

    # ========== Error Handling Tests ==========

    def test_create_customer_record_exception(self, payment_repo: PaymentRepository):
        """Test that repository exception is raised on database error."""
        with pytest.raises(RepositoryException):
            # Invalid user_id should cause foreign key constraint violation
            payment_repo.create_customer_record("invalid_user_id", f"cus_{ulid.ULID()}")
