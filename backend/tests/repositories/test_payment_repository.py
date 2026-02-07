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
from sqlalchemy.orm import Session
import ulid

from app.core.exceptions import RepositoryException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import (
    PlatformCredit,
)
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.repositories.payment_repository import PaymentRepository

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


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

        # Create service category, subcategory and catalog item if they don't exist
        category = db.query(ServiceCategory).filter_by(name="Test Category").first()
        if not category:
            category = ServiceCategory(
                id=str(ulid.ULID()),
                name="Test Category",
                description="Test category for unit tests",
            )
            db.add(category)
            db.flush()

        subcategory = db.query(ServiceSubcategory).filter_by(category_id=category.id).first()
        if not subcategory:
            subcategory = ServiceSubcategory(
                name="General",
                category_id=category.id,
                display_order=1,
            )
            db.add(subcategory)
            db.flush()

        catalog = db.query(ServiceCatalog).filter_by(name="Test Service").first()
        if not catalog:
            catalog = ServiceCatalog(
                id=str(ulid.ULID()),
                subcategory_id=subcategory.id,
                name="Test Service",
                slug=f"test-service-{str(ulid.ULID()).lower()}",
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
        booking = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=0,
        )
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

    def test_get_connected_account_by_stripe_id(
        self, payment_repo: PaymentRepository, test_instructor: tuple
    ):
        """Lookup connected account by Stripe account ID."""
        _, profile, _ = test_instructor
        stripe_account_id = f"acct_{ulid.ULID()}"
        created = payment_repo.create_connected_account_record(profile.id, stripe_account_id)

        fetched = payment_repo.get_connected_account_by_stripe_id(stripe_account_id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_record_payout_event_and_history_ordering(
        self, payment_repo: PaymentRepository, test_instructor: tuple, db: Session
    ):
        """Payout history should be returned newest-first."""
        _, profile, _ = test_instructor
        first = payment_repo.record_payout_event(
            instructor_profile_id=profile.id,
            stripe_account_id="acct_1",
            payout_id="po_1",
            amount_cents=1000,
            status="pending",
            arrival_date=None,
        )
        second = payment_repo.record_payout_event(
            instructor_profile_id=profile.id,
            stripe_account_id="acct_1",
            payout_id="po_2",
            amount_cents=2000,
            status="paid",
            arrival_date=None,
        )
        first.created_at = datetime.now() - timedelta(days=1)
        second.created_at = datetime.now()
        db.flush()

        history = payment_repo.get_instructor_payout_history(profile.id, limit=10)
        assert history
        assert history[0].payout_id == "po_2"

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

    def test_update_payment_status_returns_none_when_missing(self, payment_repo: PaymentRepository) -> None:
        """Missing payment intent should return None."""
        assert payment_repo.update_payment_status("pi_missing", "succeeded") is None

    def test_get_payment_by_intent_id(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test retrieving payment by intent ID."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        payment_repo.create_payment_record(test_booking.id, payment_intent_id, 5000, 500)

        payment = payment_repo.get_payment_by_intent_id(payment_intent_id)
        assert payment is not None
        assert payment.stripe_payment_intent_id == payment_intent_id

    def test_get_payment_by_intent_id_missing(self, payment_repo: PaymentRepository) -> None:
        """Missing payment intent should return None."""
        assert payment_repo.get_payment_by_intent_id("pi_missing") is None

    def test_get_payment_by_booking_id(self, payment_repo: PaymentRepository, test_booking: Booking):
        """Test retrieving payment by booking ID."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        payment_repo.create_payment_record(test_booking.id, payment_intent_id, 5000, 500)

        payment = payment_repo.get_payment_by_booking_id(test_booking.id)
        assert payment is not None
        assert payment.booking_id == test_booking.id

    def test_get_payment_by_booking_id_missing(self, payment_repo: PaymentRepository) -> None:
        """Missing booking should return None."""
        assert payment_repo.get_payment_by_booking_id("booking_missing") is None

    def test_get_payment_intents_for_booking_orders_latest_first(
        self, payment_repo: PaymentRepository, test_booking: Booking, db: Session
    ):
        """Payment intents should be returned newest-first."""
        first = payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )
        second = payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 6000, 600, "succeeded"
        )

        first.created_at = datetime.now() - timedelta(days=1)
        second.created_at = datetime.now()
        db.flush()

        intents = payment_repo.get_payment_intents_for_booking(test_booking.id)
        assert [intent.stripe_payment_intent_id for intent in intents[:2]] == [
            second.stripe_payment_intent_id,
            first.stripe_payment_intent_id,
        ]

    def test_find_payment_by_booking_and_amount_returns_latest(
        self, payment_repo: PaymentRepository, test_booking: Booking, db: Session
    ):
        """Return the newest matching payment intent."""
        older = payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )
        newer = payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )

        older.created_at = datetime.now() - timedelta(days=2)
        newer.created_at = datetime.now()
        db.flush()

        match = payment_repo.find_payment_by_booking_and_amount(test_booking.id, 5000)
        assert match is not None
        assert match.stripe_payment_intent_id == newer.stripe_payment_intent_id
        assert payment_repo.find_payment_by_booking_and_amount(test_booking.id, 9999) is None

    def test_get_payment_by_booking_prefix_returns_latest(
        self, payment_repo: PaymentRepository, test_booking: Booking, db: Session
    ):
        """Prefix lookup should return the latest matching payment intent."""
        first = payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )
        second = payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 6000, 600, "succeeded"
        )
        first.created_at = datetime.now() - timedelta(days=1)
        second.created_at = datetime.now()
        db.flush()

        prefix = test_booking.id[:8]
        result = payment_repo.get_payment_by_booking_prefix(prefix)
        assert result is not None
        assert result.stripe_payment_intent_id == second.stripe_payment_intent_id

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

    def test_save_payment_method_existing_updates_default(
        self, payment_repo: PaymentRepository, test_user: User
    ):
        """Re-saving an existing method should update default flag."""
        stripe_id = f"pm_{ulid.ULID()}"
        existing = payment_repo.save_payment_method(test_user.id, stripe_id, "4242", "visa", is_default=False)

        updated = payment_repo.save_payment_method(test_user.id, stripe_id, "4242", "visa", is_default=True)
        payment_repo.db.refresh(existing)
        assert updated.id == existing.id
        assert updated.is_default is True

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

    def test_get_payment_method_by_stripe_id(self, payment_repo: PaymentRepository, test_user: User):
        """Find payment method by Stripe payment method ID."""
        stripe_id = f"pm_{ulid.ULID()}"
        created = payment_repo.save_payment_method(test_user.id, stripe_id, "4242", "visa")

        fetched = payment_repo.get_payment_method_by_stripe_id(stripe_id, test_user.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_set_default_payment_method(self, payment_repo: PaymentRepository, test_user: User):
        """Set default should flip previous defaults."""
        method1 = payment_repo.save_payment_method(
            test_user.id, f"pm_{ulid.ULID()}", "4242", "visa", is_default=True
        )
        method2 = payment_repo.save_payment_method(
            test_user.id, f"pm_{ulid.ULID()}", "5555", "mastercard", is_default=False
        )

        assert payment_repo.set_default_payment_method(method2.id, test_user.id) is True
        payment_repo.db.refresh(method1)
        payment_repo.db.refresh(method2)
        assert method1.is_default is False
        assert method2.is_default is True

    def test_delete_payment_method_by_stripe_id(self, payment_repo: PaymentRepository, test_user: User):
        """Delete using Stripe payment method ID."""
        stripe_id = f"pm_{ulid.ULID()}"
        payment_repo.save_payment_method(test_user.id, stripe_id, "4242", "visa")

        result = payment_repo.delete_payment_method(stripe_id, test_user.id)
        assert result is True
        assert payment_repo.get_payment_method_by_stripe_id(stripe_id, test_user.id) is None

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
            booking = create_booking_pg_safe(
                db,
                student_id=test_booking.student_id,
                instructor_id=test_booking.instructor_id,
                instructor_service_id=test_booking.instructor_service_id,
                booking_date=datetime.now().date() + timedelta(days=i + 1),
                start_time=time(14, 0),
                end_time=time(15, 0),
                service_name="Test Service",
                hourly_rate=50.00,
                total_price=50.00,
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
                offset_index=i,
            )

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

    def test_get_platform_revenue_stats_handles_none_result(
        self, payment_repo: PaymentRepository, monkeypatch
    ):
        """Gracefully handle None query results."""
        class FakeQuery:
            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return None

        monkeypatch.setattr(payment_repo.db, "query", lambda *_args, **_kwargs: FakeQuery())
        stats = payment_repo.get_platform_revenue_stats()
        assert stats["payment_count"] == 0

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

    def test_get_instructor_earnings_date_filters(
        self, payment_repo: PaymentRepository, test_booking: Booking, test_instructor: tuple
    ):
        """Date filters should be applied when provided."""
        payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )

        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now() + timedelta(days=1)
        earnings = payment_repo.get_instructor_earnings(
            test_booking.instructor_id, start_date=start_date, end_date=end_date
        )
        assert earnings["booking_count"] == 1

    def test_get_instructor_earnings_handles_none_result(
        self, payment_repo: PaymentRepository, monkeypatch
    ):
        """Gracefully handle None query results."""
        class FakeQuery:
            def join(self, *_args, **_kwargs):
                return self

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return None

        monkeypatch.setattr(payment_repo.db, "query", lambda *_args, **_kwargs: FakeQuery())
        earnings = payment_repo.get_instructor_earnings("instructor-id")
        assert earnings["booking_count"] == 0

    def test_get_instructor_earnings_multiple_bookings(
        self, payment_repo: PaymentRepository, test_instructor: tuple, db: Session, test_user: User
    ):
        """Test instructor earnings with multiple bookings."""
        instructor_user, profile, instructor_service = test_instructor

        # Create multiple bookings and payments
        for i in range(3):
            booking = create_booking_pg_safe(
                db,
                student_id=test_user.id,
                instructor_id=instructor_user.id,
                instructor_service_id=instructor_service.id,
                booking_date=datetime.now().date(),
                start_time=time(14, 0),
                end_time=time(15, 0),
                service_name="Test Service",
                hourly_rate=50.00,
                total_price=50.00,
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
                offset_index=i,
            )

            payment_repo.create_payment_record(booking.id, f"pi_{ulid.ULID()}", 5000 + (i * 1000), 500, "succeeded")

        earnings = payment_repo.get_instructor_earnings(instructor_user.id)

        assert earnings["total_earned"] == 16500  # (5000-500) + (6000-500) + (7000-500)
        assert earnings["total_fees"] == 1500  # 500 * 3
        assert earnings["booking_count"] == 3
        assert earnings["average_earning"] == 5500.0

    def test_get_user_payment_history_filters_status_and_orders(
        self, payment_repo: PaymentRepository, test_user: User, test_instructor: tuple, db: Session
    ):
        """Return only succeeded/processing payments ordered by newest first."""
        instructor_user, _, instructor_service = test_instructor

        booking_1 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=1,
        )
        booking_2 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(11, 0),
            end_time=time(12, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=2,
        )
        booking_3 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(13, 0),
            end_time=time(14, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=3,
        )

        payment_1 = payment_repo.create_payment_record(
            booking_1.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )
        payment_2 = payment_repo.create_payment_record(
            booking_2.id, f"pi_{ulid.ULID()}", 6000, 600, "processing"
        )
        _payment_3 = payment_repo.create_payment_record(
            booking_3.id, f"pi_{ulid.ULID()}", 7000, 700, "requires_payment_method"
        )

        payment_1.created_at = datetime.now() - timedelta(days=2)
        payment_2.created_at = datetime.now()
        db.flush()

        history = payment_repo.get_user_payment_history(test_user.id, limit=10)
        assert [p.stripe_payment_intent_id for p in history] == [
            payment_2.stripe_payment_intent_id,
            payment_1.stripe_payment_intent_id,
        ]

    def test_get_instructor_payment_history_filters_and_limits(
        self, payment_repo: PaymentRepository, test_user: User, test_instructor: tuple, db: Session
    ):
        """Only succeeded payments should return, ordered newest-first."""
        instructor_user, _, instructor_service = test_instructor

        booking_1 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(15, 0),
            end_time=time(16, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=4,
        )
        booking_2 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(17, 0),
            end_time=time(18, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=5,
        )
        booking_3 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(19, 0),
            end_time=time(20, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=6,
        )

        older = payment_repo.create_payment_record(
            booking_1.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )
        newer = payment_repo.create_payment_record(
            booking_2.id, f"pi_{ulid.ULID()}", 6000, 600, "succeeded"
        )
        _processing = payment_repo.create_payment_record(
            booking_3.id, f"pi_{ulid.ULID()}", 7000, 700, "processing"
        )

        older.created_at = datetime.now() - timedelta(days=2)
        newer.created_at = datetime.now()
        db.flush()

        history = payment_repo.get_instructor_payment_history(instructor_user.id, limit=1)
        assert len(history) == 1
        assert history[0].stripe_payment_intent_id == newer.stripe_payment_intent_id

    # ========== Error Handling Tests ==========

    def test_create_customer_record_exception(self, payment_repo: PaymentRepository):
        """Test that repository exception is raised on database error."""
        with pytest.raises(RepositoryException):
            # Invalid user_id should cause foreign key constraint violation
            payment_repo.create_customer_record("invalid_user_id", f"cus_{ulid.ULID()}")

    # ========== Payment Event Tests (Phase 1.1) ==========

    def test_create_payment_event(self, payment_repo: PaymentRepository, db: Session, test_user: User):
        """Test creating a payment event."""
        # Create instructor profile and service first
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
        from app.models.subcategory import ServiceSubcategory

        # Create category, subcategory and catalog with unique slugs
        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Test Category",
            description="Test",
        )
        db.add(category)
        db.flush()

        subcategory = ServiceSubcategory(
            name="General",
            category_id=category.id,
            display_order=1,
        )
        db.add(subcategory)
        db.flush()

        catalog = ServiceCatalog(
            id=str(ulid.ULID()),
            subcategory_id=subcategory.id,
            name="Test Service",
            slug=f"test-service-{str(ulid.ULID())[:8]}",
            description="Test",
        )
        db.add(catalog)

        # Create instructor profile
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=test_user.id,
            bio="Test",
            years_experience=1,
        )
        db.add(profile)

        # Create instructor service
        service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=50.00,
            duration_options=[60],
            is_active=True,
        )
        db.add(service)
        db.flush()

        # Create a booking first
        booking = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=test_user.id,
            instructor_service_id=service.id,
            booking_date=datetime.now().date(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
        )

        # Create payment event
        event = payment_repo.create_payment_event(
            booking_id=booking.id,
            event_type="setup_intent_created",
            event_data={"setup_intent_id": "seti_test123", "status": "requires_payment_method"},
        )

        assert event.id is not None
        assert event.booking_id == booking.id
        assert event.event_type == "setup_intent_created"
        assert event.event_data["setup_intent_id"] == "seti_test123"
        assert event.created_at is not None

    def test_get_payment_events_for_booking(self, payment_repo: PaymentRepository, db: Session, test_user: User):
        """Test retrieving all payment events for a booking."""
        # Create instructor profile and service first
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
        from app.models.subcategory import ServiceSubcategory

        # Create category, subcategory and catalog with unique slugs
        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Test Category",
            description="Test",
        )
        db.add(category)
        db.flush()

        subcategory = ServiceSubcategory(
            name="General",
            category_id=category.id,
            display_order=1,
        )
        db.add(subcategory)
        db.flush()

        catalog = ServiceCatalog(
            id=str(ulid.ULID()),
            subcategory_id=subcategory.id,
            name="Test Service",
            slug=f"test-service-{str(ulid.ULID())[:8]}",
            description="Test",
        )
        db.add(catalog)

        # Create instructor profile
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=test_user.id,
            bio="Test",
            years_experience=1,
        )
        db.add(profile)

        # Create instructor service
        service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=50.00,
            duration_options=[60],
            is_active=True,
        )
        db.add(service)
        db.flush()

        # Create a booking
        booking = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=test_user.id,
            instructor_service_id=service.id,
            booking_date=datetime.now().date(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
        )

        # Create multiple events
        events_data = [
            ("setup_intent_created", {"setup_intent_id": "seti_123"}),
            ("auth_scheduled", {"scheduled_for": "2024-01-01T10:00:00"}),
            ("auth_succeeded", {"payment_intent_id": "pi_123"}),
        ]

        for event_type, event_data in events_data:
            payment_repo.create_payment_event(booking.id, event_type, event_data)

        # Retrieve events
        events = payment_repo.get_payment_events_for_booking(booking.id)

        assert len(events) == 3
        assert events[0].event_type == "setup_intent_created"  # Ordered by creation time
        assert events[1].event_type == "auth_scheduled"
        assert events[2].event_type == "auth_succeeded"

    def test_get_latest_payment_event(self, payment_repo: PaymentRepository, db: Session, test_user: User):
        """Test retrieving the latest payment event."""
        # Create instructor profile and service first
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
        from app.models.subcategory import ServiceSubcategory

        # Create category, subcategory and catalog with unique slugs
        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Test Category",
            description="Test",
        )
        db.add(category)
        db.flush()

        subcategory = ServiceSubcategory(
            name="General",
            category_id=category.id,
            display_order=1,
        )
        db.add(subcategory)
        db.flush()

        catalog = ServiceCatalog(
            id=str(ulid.ULID()),
            subcategory_id=subcategory.id,
            name="Test Service",
            slug=f"test-service-{str(ulid.ULID())[:8]}",
            description="Test",
        )
        db.add(catalog)

        # Create instructor profile
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=test_user.id,
            bio="Test",
            years_experience=1,
        )
        db.add(profile)

        # Create instructor service
        service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=50.00,
            duration_options=[60],
            is_active=True,
        )
        db.add(service)
        db.flush()

        # Create a booking
        booking = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=test_user.id,
            instructor_service_id=service.id,
            booking_date=datetime.now().date(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
        )

        # Create events with small delays to ensure order
        _event1 = payment_repo.create_payment_event(booking.id, "setup_intent_created", {"step": 1})
        db.commit()
        _event2 = payment_repo.create_payment_event(booking.id, "auth_scheduled", {"step": 2})
        db.commit()
        latest_event = payment_repo.create_payment_event(booking.id, "auth_succeeded", {"step": 3})
        db.commit()

        # Get latest event
        result = payment_repo.get_latest_payment_event(booking.id)
        assert result is not None
        assert result.id == latest_event.id  # Verify we get the most recent event
        assert result.event_type == "auth_succeeded"
        assert result.event_data["step"] == 3

        # Get latest event of specific type
        result = payment_repo.get_latest_payment_event(booking.id, event_type="auth_scheduled")
        assert result.event_type == "auth_scheduled"
        assert result.event_data["step"] == 2

    # ========== Platform Credit Tests (Phase 1.3) ==========

    def test_create_platform_credit(self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking):
        """Test creating a platform credit."""
        credit = payment_repo.create_platform_credit(
            user_id=test_user.id,
            amount_cents=5000,  # $50
            reason="12-24 hour cancellation",
            source_booking_id=test_booking.id,
            expires_at=datetime.now() + timedelta(days=365),
        )

        assert credit.id is not None
        assert credit.user_id == test_user.id
        assert credit.amount_cents == 5000
        assert credit.reason == "12-24 hour cancellation"
        assert credit.used_at is None
        assert credit.is_available is True

    def test_create_platform_credit_default_expiry(self, payment_repo: PaymentRepository, test_user: User):
        """Test default expiry is set to ~1 year when not provided."""
        from datetime import timezone

        before = datetime.now(timezone.utc)
        credit = payment_repo.create_platform_credit(
            user_id=test_user.id,
            amount_cents=1000,
            reason="Default expiry test",
            expires_at=None,
        )
        assert credit.expires_at is not None
        # Approximately one year in future (allow small deltas)
        delta_days = (credit.expires_at - before).days
        assert 360 <= delta_days <= 370

    def test_apply_credits_for_booking_full_and_partial(
        self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking
    ):
        """Test reserving multiple credits, including creating a remainder credit when needed."""
        # Create two credits: 3000 and 1000 cents
        c1 = payment_repo.create_platform_credit(user_id=test_user.id, amount_cents=3000, reason="c1", expires_at=None)
        c2 = payment_repo.create_platform_credit(user_id=test_user.id, amount_cents=1000, reason="c2", expires_at=None)

        # Apply against 3500 cents to cover fully with a remainder from c2
        result = payment_repo.apply_credits_for_booking(
            user_id=test_user.id, booking_id=test_booking.id, amount_cents=3500
        )

        assert result["applied_cents"] == 3500
        assert set(result["used_credit_ids"]) == {c1.id, c2.id}

        # Verify credits marked reserved
        payment_repo.db.refresh(c1)
        payment_repo.db.refresh(c2)
        assert c1.status == "reserved"
        assert c1.reserved_for_booking_id == test_booking.id
        assert c1.reserved_amount_cents == 3000
        assert c2.status == "reserved"
        assert c2.reserved_for_booking_id == test_booking.id
        assert c2.reserved_amount_cents == 500
        assert c2.amount_cents == 500

        # Remainder credit should exist for 1000-500=500 cents
        remainder_id = result["remainder_credit_id"]
        assert remainder_id is not None
        remainder = payment_repo.db.query(PlatformCredit).filter(PlatformCredit.id == remainder_id).first()
        assert remainder is not None
        assert remainder.amount_cents == 500
        assert remainder.status == "available"

    def test_apply_credits_noop_when_zero(
        self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking
    ):
        """Test no-op when amount is zero or negative."""
        result = payment_repo.apply_credits_for_booking(
            user_id=test_user.id, booking_id=test_booking.id, amount_cents=0
        )
        assert result["applied_cents"] == 0

    def test_get_applied_credit_cents_for_booking_prefers_credit_used(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """credit_used events should take precedence over legacy credits_applied."""
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"used_cents": 200},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"used_cents": "300"},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"used_cents": "bad"},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credits_applied",
            event_data={"applied_cents": 999},
        )

        assert payment_repo.get_applied_credit_cents_for_booking(test_booking.id) == 500

    def test_get_applied_credit_cents_for_booking_legacy_fallback(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """Legacy credits_applied should be summed when no credit_used events exist."""
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credits_applied",
            event_data={"applied_cents": 250},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credits_applied",
            event_data={"applied_cents": "350"},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credits_applied",
            event_data={"applied_cents": "bad"},
        )
        assert payment_repo.get_applied_credit_cents_for_booking(test_booking.id) == 600

    def test_get_credits_used_by_booking_filters_invalid(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """Only valid credit_used entries should be returned."""
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"credit_id": "c_1", "used_cents": 200},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"credit_id": "c_2", "used_cents": "bad"},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"credit_id": "c_4", "used_cents": None},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"credit_id": None, "used_cents": 300},
        )
        payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="credit_used",
            event_data={"credit_id": "c_3", "used_cents": -1},
        )

        used = payment_repo.get_credits_used_by_booking(test_booking.id)
        assert used == [("c_1", 200)]

    def test_get_available_credits(self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking):
        """Test retrieving available credits for a user."""
        # Create multiple credits
        future_date = datetime.now() + timedelta(days=30)
        past_date = datetime.now() - timedelta(days=1)

        # Available credit
        credit1 = payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=2000, reason="Credit 1", expires_at=future_date
        )

        # Another available credit (no expiration)
        credit2 = payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=3000, reason="Credit 2", expires_at=None
        )

        # Expired credit (should not be returned)
        _credit3 = payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=1000, reason="Expired", expires_at=past_date
        )

        # Used credit (should not be returned)
        credit4 = payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=1500, reason="Used", expires_at=future_date
        )
        payment_repo.mark_credit_used(credit4.id, test_booking.id)

        # Get available credits
        available = payment_repo.get_available_credits(test_user.id)

        assert len(available) == 2
        # Should be ordered FIFO by created_at
        assert available[0].id == credit1.id
        assert available[1].id == credit2.id

    def test_get_total_available_credits(self, payment_repo: PaymentRepository, test_user: User):
        """Test calculating total available credits."""
        future_date = datetime.now() + timedelta(days=30)

        # Create credits
        payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=2000, reason="Credit 1", expires_at=future_date
        )
        payment_repo.create_platform_credit(user_id=test_user.id, amount_cents=3000, reason="Credit 2", expires_at=None)

        # This should not be counted (expired)
        payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=1000, reason="Expired", expires_at=datetime.now() - timedelta(days=1)
        )

        total = payment_repo.get_total_available_credits(test_user.id)
        assert total == 5000  # 2000 + 3000

    def test_get_credits_issued_for_source_and_delete(
        self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking, db: Session
    ):
        """Credits for a source booking should return in created order and be deletable."""
        credit_1 = payment_repo.create_platform_credit(
            user_id=test_user.id,
            amount_cents=1000,
            reason="Source 1",
            source_booking_id=test_booking.id,
            expires_at=None,
        )
        credit_2 = payment_repo.create_platform_credit(
            user_id=test_user.id,
            amount_cents=2000,
            reason="Source 2",
            source_booking_id=test_booking.id,
            expires_at=None,
        )
        credit_1.created_at = datetime.now() - timedelta(days=1)
        credit_2.created_at = datetime.now()
        db.flush()

        issued = payment_repo.get_credits_issued_for_source(test_booking.id)
        assert [c.id for c in issued] == [credit_1.id, credit_2.id]

        payment_repo.delete_platform_credit(credit_1.id)
        remaining = payment_repo.get_credits_issued_for_source(test_booking.id)
        assert [c.id for c in remaining] == [credit_2.id]

    def test_delete_platform_credit_noop_when_missing(self, payment_repo: PaymentRepository) -> None:
        """Deleting a missing credit should be a no-op."""
        payment_repo.delete_platform_credit(str(ulid.ULID()))

    def test_mark_credit_used(self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking):
        """Test marking a credit as used."""
        # Create credit
        credit = payment_repo.create_platform_credit(
            user_id=test_user.id, amount_cents=2000, reason="Test credit", expires_at=None
        )

        assert credit.used_at is None
        assert credit.is_available is True

        # Mark as used
        updated_credit = payment_repo.mark_credit_used(credit.id, test_booking.id)

        assert updated_credit.used_at is not None
        assert updated_credit.used_booking_id == test_booking.id
        assert updated_credit.is_available is False

        # Trying to use again should raise exception
        with pytest.raises(RepositoryException, match="already used"):
            payment_repo.mark_credit_used(credit.id, test_booking.id)

    def test_mark_nonexistent_credit_used(self, payment_repo: PaymentRepository):
        """Test marking a non-existent credit as used."""
        with pytest.raises(RepositoryException, match="not found"):
            payment_repo.mark_credit_used(str(ulid.ULID()), str(ulid.ULID()))

    def test_save_payment_method_existing_no_default_change(
        self, payment_repo: PaymentRepository, test_user: User
    ):
        """Re-saving an existing method without default change should keep flags intact."""
        stripe_id = f"pm_{ulid.ULID()}"
        created = payment_repo.save_payment_method(test_user.id, stripe_id, "4242", "visa", is_default=False)

        updated = payment_repo.save_payment_method(test_user.id, stripe_id, "4242", "visa", is_default=False)

        assert updated.id == created.id
        assert updated.is_default is False

    def test_get_platform_revenue_stats_end_date_filter(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """End date filters should be applied when provided."""
        payment_repo.create_payment_record(
            test_booking.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )

        end_date = datetime.now() + timedelta(days=1)
        stats = payment_repo.get_platform_revenue_stats(end_date=end_date)

        assert stats["payment_count"] == 1

    def test_get_instructor_payment_history_without_limit(
        self, payment_repo: PaymentRepository, test_user: User, test_instructor: tuple, db: Session
    ):
        """Limit=0 should return all matching payments."""
        instructor_user, _, instructor_service = test_instructor

        booking_1 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=10,
        )
        booking_2 = create_booking_pg_safe(
            db,
            student_id=test_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=datetime.now().date(),
            start_time=time(11, 0),
            end_time=time(12, 0),
            service_name="Test Service",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            offset_index=11,
        )

        payment_repo.create_payment_record(
            booking_1.id, f"pi_{ulid.ULID()}", 5000, 500, "succeeded"
        )
        payment_repo.create_payment_record(
            booking_2.id, f"pi_{ulid.ULID()}", 6000, 600, "succeeded"
        )

        history = payment_repo.get_instructor_payment_history(instructor_user.id, limit=0)
        assert len(history) == 2

    def test_apply_credits_for_booking_breaks_when_remaining_zero(
        self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking
    ):
        """Credits beyond needed should be skipped once remaining is zero."""
        c1 = payment_repo.create_platform_credit(user_id=test_user.id, amount_cents=1000, reason="c1", expires_at=None)
        c2 = payment_repo.create_platform_credit(user_id=test_user.id, amount_cents=1000, reason="c2", expires_at=None)
        c3 = payment_repo.create_platform_credit(user_id=test_user.id, amount_cents=1000, reason="c3", expires_at=None)

        result = payment_repo.apply_credits_for_booking(
            user_id=test_user.id, booking_id=test_booking.id, amount_cents=1500
        )

        assert result["applied_cents"] == 1500
        assert set(result["used_credit_ids"]) == {c1.id, c2.id}

        payment_repo.db.refresh(c3)
        assert c3.status == "available"
        assert c3.reserved_for_booking_id is None

    def test_apply_credits_for_booking_no_available_credits(
        self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking
    ):
        """No available credits should result in zero applied and no events."""
        result = payment_repo.apply_credits_for_booking(
            user_id=test_user.id, booking_id=test_booking.id, amount_cents=500
        )

        assert result["applied_cents"] == 0
        assert result["used_credit_ids"] == []
        assert result["remainder_credit_id"] is None

        events = payment_repo.get_payment_events_for_booking(test_booking.id)
        assert events == []

    def test_apply_credits_for_booking_raises_repository_exception(
        self, payment_repo: PaymentRepository, test_user: User, test_booking: Booking, monkeypatch
    ):
        """Exceptions during credit application should be wrapped."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo, "get_available_credits", boom)

        with pytest.raises(RepositoryException):
            payment_repo.apply_credits_for_booking(
                user_id=test_user.id, booking_id=test_booking.id, amount_cents=500
            )

    def test_create_payment_event_handles_timestamp_failure(
        self, payment_repo: PaymentRepository, test_booking: Booking, monkeypatch
    ):
        """Timestamp assignment failure should not prevent event creation."""
        from app.repositories import payment_repository as payment_repo_module

        class BrokenDateTime:
            @staticmethod
            def now(_tz=None):
                raise RuntimeError("boom")

        monkeypatch.setattr(payment_repo_module, "datetime", BrokenDateTime)

        event = payment_repo.create_payment_event(
            booking_id=test_booking.id,
            event_type="auth_scheduled",
            event_data={"attempt": 1},
        )

        assert event.id is not None

    def test_create_payment_event_raises_repository_exception_on_db_error(
        self, payment_repo: PaymentRepository, test_booking: Booking, monkeypatch
    ):
        """Database errors should be wrapped in RepositoryException."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo.db, "add", boom)

        with pytest.raises(RepositoryException):
            payment_repo.create_payment_event(
                booking_id=test_booking.id,
                event_type="auth_failed",
                event_data={"error": "declined"},
            )

    def test_create_connected_account_record_raises_repository_exception_on_flush(
        self, payment_repo: PaymentRepository, monkeypatch
    ):
        """Flush errors should surface as RepositoryException."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo.db, "flush", boom)

        with pytest.raises(RepositoryException):
            payment_repo.create_connected_account_record("profile_id", "acct_test")

    def test_create_payment_record_raises_repository_exception_on_flush(
        self, payment_repo: PaymentRepository, monkeypatch
    ):
        """Flush errors should surface as RepositoryException."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo.db, "flush", boom)

        with pytest.raises(RepositoryException):
            payment_repo.create_payment_record("booking_id", "pi_test", 1000, 100, "succeeded")

    def test_record_payout_event_raises_repository_exception_on_flush(
        self, payment_repo: PaymentRepository, monkeypatch
    ):
        """Flush errors should surface as RepositoryException."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo.db, "flush", boom)

        with pytest.raises(RepositoryException):
            payment_repo.record_payout_event(
                instructor_profile_id="profile_id",
                stripe_account_id="acct_test",
                payout_id="po_test",
                amount_cents=1000,
                status="pending",
                arrival_date=None,
            )

    def test_create_platform_credit_raises_repository_exception_on_flush(
        self, payment_repo: PaymentRepository, monkeypatch
    ):
        """Flush errors should surface as RepositoryException."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo.db, "flush", boom)

        with pytest.raises(RepositoryException):
            payment_repo.create_platform_credit(
                user_id="user_id",
                amount_cents=1000,
                reason="test",
                expires_at=None,
            )

    # ========== Earnings Metadata Tests (Part 9) ==========

    def test_create_payment_record_stores_earnings_metadata(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """Test that earnings metadata is stored when provided."""
        from decimal import Decimal

        payment_intent_id = f"pi_{ulid.ULID()}"
        amount = 5600  # $56.00 in cents (includes 12% student fee)
        fee = 600  # $6.00 platform fee (12% of $50 lesson)

        payment = payment_repo.create_payment_record(
            test_booking.id,
            payment_intent_id,
            amount,
            fee,
            status="succeeded",
            base_price_cents=5000,  # $50.00 lesson price
            instructor_tier_pct=Decimal("0.12"),  # 12% tier
            instructor_payout_cents=4400,  # $44.00 to instructor
        )

        assert payment is not None
        assert payment.base_price_cents == 5000
        assert payment.instructor_tier_pct == Decimal("0.12")
        assert payment.instructor_payout_cents == 4400

        # Verify the data persists (re-fetch from DB)
        fetched = payment_repo.get_payment_by_intent_id(payment_intent_id)
        assert fetched is not None
        assert fetched.base_price_cents == 5000
        assert fetched.instructor_tier_pct == Decimal("0.12")
        assert fetched.instructor_payout_cents == 4400

    def test_create_payment_record_without_earnings_metadata(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """Test that payment records work without earnings metadata (legacy support)."""
        payment_intent_id = f"pi_{ulid.ULID()}"
        amount = 5000
        fee = 500

        payment = payment_repo.create_payment_record(
            test_booking.id,
            payment_intent_id,
            amount,
            fee,
            status="succeeded",
            # No earnings metadata provided
        )

        assert payment is not None
        assert payment.base_price_cents is None
        assert payment.instructor_tier_pct is None
        assert payment.instructor_payout_cents is None

    def test_create_payment_record_stores_founding_instructor_tier(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """Test that 8% founding instructor tier is stored correctly."""
        from decimal import Decimal

        payment_intent_id = f"pi_{ulid.ULID()}"

        payment = payment_repo.create_payment_record(
            test_booking.id,
            payment_intent_id,
            amount=5600,
            application_fee=400,  # 8% of $50 = $4
            status="succeeded",
            base_price_cents=5000,
            instructor_tier_pct=Decimal("0.08"),  # 8% founding rate
            instructor_payout_cents=4600,  # $50 - $4 = $46
        )

        assert payment.instructor_tier_pct == Decimal("0.08")
        assert payment.instructor_payout_cents == 4600

    def test_create_payment_record_stores_standard_instructor_tier(
        self, payment_repo: PaymentRepository, test_booking: Booking
    ):
        """Test that 12% standard instructor tier is stored correctly."""
        from decimal import Decimal

        payment_intent_id = f"pi_{ulid.ULID()}"

        payment = payment_repo.create_payment_record(
            test_booking.id,
            payment_intent_id,
            amount=5600,
            application_fee=600,  # 12% of $50 = $6
            status="succeeded",
            base_price_cents=5000,
            instructor_tier_pct=Decimal("0.12"),  # 12% standard rate
            instructor_payout_cents=4400,  # $50 - $6 = $44
        )

        assert payment.instructor_tier_pct == Decimal("0.12")
        assert payment.instructor_payout_cents == 4400

    @pytest.mark.parametrize(
        ("method_name", "args"),
        [
            ("get_customer_by_user_id", ("user_id",)),
            ("get_customer_by_stripe_id", ("cus_test",)),
            ("get_connected_account_by_instructor_id", ("profile_id",)),
            ("update_onboarding_status", ("acct_test", True)),
            ("update_payment_status", ("pi_test", "succeeded")),
            ("get_payment_by_intent_id", ("pi_test",)),
            ("get_payment_by_booking_id", ("booking_id",)),
            ("get_payment_intents_for_booking", ("booking_id",)),
            ("find_payment_by_booking_and_amount", ("booking_id", 1000)),
            ("get_payment_by_booking_prefix", ("book",)),
            ("get_instructor_payout_history", ("profile_id",)),
            ("get_connected_account_by_stripe_id", ("acct_test",)),
            ("save_payment_method", ("user_id", "pm_test", "4242", "visa")),
            ("get_payment_methods_by_user", ("user_id",)),
            ("get_default_payment_method", ("user_id",)),
            ("get_payment_method_by_stripe_id", ("pm_test", "user_id")),
            ("set_default_payment_method", ("pm_db_id", "user_id")),
            ("delete_payment_method", ("pm_test", "user_id")),
            ("get_platform_revenue_stats", ()),
            ("get_instructor_earnings", ("instructor_id",)),
            ("get_user_payment_history", ("user_id",)),
            ("get_instructor_payment_history", ("instructor_id",)),
            ("get_payment_events_for_booking", ("booking_id",)),
            ("get_latest_payment_event", ("booking_id",)),
            ("get_applied_credit_cents_for_booking", ("booking_id",)),
            ("get_available_credits", ("user_id",)),
            ("delete_platform_credit", ("credit_id",)),
            ("get_credits_issued_for_source", ("booking_id",)),
            ("get_credits_used_by_booking", ("booking_id",)),
            ("get_total_available_credits", ("user_id",)),
            ("mark_credit_used", ("credit_id", "booking_id")),
        ],
    )
    def test_repository_query_errors_raise_repository_exception(
        self, payment_repo: PaymentRepository, monkeypatch, method_name: str, args: tuple
    ):
        """All query failures should surface as RepositoryException."""
        def boom(*_args, **_kwargs):
            raise Exception("boom")

        monkeypatch.setattr(payment_repo.db, "query", boom)

        with pytest.raises(RepositoryException):
            getattr(payment_repo, method_name)(*args)
