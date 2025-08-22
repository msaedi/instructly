"""
Tests for BookingService payment functionality (Phase 2).

Tests the two-step booking flow:
1. Create booking with SetupIntent
2. Confirm payment method and schedule authorization
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
import ulid
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentEvent
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService


class TestBookingPaymentService:
    """Test suite for BookingService payment functionality."""

    @pytest.fixture
    def student_user(self, db: Session) -> User:
        """Create a test student user."""
        user = User(
            id=str(ulid.ULID()),
            email=f"student_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="Student",
            zip_code="10001",
        )
        db.add(user)
        db.flush()
        return user

    @pytest.fixture
    def instructor_setup(self, db: Session) -> tuple[User, InstructorProfile, InstructorService]:
        """Create instructor with profile and service."""
        # Create instructor user
        instructor = User(
            id=str(ulid.ULID()),
            email=f"instructor_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="Instructor",
            zip_code="10001",
        )
        db.add(instructor)
        db.flush()

        # Create instructor profile
        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=instructor.id,
            bio="Test instructor",
            years_experience=5,
            accepts_instant_booking=True,
        )
        db.add(profile)
        db.flush()

        # Create service category and catalog
        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Test Category",
            slug="test-category",
            description="Test category",
        )
        db.add(category)
        db.flush()

        catalog = ServiceCatalog(
            id=str(ulid.ULID()),
            category_id=category.id,
            name="Test Service",
            slug="test-service",
            description="Test service",
        )
        db.add(catalog)
        db.flush()

        # Create instructor service
        service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=100.00,
            duration_options=[30, 60, 90],
            is_active=True,
        )
        db.add(service)
        db.flush()

        return instructor, profile, service

    @pytest.fixture
    def booking_service(self, db: Session) -> BookingService:
        """Create BookingService instance."""
        return BookingService(db)

    @pytest.fixture
    def booking_data(self, instructor_setup) -> BookingCreate:
        """Create sample booking data."""
        instructor, profile, service = instructor_setup
        tomorrow = date.today() + timedelta(days=1)

        return BookingCreate(
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=time(14, 0),  # 2 PM
            selected_duration=60,
            student_note="Test booking",
        )

    # ========== Phase 2.1: SetupIntent Flow Tests ==========

    @patch("stripe.SetupIntent.create")
    @patch("app.services.stripe_service.StripeService.get_or_create_customer")
    async def test_create_booking_with_payment_setup(
        self,
        mock_get_customer,
        mock_setup_intent,
        booking_service: BookingService,
        student_user: User,
        booking_data: BookingCreate,
        db: Session,
    ):
        """Test creating a booking with payment setup."""
        # Mock Stripe customer
        mock_customer = MagicMock()
        mock_customer.stripe_customer_id = "cus_test123"
        mock_get_customer.return_value = mock_customer

        # Mock SetupIntent
        mock_intent = MagicMock()
        mock_intent.id = "seti_test123"
        mock_intent.client_secret = "seti_test123_secret"
        mock_intent.status = "requires_payment_method"
        mock_setup_intent.return_value = mock_intent

        # Create booking
        booking = await booking_service.create_booking_with_payment_setup(
            student=student_user,
            booking_data=booking_data,
            selected_duration=60,
        )

        # Verify booking created with PENDING status
        assert booking.id is not None
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_status == "pending_payment_method"
        assert booking.payment_intent_id == "seti_test123"
        assert hasattr(booking, "setup_intent_client_secret")
        assert booking.setup_intent_client_secret == "seti_test123_secret"

        # Verify SetupIntent was created with correct params
        mock_setup_intent.assert_called_once()
        call_args = mock_setup_intent.call_args[1]
        assert call_args["customer"] == "cus_test123"
        assert call_args["payment_method_types"] == ["card"]
        assert call_args["usage"] == "off_session"
        assert call_args["metadata"]["booking_id"] == booking.id
        assert call_args["metadata"]["amount_cents"] == 10000  # $100

        # Verify payment event was created
        payment_events = db.query(PaymentEvent).filter_by(booking_id=booking.id).all()
        assert len(payment_events) == 1
        assert payment_events[0].event_type == "setup_intent_created"
        assert payment_events[0].event_data["setup_intent_id"] == "seti_test123"

    async def test_create_booking_with_invalid_duration(
        self,
        booking_service: BookingService,
        student_user: User,
        booking_data: BookingCreate,
    ):
        """Test that invalid duration is rejected."""
        with pytest.raises(ValidationException, match="Invalid duration"):
            await booking_service.create_booking_with_payment_setup(
                student=student_user,
                booking_data=booking_data,
                selected_duration=120,  # Not in duration_options
            )

    # ========== Phase 2.2: Payment Confirmation Tests ==========

    async def test_confirm_booking_payment_immediate_auth(
        self,
        booking_service: BookingService,
        student_user: User,
        instructor_setup,
        db: Session,
    ):
        """Test confirming payment for a booking within 24 hours."""
        instructor, profile, service = instructor_setup

        # Create a booking for 2 hours from now (immediate auth needed)
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=(datetime.now() + timedelta(hours=2)).time(),
            end_time=(datetime.now() + timedelta(hours=3)).time(),
            service_name="Test Service",
            hourly_rate=100.00,
            total_price=100.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
            payment_status="pending_payment_method",
        )
        db.add(booking)
        db.flush()

        # Confirm payment
        confirmed_booking = await booking_service.confirm_booking_payment(
            booking_id=booking.id,
            student=student_user,
            payment_method_id="pm_test123",
            save_payment_method=False,
        )

        # Verify booking updated correctly
        assert confirmed_booking.status == BookingStatus.CONFIRMED
        assert confirmed_booking.payment_method_id == "pm_test123"
        assert confirmed_booking.payment_status == "authorizing"
        assert confirmed_booking.confirmed_at is not None

        # Verify immediate auth event created
        auth_event = db.query(PaymentEvent).filter_by(booking_id=booking.id, event_type="auth_immediate").first()
        assert auth_event is not None
        assert auth_event.event_data["payment_method_id"] == "pm_test123"
        assert auth_event.event_data["scheduled_for"] == "immediate"

    async def test_confirm_booking_payment_scheduled_auth(
        self,
        booking_service: BookingService,
        student_user: User,
        instructor_setup,
        db: Session,
    ):
        """Test confirming payment for a booking >24 hours away."""
        instructor, profile, service = instructor_setup

        # Create a booking for 3 days from now (scheduled auth)
        future_date = date.today() + timedelta(days=3)
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=future_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test Service",
            hourly_rate=100.00,
            total_price=100.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
            payment_status="pending_payment_method",
        )
        db.add(booking)
        db.flush()

        # Confirm payment
        confirmed_booking = await booking_service.confirm_booking_payment(
            booking_id=booking.id,
            student=student_user,
            payment_method_id="pm_test456",
            save_payment_method=False,
        )

        # Verify booking updated correctly
        assert confirmed_booking.status == BookingStatus.CONFIRMED
        assert confirmed_booking.payment_method_id == "pm_test456"
        assert confirmed_booking.payment_status == "scheduled"

        # Verify scheduled auth event created
        scheduled_event = db.query(PaymentEvent).filter_by(booking_id=booking.id, event_type="auth_scheduled").first()
        assert scheduled_event is not None
        assert scheduled_event.event_data["payment_method_id"] == "pm_test456"

        # Verify scheduled time is ~24 hours before lesson
        scheduled_time = datetime.fromisoformat(scheduled_event.event_data["scheduled_for"])
        lesson_time = datetime.combine(future_date, time(14, 0))
        time_diff = lesson_time - scheduled_time
        assert 23.5 * 3600 < time_diff.total_seconds() < 24.5 * 3600  # Within 30 min of 24 hours

    async def test_confirm_booking_payment_not_owner(
        self,
        booking_service: BookingService,
        student_user: User,
        db: Session,
    ):
        """Test that only booking owner can confirm payment."""
        # Create another user
        other_user = User(
            id=str(ulid.ULID()),
            email=f"other_{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Other",
            last_name="User",
            zip_code="10001",
        )
        db.add(other_user)

        # Create booking for the other user
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=other_user.id,
            instructor_id=str(ulid.ULID()),
            instructor_service_id=str(ulid.ULID()),
            booking_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.flush()

        # Try to confirm as different user
        with pytest.raises(ValidationException, match="your own bookings"):
            await booking_service.confirm_booking_payment(
                booking_id=booking.id,
                student=student_user,  # Wrong user
                payment_method_id="pm_test",
                save_payment_method=False,
            )

    async def test_confirm_booking_payment_wrong_status(
        self,
        booking_service: BookingService,
        student_user: User,
        db: Session,
    ):
        """Test that only PENDING bookings can be confirmed."""
        # Create confirmed booking
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=str(ulid.ULID()),
            instructor_service_id=str(ulid.ULID()),
            booking_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,  # Already confirmed
        )
        db.add(booking)
        db.flush()

        # Try to confirm already confirmed booking
        with pytest.raises(ValidationException, match="Cannot confirm payment"):
            await booking_service.confirm_booking_payment(
                booking_id=booking.id,
                student=student_user,
                payment_method_id="pm_test",
                save_payment_method=False,
            )

    async def test_confirm_nonexistent_booking(
        self,
        booking_service: BookingService,
        student_user: User,
    ):
        """Test confirming payment for non-existent booking."""
        with pytest.raises(NotFoundException):
            await booking_service.confirm_booking_payment(
                booking_id=str(ulid.ULID()),
                student=student_user,
                payment_method_id="pm_test",
                save_payment_method=False,
            )

    @patch("app.services.stripe_service.StripeService.save_payment_method")
    async def test_confirm_booking_with_save_payment(
        self,
        mock_save_payment,
        booking_service: BookingService,
        student_user: User,
        db: Session,
    ):
        """Test saving payment method during confirmation."""
        # Create booking
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=str(ulid.ULID()),
            instructor_service_id=str(ulid.ULID()),
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name="Test",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.flush()

        # Confirm with save_payment_method=True
        await booking_service.confirm_booking_payment(
            booking_id=booking.id,
            student=student_user,
            payment_method_id="pm_save_test",
            save_payment_method=True,
        )

        # Verify save_payment_method was called
        mock_save_payment.assert_called_once_with(
            user_id=student_user.id,
            payment_method_id="pm_save_test",
            set_as_default=False,
        )
