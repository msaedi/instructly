"""
Tests for booking payment route endpoints (Phase 2).

Tests the API endpoints for:
- Creating bookings with SetupIntent
- Confirming payment methods
"""

from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

import pytest
import ulid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.rbac import Role
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User


class TestBookingPaymentRoutes:
    """Test suite for booking payment API endpoints."""

    @pytest.fixture
    def student_user(self, db: Session) -> User:
        """Create a test student user with role."""
        # Create student role
        student_role = db.query(Role).filter_by(name=RoleName.STUDENT).first()
        if not student_role:
            student_role = Role(
                id=str(ulid.ULID()),
                name=RoleName.STUDENT,
                description="Student role",
            )
            db.add(student_role)
            db.flush()

        # Create user
        user = User(
            id=str(ulid.ULID()),
            email=f"student_{ulid.ULID()}@example.com",
            hashed_password="$2b$12$test",  # Mock hashed password
            first_name="Test",
            last_name="Student",
            zip_code="10001",
            is_active=True,
        )
        user.roles.append(student_role)
        db.add(user)
        db.flush()
        return user

    @pytest.fixture
    def instructor_setup(self, db: Session) -> tuple[User, InstructorProfile, InstructorService]:
        """Create instructor with profile and service."""
        # Create instructor role
        instructor_role = db.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
        if not instructor_role:
            instructor_role = Role(
                id=str(ulid.ULID()),
                name=RoleName.INSTRUCTOR,
                description="Instructor role",
            )
            db.add(instructor_role)
            db.flush()

        # Create instructor user
        instructor = User(
            id=str(ulid.ULID()),
            email=f"instructor_{ulid.ULID()}@example.com",
            hashed_password="$2b$12$test",
            first_name="Test",
            last_name="Instructor",
            zip_code="10001",
            is_active=True,
        )
        instructor.roles.append(instructor_role)
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
    def auth_headers(self, student_user: User) -> dict:
        """Create authentication headers for student user."""
        # Mock JWT token
        return {"Authorization": f"Bearer test_token_{student_user.id}"}

    @pytest.fixture
    def authenticated_client(self, client: TestClient, student_user: User, auth_headers: dict) -> TestClient:
        """Create authenticated test client."""
        # Mock the authentication dependency
        from app.api.dependencies import get_current_active_user

        async def mock_get_user():
            return student_user

        client.app.dependency_overrides[get_current_active_user] = mock_get_user
        return client

    # ========== POST /bookings/ Tests (Create with SetupIntent) ==========

    @patch("stripe.SetupIntent.create")
    @patch("app.services.stripe_service.StripeService.get_or_create_customer")
    def test_create_booking_with_payment_setup(
        self,
        mock_get_customer,
        mock_setup_intent,
        authenticated_client: TestClient,
        student_user: User,
        instructor_setup,
        db: Session,
    ):
        """Test creating a booking returns SetupIntent client_secret."""
        instructor, profile, service = instructor_setup

        # Mock Stripe customer
        mock_customer = MagicMock()
        mock_customer.stripe_customer_id = "cus_test123"
        mock_get_customer.return_value = mock_customer

        # Mock SetupIntent
        mock_intent = MagicMock()
        mock_intent.id = "seti_test123"
        mock_intent.client_secret = "seti_test123_secret_key"
        mock_intent.status = "requires_payment_method"
        mock_setup_intent.return_value = mock_intent

        # Prepare booking data
        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": instructor.id,
            "instructor_service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "14:00",
            "selected_duration": 60,
            "student_note": "Test booking",
        }

        # Create booking
        response = authenticated_client.post("/bookings/", json=booking_data)

        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert data["status"] == "PENDING"
        assert data["setup_intent_client_secret"] == "seti_test123_secret_key"
        assert data["requires_payment_method"] is True

        # Verify booking in database
        booking = db.query(Booking).filter_by(id=data["id"]).first()
        assert booking is not None
        assert booking.status == BookingStatus.PENDING
        assert booking.payment_status == "pending_payment_method"
        assert booking.payment_intent_id == "seti_test123"

    def test_create_booking_invalid_duration(
        self,
        authenticated_client: TestClient,
        instructor_setup,
    ):
        """Test that invalid duration is rejected."""
        instructor, profile, service = instructor_setup

        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": instructor.id,
            "instructor_service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "14:00",
            "selected_duration": 120,  # Not in duration_options
            "student_note": "Test booking",
        }

        response = authenticated_client.post("/bookings/", json=booking_data)

        assert response.status_code == 422
        assert "Invalid duration" in response.json()["detail"]

    def test_create_booking_unauthenticated(
        self,
        client: TestClient,
        instructor_setup,
    ):
        """Test that unauthenticated requests are rejected."""
        instructor, profile, service = instructor_setup

        booking_data = {
            "instructor_id": instructor.id,
            "instructor_service_id": service.id,
            "booking_date": date.today().isoformat(),
            "start_time": "14:00",
            "selected_duration": 60,
        }

        response = client.post("/bookings/", json=booking_data)
        assert response.status_code == 401

    # ========== POST /bookings/{id}/confirm-payment Tests ==========

    def test_confirm_booking_payment_immediate(
        self,
        authenticated_client: TestClient,
        student_user: User,
        instructor_setup,
        db: Session,
    ):
        """Test confirming payment for booking within 24 hours."""
        instructor, profile, service = instructor_setup

        # Create pending booking for 2 hours from now
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
        payment_data = {
            "payment_method_id": "pm_test123",
            "save_payment_method": False,
        }

        response = authenticated_client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json=payment_data,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert data["id"] == booking.id
        assert data["status"] == "CONFIRMED"

        # Verify booking updated
        db.refresh(booking)
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.payment_method_id == "pm_test123"
        assert booking.payment_status == "authorizing"

    def test_confirm_booking_payment_scheduled(
        self,
        authenticated_client: TestClient,
        student_user: User,
        instructor_setup,
        db: Session,
    ):
        """Test confirming payment for booking >24 hours away."""
        instructor, profile, service = instructor_setup

        # Create pending booking for 3 days from now
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
        payment_data = {
            "payment_method_id": "pm_test456",
            "save_payment_method": True,
        }

        response = authenticated_client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json=payment_data,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert data["status"] == "CONFIRMED"

        # Verify booking updated
        db.refresh(booking)
        assert booking.payment_status == "scheduled"

    def test_confirm_booking_not_owner(
        self,
        authenticated_client: TestClient,
        db: Session,
    ):
        """Test that only booking owner can confirm payment."""
        # Create booking for different user
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=str(ulid.ULID()),  # Different user
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

        payment_data = {
            "payment_method_id": "pm_test",
            "save_payment_method": False,
        }

        response = authenticated_client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json=payment_data,
        )

        assert response.status_code == 422
        assert "your own bookings" in response.json()["detail"]

    def test_confirm_booking_already_confirmed(
        self,
        authenticated_client: TestClient,
        student_user: User,
        db: Session,
    ):
        """Test that already confirmed bookings cannot be re-confirmed."""
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

        payment_data = {
            "payment_method_id": "pm_test",
            "save_payment_method": False,
        }

        response = authenticated_client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json=payment_data,
        )

        assert response.status_code == 422
        assert "Cannot confirm payment" in response.json()["detail"]

    def test_confirm_booking_not_found(
        self,
        authenticated_client: TestClient,
    ):
        """Test confirming non-existent booking."""
        payment_data = {
            "payment_method_id": "pm_test",
            "save_payment_method": False,
        }

        response = authenticated_client.post(
            f"/bookings/{ulid.ULID()}/confirm-payment",
            json=payment_data,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_confirm_payment_invalid_data(
        self,
        authenticated_client: TestClient,
        student_user: User,
        db: Session,
    ):
        """Test that invalid payment data is rejected."""
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
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.flush()

        # Missing payment_method_id
        payment_data = {
            "save_payment_method": False,
        }

        response = authenticated_client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json=payment_data,
        )

        assert response.status_code == 422
        assert "payment_method_id" in str(response.json()["detail"])
