"""
Tests for booking payment route endpoints (Phase 2).

Tests the API endpoints for:
- Creating bookings with SetupIntent
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
import ulid

from app.core.enums import RoleName
from app.models.booking import Booking, BookingStatus
from app.models.booking_payment import BookingPayment
from app.models.instructor import InstructorProfile
from app.models.rbac import Role
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
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
        db.commit()  # Commit so the user is visible to other sessions
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
        )
        profile.min_advance_booking_hours = 0
        db.add(profile)
        db.flush()

        # Create service category, subcategory, and catalog
        category_ulid = str(ulid.ULID())
        category = ServiceCategory(
            id=category_ulid,
            name="Test Category",
            description="Test category",
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

        catalog_ulid = str(ulid.ULID())
        catalog = ServiceCatalog(
            id=catalog_ulid,
            subcategory_id=subcategory.id,
            name="Test Service",
            slug=f"test-service-{catalog_ulid.lower()}",
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
            offers_at_location=True,
            is_active=True,
        )
        db.add(service)
        db.flush()
        db.commit()

        return instructor, profile, service

    @pytest.fixture
    def auth_headers(self, student_user: User) -> dict:
        """Create real authentication headers for student user."""
        from app.auth import create_access_token

        token = create_access_token(data={"sub": student_user.email})
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture
    def authenticated_client(self, client: TestClient, auth_headers: dict) -> TestClient:
        """Attach Authorization headers so requests authenticate via bearer token."""
        client.headers.update(auth_headers)
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
        response = authenticated_client.post("/api/v1/bookings/", json=booking_data)

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
        bp_check = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
        assert bp_check is not None, "BookingPayment row should exist"
        assert bp_check.payment_status == "payment_method_required"
        assert bp_check.payment_intent_id is None

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

        response = authenticated_client.post("/api/v1/bookings/", json=booking_data)

        assert response.status_code == 422  # BusinessRuleException returns 422
        error_detail = response.json()["detail"]
        # Handle both string and dict error formats
        if isinstance(error_detail, dict):
            assert "Invalid duration" in error_detail.get("message", "")
        else:
            assert "Invalid duration" in error_detail

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

        response = client.post("/api/v1/bookings/", json=booking_data)
        assert response.status_code == 401

    def test_create_booking_rejects_price_below_floor(
        self,
        authenticated_client: TestClient,
        instructor_setup,
        db: Session,
        enable_price_floors,
    ):
        """Ensure booking creation is blocked when rate falls below the configured floor."""

        instructor, profile, service = instructor_setup
        service.hourly_rate = 75.00
        db.add(service)
        db.commit()

        tomorrow = date.today() + timedelta(days=1)
        booking_data = {
            "instructor_id": instructor.id,
            "instructor_service_id": service.id,
            "booking_date": tomorrow.isoformat(),
            "start_time": "14:00",
            "selected_duration": 60,
            "student_note": "Test booking",
            "meeting_location": "Central Park",
            "location_lat": 40.758,
            "location_lng": -73.985,
            "location_type": "instructor_location",
        }

        response = authenticated_client.post("/api/v1/bookings/", json=booking_data)

        assert response.status_code == 422
        detail = response.json()
        message = detail.get("detail")
        if isinstance(message, dict):
            message = message.get("message")
        assert message is not None
        assert "Minimum price for a in-person 60-minute private session" in str(message)
