"""
Tests for payment API routes.

Comprehensive test suite verifying:
- All required payment endpoints exist
- Role-based access control
- Request/response validation
- Error handling
- Webhook endpoint functionality
"""

from datetime import datetime, time
from typing import Dict
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
import stripe
import ulid

from app.core.enums import RoleName
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User


class TestPaymentRoutes:
    """Test suite for payment API routes."""

    # ========== Endpoint Existence Tests ==========

    def test_all_required_endpoints_exist(self, client: TestClient):
        """Test that all required payment endpoints are registered."""
        # Get all registered routes
        from app.main import fastapi_app

        routes = [route.path for route in fastapi_app.routes if hasattr(route, "path")]

        # Define required endpoints
        required_endpoints = [
            # Instructor endpoints
            "/api/payments/connect/onboard",
            "/api/payments/connect/status",
            "/api/payments/connect/dashboard",
            "/api/payments/earnings",
            # Student endpoints
            "/api/payments/methods",
            "/api/payments/checkout",
            # Webhook endpoints
            "/api/payments/webhooks/stripe",
            "/webhooks/stripe/payment-events",
            "/webhooks/stripe/account-events",
            "/webhooks/stripe/test",
        ]

        # Check each endpoint exists
        missing_endpoints = []
        for endpoint in required_endpoints:
            if endpoint not in routes:
                missing_endpoints.append(endpoint)

        assert not missing_endpoints, f"Missing endpoints: {missing_endpoints}"

    def test_endpoint_methods(self, client: TestClient):
        """Test that endpoints have correct HTTP methods."""
        from app.main import fastapi_app

        # Collect all methods for each path
        path_methods = {}
        for route in fastapi_app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                path = route.path
                if path not in path_methods:
                    path_methods[path] = set()
                path_methods[path].update(route.methods)

        # Define expected methods for each endpoint
        expected_methods = {
            "/api/payments/connect/onboard": ["POST"],
            "/api/payments/connect/status": ["GET"],
            "/api/payments/connect/dashboard": ["GET"],
            "/api/payments/earnings": ["GET"],
            "/api/payments/methods": ["GET", "POST"],
            "/api/payments/checkout": ["POST"],
            "/api/payments/webhooks/stripe": ["POST"],
        }

        # Check each endpoint has expected methods
        for path, expected in expected_methods.items():
            assert path in path_methods, f"Endpoint {path} not found"
            actual = path_methods[path]
            for method in expected:
                assert method in actual, f"{path} missing {method} method (has {actual})"

    # ========== Authentication Tests ==========

    def test_instructor_endpoints_require_auth(self, client: TestClient):
        """Test that instructor endpoints require authentication."""
        instructor_endpoints = [
            ("/api/payments/connect/onboard", "POST"),
            ("/api/payments/connect/status", "GET"),
            ("/api/payments/connect/dashboard", "GET"),
            ("/api/payments/earnings", "GET"),
        ]

        for endpoint, method in instructor_endpoints:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json={})

            assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"{endpoint} should require authentication"

    def test_student_endpoints_require_auth(self, client: TestClient):
        """Test that student endpoints require authentication."""
        student_endpoints = [
            ("/api/payments/methods", "GET"),
            ("/api/payments/methods", "POST"),
            ("/api/payments/checkout", "POST"),
        ]

        for endpoint, method in student_endpoints:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json={})

            assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"{endpoint} should require authentication"

    def test_webhook_endpoint_no_auth(self, client: TestClient):
        """Test that webhook endpoint doesn't require authentication."""
        # Webhook should return 400 for missing signature, not 401
        response = client.post("/api/payments/webhooks/stripe", content="test")
        assert (
            response.status_code != status.HTTP_401_UNAUTHORIZED
        ), "Webhook endpoint should not require authentication"

    # ========== Role-Based Access Tests ==========

    @pytest.fixture
    def student_user(self, db: Session) -> User:
        """Create a test student user."""
        from app.services.permission_service import PermissionService

        user = User(
            id=str(ulid.ULID()),
            email=f"student_{ulid.ULID()}@test.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="Student",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign student role
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, RoleName.STUDENT)

        return user

    @pytest.fixture
    def instructor_user(self, db: Session) -> tuple[User, InstructorProfile]:
        """Create a test instructor user with profile."""
        from app.services.permission_service import PermissionService

        user = User(
            id=str(ulid.ULID()),
            email=f"instructor_{ulid.ULID()}@test.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="Instructor",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign instructor role
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, RoleName.INSTRUCTOR)

        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=user.id,
            bio="Test instructor",
            years_experience=5,
        )
        db.add(profile)
        db.flush()

        return user, profile

    @pytest.fixture
    def student_headers(self, student_user: User) -> dict:
        """Get auth headers for student user."""
        from app.auth import create_access_token

        student_token = create_access_token(data={"sub": student_user.email})
        return {"Authorization": f"Bearer {student_token}"}

    @pytest.fixture
    def instructor_headers(self, instructor_user: tuple) -> dict:
        """Get auth headers for instructor user."""
        from app.auth import create_access_token

        user, _ = instructor_user
        instructor_token = create_access_token(data={"sub": user.email})
        return {"Authorization": f"Bearer {instructor_token}"}

    def test_student_cannot_access_instructor_endpoints(
        self, client: TestClient, student_user: User, student_headers: dict, db: Session
    ):
        """Test that students cannot access instructor endpoints."""
        # Ensure user is committed to database
        db.commit()

        # Try to access instructor endpoints
        response = client.post(
            "/api/payments/connect/onboard",
            headers=student_headers,
        )
        # Should get 403 Forbidden due to role check
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_instructor_cannot_access_student_endpoints(
        self, client: TestClient, instructor_user: tuple, instructor_headers: dict, db: Session
    ):
        """Test that instructors cannot access student endpoints."""
        # Ensure user is committed to database
        db.commit()

        # Try to access student endpoints
        response = client.post(
            "/api/payments/methods",
            headers=instructor_headers,
            json={"payment_method_id": "pm_test", "set_as_default": False},
        )
        # Should get 403 Forbidden due to role check
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ========== Webhook Tests ==========

    def test_webhook_missing_signature(self, client: TestClient):
        """Test webhook endpoint with missing signature."""
        response = client.post(
            "/api/payments/webhooks/stripe",
            content='{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "signature" in response.json()["detail"].lower()

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.payments.settings")
    def test_webhook_with_valid_signature(
        self, mock_settings, mock_handle_event, mock_construct_event, client: TestClient, db: Session
    ):
        """Test webhook endpoint with valid signature."""
        # Mock webhook secrets configuration
        mock_settings.webhook_secrets = ["whsec_test_secret"]

        # Mock successful signature verification
        mock_construct_event.return_value = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test"}}}

        # Mock successful webhook handling
        mock_handle_event.return_value = {"success": True, "event_type": "payment_intent.succeeded"}

        response = client.post(
            "/api/payments/webhooks/stripe",
            content='{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json", "stripe-signature": "test_signature"},
        )

        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert response_data["status"] == "success"
        assert response_data["event_type"] == "payment_intent.succeeded"

        # Verify the event was processed
        mock_construct_event.assert_called_once()
        mock_handle_event.assert_called_once()

    @patch("stripe.Webhook.construct_event")
    @patch("app.routes.payments.settings")
    def test_webhook_invalid_signature(self, mock_settings, mock_construct_event, client: TestClient, db: Session):
        """Test webhook endpoint with invalid signature."""

        # Mock webhook secrets configuration
        mock_settings.webhook_secrets = ["whsec_test_secret"]

        # Mock invalid signature error
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", sig_header="invalid"
        )

        response = client.post(
            "/api/payments/webhooks/stripe",
            content='{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json", "stripe-signature": "invalid_signature"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "signature" in response.json()["detail"].lower()

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.payments.settings")
    def test_webhook_processing_error_returns_200(
        self, mock_settings, mock_handle_event, mock_construct_event, client: TestClient, db: Session
    ):
        """Test webhook returns 200 even on processing errors to prevent retries."""
        from app.core.exceptions import ServiceException

        # Mock webhook secrets configuration
        mock_settings.webhook_secrets = ["whsec_test_secret"]

        # Mock successful signature verification
        mock_construct_event.return_value = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test"}}}

        # Mock processing error (not signature error)
        mock_handle_event.side_effect = ServiceException("Processing error")

        response = client.post(
            "/api/payments/webhooks/stripe",
            content='{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json", "stripe-signature": "test_signature"},
        )

        # Should return 200 to prevent Stripe retries
        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert response_data["status"] == "error"
        assert response_data["event_type"] == "unknown"
        assert "error" in response_data["message"].lower()

    # ========== Response Format Tests ==========

    @patch("app.services.stripe_service.StripeService.check_account_status")
    def test_onboarding_status_response_format(
        self, mock_check_status, client: TestClient, instructor_user: tuple, instructor_headers: dict, db: Session
    ):
        """Test onboarding status endpoint returns correct format."""
        user, profile = instructor_user
        db.commit()

        mock_check_status.return_value = {
            "has_account": True,
            "onboarding_completed": True,
            "can_accept_payments": True,
            "details_submitted": True,
        }

        response = client.get("/api/payments/connect/status", headers=instructor_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check response format
        assert "has_account" in data
        assert "onboarding_completed" in data
        assert "charges_enabled" in data
        assert "requirements" in data
        assert isinstance(data["requirements"], list)

    @patch("app.services.stripe_service.StripeService.get_user_payment_methods")
    def test_payment_methods_list_format(
        self, mock_get_methods, client: TestClient, student_user: User, student_headers: dict, db: Session
    ):
        """Test payment methods list endpoint returns correct format."""
        db.commit()

        # Mock payment methods
        from app.models.payment import PaymentMethod

        mock_method = PaymentMethod(
            id=str(ulid.ULID()),
            user_id=student_user.id,
            stripe_payment_method_id="pm_test",
            last4="4242",
            brand="visa",
            is_default=True,
            created_at=datetime.now(),
        )
        mock_get_methods.return_value = [mock_method]

        response = client.get("/api/payments/methods", headers=student_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check response format
        assert isinstance(data, list)
        if data:
            method = data[0]
            assert "id" in method
            assert "last4" in method
            assert "brand" in method
            assert "is_default" in method
            assert "created_at" in method

    # ========== Error Handling Tests ==========

    def test_checkout_booking_not_found(
        self, client: TestClient, student_user: User, student_headers: dict, db: Session
    ):
        """Test checkout with non-existent booking."""
        db.commit()

        response = client.post(
            "/api/payments/checkout",
            headers=student_headers,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test", "save_payment_method": False},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_checkout_wrong_student(
        self, client: TestClient, student_user: User, student_headers: dict, instructor_user: tuple, db: Session
    ):
        """Test checkout with booking owned by different student."""
        db.commit()

        # Create booking for different student
        from app.services.permission_service import PermissionService

        other_student = User(
            id=str(ulid.ULID()),
            email=f"other_{ulid.ULID()}@test.com",
            hashed_password="hashed",
            first_name="Other",
            last_name="Student",
            zip_code="10001",
        )
        db.add(other_student)
        db.flush()

        # Assign student role
        permission_service = PermissionService(db)
        permission_service.assign_role(other_student.id, RoleName.STUDENT)

        # Use the instructor from the fixture
        instructor, instructor_profile = instructor_user


        now = datetime.now()

        # Create a minimal instructor service for the booking

        # Create category and service if needed
        unique_id = str(ulid.ULID())[:8]  # Use part of ULID for uniqueness
        category = ServiceCategory(
            id=str(ulid.ULID()), name="Test Category", slug=f"test-category-{unique_id}", description="Test"
        )
        db.add(category)

        service = ServiceCatalog(
            id=str(ulid.ULID()),
            category_id=category.id,
            name="Test Service",
            slug=f"test-service-{unique_id}",
            description="Test",
        )
        db.add(service)

        instructor_service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=instructor_profile.id,
            service_catalog_id=service.id,
            hourly_rate=50.00,
            is_active=True,
        )
        db.add(instructor_service)
        db.flush()

        booking = Booking(
            id=str(ulid.ULID()),
            student_id=other_student.id,  # Different student
            instructor_id=instructor.id,  # Use actual instructor from fixture
            instructor_service_id=instructor_service.id,  # Use actual service
            booking_date=now.date(),
            start_time=time(14, 0),  # 2:00 PM
            end_time=time(15, 0),  # 3:00 PM
            service_name="Test",
            hourly_rate=50.00,
            total_price=50.00,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        response = client.post(
            "/api/payments/checkout",
            headers=student_headers,
            json={"booking_id": booking.id, "payment_method_id": "pm_test", "save_payment_method": False},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "own bookings" in response.json()["detail"].lower()


class TestWebhookEndpoints:
    """Specific tests for webhook endpoints."""

    def test_stripe_webhooks_router_endpoints_exist(self, client: TestClient):
        """Test that stripe_webhooks router endpoints are registered."""
        from app.main import fastapi_app

        routes = [route.path for route in fastapi_app.routes if hasattr(route, "path")]

        webhook_endpoints = [
            "/webhooks/stripe/payment-events",
            "/webhooks/stripe/account-events",
            "/webhooks/stripe/test",
        ]

        for endpoint in webhook_endpoints:
            assert endpoint in routes, f"Missing webhook endpoint: {endpoint}"

    def test_webhook_test_endpoint(self, client: TestClient):
        """Test the webhook test endpoint."""
        response = client.get("/webhooks/stripe/test")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert "webhook" in data["message"].lower()

    def test_payment_events_webhook_endpoint(self, client: TestClient):
        """Test payment events webhook endpoint."""
        response = client.post(
            "/webhooks/stripe/payment-events",
            json={"type": "payment_intent.succeeded"},
            headers={"Content-Type": "application/json"},
        )

        # Should require signature
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_account_events_webhook_endpoint(self, client: TestClient):
        """Test account events webhook endpoint."""
        response = client.post(
            "/webhooks/stripe/account-events",
            json={"type": "account.updated"},
            headers={"Content-Type": "application/json"},
        )

        # Should require signature
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTransactionHistory:
    """Test cases for transaction history endpoint."""

    def test_get_transaction_history_authenticated(self, client: TestClient, auth_headers_student: Dict[str, str]):
        """Test getting transaction history as authenticated student."""
        response = client.get("/api/payments/transactions", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_transaction_history_unauthenticated(self, client: TestClient):
        """Test getting transaction history without authentication."""
        response = client.get("/api/payments/transactions")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_transaction_history_with_pagination(self, client: TestClient, auth_headers_student: Dict[str, str]):
        """Test getting transaction history with pagination parameters."""
        response = client.get("/api/payments/transactions?limit=10&offset=5", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10


class TestCreditBalance:
    """Test cases for credit balance endpoint."""

    def test_get_credit_balance_authenticated(self, client: TestClient, auth_headers_student: Dict[str, str]):
        """Test getting credit balance as authenticated student."""
        response = client.get("/api/payments/credits", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "available" in data
        assert "expires_at" in data
        assert "pending" in data
        assert isinstance(data["available"], (int, float))

    def test_get_credit_balance_unauthenticated(self, client: TestClient):
        """Test getting credit balance without authentication."""
        response = client.get("/api/payments/credits")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
