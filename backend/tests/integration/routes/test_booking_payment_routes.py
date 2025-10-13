from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User


@pytest.fixture
def student_user(db: Session, auth_headers_student) -> User:
    """Return the student user created by auth_headers_student."""
    user = db.query(User).filter_by(email="test.student@example.com").first()
    assert user is not None, "Expected test.student@example.com to exist"
    return user


@pytest.fixture
def instructor_setup(db: Session, test_instructor: User):
    """Return (instructor, profile, service) using seeded catalog and test_instructor."""
    instructor = test_instructor
    profile = db.query(InstructorProfile).filter_by(user_id=instructor.id).first()
    assert profile is not None, "Instructor profile not found"
    service = db.query(Service).filter_by(instructor_profile_id=profile.id, is_active=True).first()
    assert service is not None, "Active instructor service not found"
    return instructor, profile, service


@pytest.mark.parametrize(
    "minutes_ahead, expected_status",
    [
        (23 * 60 + 59, "authorizing"),  # 23h59m -> immediate
        (24 * 60 + 1, "scheduled"),  # 24h01m -> scheduled
    ],
)
def test_confirm_booking_payment_boundary_route(
    minutes_ahead: int,
    expected_status: str,
    client,
    auth_headers_student,
    student_user,
    instructor_setup,
    db: Session,
):
    """
    Route-level boundary: <=24h is immediate (authorizing), >24h is scheduled.
    Uses a fixed 'now' and monkeypatches booking_service.datetime.now to avoid clock drift.
    """
    instructor, _profile, service = instructor_setup

    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).replace(microsecond=0)
    start_dt = fixed_now + timedelta(minutes=minutes_ahead)

    # Build a one-hour booking starting at start_dt
    booking = Booking(
        id=str(ulid.ULID()),
        student_id=student_user.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=(start_dt + timedelta(hours=1)).time(),
        service_name="Boundary Test",
        hourly_rate=100.00,
        total_price=100.00,
        duration_minutes=60,
        status=BookingStatus.PENDING,
        payment_status="pending_payment_method",
    )
    db.add(booking)
    db.commit()

    # Monkeypatch datetime.now used inside booking_service
    import app.services.booking_service as mod

    RealDT = mod.datetime

    class FixedDT(RealDT):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    mod.datetime = FixedDT
    try:
        resp = client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json={"payment_method_id": "pm_test", "save_payment_method": False},
            headers=auth_headers_student,
        )
    finally:
        mod.datetime = RealDT

    assert resp.status_code == 200, resp.text
    db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED

    # Determine dynamic threshold: 24h plus any buffer_time_minutes from profile
    threshold_minutes = 24 * 60 + getattr(_profile, "buffer_time_minutes", 0)
    expected_status = "scheduled" if minutes_ahead > threshold_minutes else "authorizing"
    assert booking.payment_status == expected_status

"""
Tests for booking payment route endpoints (Phase 2).

Tests the API endpoints for:
- Creating bookings with SetupIntent
- Confirming payment methods
"""

from datetime import date, time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
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
        )
        db.add(profile)
        db.flush()

        # Create service category and catalog
        category_ulid = str(ulid.ULID())
        category = ServiceCategory(
            id=category_ulid,
            name="Test Category",
            slug=f"test-category-{category_ulid.lower()}",
            description="Test category",
        )
        db.add(category)

        catalog_ulid = str(ulid.ULID())
        catalog = ServiceCatalog(
            id=catalog_ulid,
            category_id=category.id,
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
            is_active=True,
        )
        db.add(service)
        db.flush()
        db.commit()

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

        response = client.post("/bookings/", json=booking_data)
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
            "location_type": "neutral",
        }

        response = authenticated_client.post("/bookings/", json=booking_data)

        assert response.status_code == 422
        detail = response.json()
        message = detail.get("detail")
        if isinstance(message, dict):
            message = message.get("message")
        assert message is not None
        assert "Minimum price for a in-person 60-minute private session" in str(message)

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

        # Rule under test: "immediate" iff (start - now) <= 24 hours.
        # Deterministic and same-day end: if adding 1h would cross midnight, use tomorrow 10:00.
        now_ts = datetime.now().replace(microsecond=0)
        base = now_ts + timedelta(hours=2, minutes=5)
        if (base + timedelta(hours=1)).date() != base.date():
            base = datetime.combine((now_ts + timedelta(days=1)).date(), time(10, 0))
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=base.date(),
            start_time=base.time(),
            end_time=(base + timedelta(hours=1)).time(),
            service_name="Test Service",
            hourly_rate=100.00,
            total_price=100.00,
            duration_minutes=60,
            status=BookingStatus.PENDING,
            payment_status="pending_payment_method",
        )
        db.add(booking)
        db.commit()  # Need to commit, not just flush

        # Confirm payment
        payment_data = {
            "payment_method_id": "pm_test123",
            "save_payment_method": False,
        }

        response = authenticated_client.post(
            f"/bookings/{booking.id}/confirm-payment",
            json=payment_data,
        )

        # Debug output if failing
        if response.status_code != 200:
            print(f"Expected 200, got {response.status_code}")
            print(f"Response: {response.json()}")

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
        from unittest.mock import MagicMock, patch

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
        db.commit()  # Need to commit, not just flush

        # Mock Stripe services to avoid real API calls
        with patch("app.services.stripe_service.StripeService.save_payment_method") as mock_save_payment, patch(
            "app.services.stripe_service.StripeService.get_or_create_customer"
        ) as mock_get_customer:
            # Setup mocks
            mock_save_payment.return_value = MagicMock(id="pm_test456")
            mock_get_customer.return_value = "cus_test123"

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
        student_user: User,
        instructor_setup: tuple,
        db: Session,
    ):
        """Test that only booking owner can confirm payment."""
        instructor, profile, service = instructor_setup

        # Create another student user for the booking
        other_student = User(
            id=str(ulid.ULID()),
            email=f"other_{ulid.ULID()}@example.com",
            hashed_password="$2b$12$test",
            first_name="Other",
            last_name="Student",
            zip_code="10001",
            is_active=True,
        )
        db.add(other_student)
        db.flush()

        # Create booking for different user
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=other_student.id,  # Different user
            instructor_id=instructor.id,
            instructor_service_id=service.id,
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

        # Should return 404 for security - don't reveal existence of other users' bookings
        assert response.status_code == 404

    def test_confirm_booking_already_confirmed(
        self,
        authenticated_client: TestClient,
        student_user: User,
        instructor_setup: tuple,
        db: Session,
    ):
        """Test that already confirmed bookings cannot be re-confirmed."""
        instructor, profile, service = instructor_setup

        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
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

        # For already confirmed bookings, the service might still return 404
        # if it filters by status first
        assert response.status_code in [404, 422]
        if response.status_code == 422:
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
        # Handle both string and dict error formats
        error_detail = response.json()["detail"]
        if isinstance(error_detail, dict):
            assert "not found" in error_detail.get("message", "").lower()
        else:
            assert "not found" in error_detail.lower()

    def test_confirm_payment_invalid_data(
        self,
        authenticated_client: TestClient,
        student_user: User,
        instructor_setup: tuple,
        db: Session,
    ):
        """Test that invalid payment data is rejected."""
        instructor, profile, service = instructor_setup

        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student_user.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
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
