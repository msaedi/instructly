"""
Tests for payment API routes.

Comprehensive test suite verifying:
- All required payment endpoints exist
- Role-based access control
- Request/response validation
- Error handling
- Webhook endpoint functionality
"""

from datetime import date, datetime, time
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, call, patch
from urllib.parse import urljoin

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request
import stripe
import ulid

from app.core.enums import RoleName
from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.schemas.payment_schemas import CheckoutResponse

HTTP_422_STATUS = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


class _DummySecret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


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
            "/api/v1/payments/connect/onboard",
            "/api/v1/payments/connect/status",
            "/api/v1/payments/connect/dashboard",
            "/api/v1/payments/earnings",
            "/api/v1/payments/earnings/export",
            "/api/v1/payments/payouts",
            # Student endpoints
            "/api/v1/payments/methods",
            "/api/v1/payments/checkout",
            # Webhook endpoints (unified in v1)
            "/api/v1/payments/webhooks/stripe",
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
            "/api/v1/payments/connect/onboard": ["POST"],
            "/api/v1/payments/connect/status": ["GET"],
            "/api/v1/payments/connect/dashboard": ["GET"],
            "/api/v1/payments/earnings": ["GET"],
            "/api/v1/payments/earnings/export": ["POST"],
            "/api/v1/payments/payouts": ["GET"],
            "/api/v1/payments/methods": ["GET", "POST"],
            "/api/v1/payments/checkout": ["POST"],
            "/api/v1/payments/webhooks/stripe": ["POST"],
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
            ("/api/v1/payments/connect/onboard", "POST"),
            ("/api/v1/payments/connect/status", "GET"),
            ("/api/v1/payments/connect/dashboard", "GET"),
            ("/api/v1/payments/earnings", "GET"),
            ("/api/v1/payments/earnings/export", "POST"),
            ("/api/v1/payments/payouts", "GET"),
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
            ("/api/v1/payments/methods", "GET"),
            ("/api/v1/payments/methods", "POST"),
            ("/api/v1/payments/checkout", "POST"),
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
        response = client.post("/api/v1/payments/webhooks/stripe", content="test")
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
            "/api/v1/payments/connect/onboard",
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
            "/api/v1/payments/methods",
            headers=instructor_headers,
            json={"payment_method_id": "pm_test", "set_as_default": False},
        )
        # Should get 403 Forbidden due to role check
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ========== Webhook Tests ==========

    def test_webhook_missing_signature(self, client: TestClient):
        """Test webhook endpoint with missing signature."""
        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content='{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "signature" in response.json()["detail"].lower()

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.v1.payments.settings")
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
            "/api/v1/payments/webhooks/stripe",
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
    @patch("app.routes.v1.payments.settings")
    def test_webhook_invalid_signature(self, mock_settings, mock_construct_event, client: TestClient, db: Session):
        """Test webhook endpoint with invalid signature."""

        # Mock webhook secrets configuration
        mock_settings.webhook_secrets = ["whsec_test_secret"]

        # Mock invalid signature error
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", sig_header="invalid"
        )

        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content='{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json", "stripe-signature": "invalid_signature"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "signature" in response.json()["detail"].lower()

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.v1.payments.settings")
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
            "/api/v1/payments/webhooks/stripe",
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
        # Ensure a connected account exists so the handler exercises the live status path.
        from app.repositories.payment_repository import PaymentRepository

        PaymentRepository(db).create_connected_account_record(
            profile.id, "acct_test123", onboarding_completed=False
        )
        db.commit()

        mock_check_status.return_value = {
            "has_account": True,
            "onboarding_completed": True,
            # Prefer the canonical Stripe field name (regression guard)
            "charges_enabled": True,
            "details_submitted": True,
            "requirements": [],
        }

        response = client.get("/api/v1/payments/connect/status", headers=instructor_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check response format
        assert "has_account" in data
        assert "onboarding_completed" in data
        assert "charges_enabled" in data
        assert "requirements" in data
        assert isinstance(data["requirements"], list)
        assert data["charges_enabled"] is True

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

        response = client.get("/api/v1/payments/methods", headers=student_headers)

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
            "/api/v1/payments/checkout",
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
            "/api/v1/payments/checkout",
            headers=student_headers,
            json={"booking_id": booking.id, "payment_method_id": "pm_test", "save_payment_method": False},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "own bookings" in response.json()["detail"].lower()


class TestWebhookEndpoints:
    """Specific tests for webhook endpoints."""

    def test_stripe_webhooks_router_endpoints_exist(self, client: TestClient):
        """Test that stripe webhook endpoint is registered."""
        from app.main import fastapi_app

        routes = [route.path for route in fastapi_app.routes if hasattr(route, "path")]

        # V1 unified webhook endpoint
        webhook_endpoint = "/api/v1/payments/webhooks/stripe"
        assert webhook_endpoint in routes, f"Missing webhook endpoint: {webhook_endpoint}"

    def test_stripe_webhook_endpoint_requires_signature(self, client: TestClient):
        """Test that the unified Stripe webhook endpoint requires signature."""
        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content=b'{"type": "payment_intent.succeeded"}',
            headers={"Content-Type": "application/json"},
        )

        # Should require signature (returns 400 without valid Stripe-Signature header)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTransactionHistory:
    """Test cases for transaction history endpoint."""

    def test_get_transaction_history_authenticated(self, client: TestClient, auth_headers_student: Dict[str, str]):
        """Test getting transaction history as authenticated student."""
        response = client.get("/api/v1/payments/transactions", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_transaction_history_unauthenticated(self, client: TestClient):
        """Test getting transaction history without authentication."""
        response = client.get("/api/v1/payments/transactions")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_transaction_history_with_pagination(self, client: TestClient, auth_headers_student: Dict[str, str]):
        """Test getting transaction history with pagination parameters."""
        response = client.get("/api/v1/payments/transactions?limit=10&offset=5", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10


class TestCreditBalance:
    """Test cases for credit balance endpoint."""

    def test_get_credit_balance_authenticated(self, client: TestClient, auth_headers_student: Dict[str, str]):
        """Test getting credit balance as authenticated student."""
        response = client.get("/api/v1/payments/credits", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "available" in data
        assert "expires_at" in data
        assert "pending" in data
        assert isinstance(data["available"], (int, float))

    def test_get_credit_balance_unauthenticated(self, client: TestClient):
        """Test getting credit balance without authentication."""
        response = client.get("/api/v1/payments/credits")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPaymentMethodListErrors:
    """Tests for payment method list error handling."""

    def test_list_payment_methods_requires_student_role(
        self, client: TestClient, auth_headers_instructor: Dict[str, str]
    ):
        response = client.get("/api/v1/payments/methods", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("app.services.stripe_service.StripeService.get_user_payment_methods")
    def test_list_payment_methods_service_exception(
        self,
        mock_get_methods,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_get_methods.side_effect = ServiceException("List failed")

        response = client.get("/api/v1/payments/methods", headers=auth_headers_student)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("app.services.stripe_service.StripeService.get_user_payment_methods")
    def test_list_payment_methods_unexpected_exception(
        self,
        mock_get_methods,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_get_methods.side_effect = Exception("boom")

        response = client.get("/api/v1/payments/methods", headers=auth_headers_student)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCheckoutEndpoint:
    """Tests for POST /api/v1/payments/checkout."""

    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    def test_checkout_lock_contention_returns_429(
        self, mock_acquire_lock, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        mock_acquire_lock.return_value = False

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    @patch("app.routes.v1.payments.get_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    @patch("app.services.stripe_service.StripeService.create_booking_checkout")
    def test_checkout_returns_cached_response(
        self,
        mock_create_checkout,
        mock_acquire_lock,
        mock_get_cached,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_acquire_lock.return_value = True
        mock_get_cached.return_value = {
            "success": True,
            "payment_intent_id": "pi_cached",
            "status": "requires_capture",
            "amount": 12000,
            "application_fee": 1440,
            "client_secret": None,
            "requires_action": False,
        }

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payment_intent_id"] == "pi_cached"
        mock_create_checkout.assert_not_called()

    @patch("app.routes.v1.payments.release_lock", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.get_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    @patch("app.services.stripe_service.StripeService.create_booking_checkout")
    def test_checkout_service_exception_not_found(
        self,
        mock_create_checkout,
        mock_acquire_lock,
        mock_get_cached,
        mock_release_lock,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_acquire_lock.return_value = True
        mock_get_cached.return_value = None
        mock_create_checkout.side_effect = ServiceException("Booking not found", code="not_found")

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        mock_release_lock.assert_awaited_once()

    @patch("app.routes.v1.payments.release_lock", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.get_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    @patch("app.services.stripe_service.StripeService.create_booking_checkout")
    def test_checkout_service_exception_forbidden(
        self,
        mock_create_checkout,
        mock_acquire_lock,
        mock_get_cached,
        mock_release_lock,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_acquire_lock.return_value = True
        mock_get_cached.return_value = None
        mock_create_checkout.side_effect = ServiceException("Forbidden", code="forbidden")

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_release_lock.assert_awaited_once()

    @patch("app.routes.v1.payments.release_lock", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.get_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    @patch("app.services.stripe_service.StripeService.create_booking_checkout")
    def test_checkout_service_exception_defaults_to_400(
        self,
        mock_create_checkout,
        mock_acquire_lock,
        mock_get_cached,
        mock_release_lock,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_acquire_lock.return_value = True
        mock_get_cached.return_value = None
        mock_create_checkout.side_effect = ServiceException("Payment error", code="unknown")

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_release_lock.assert_awaited_once()

    @patch("app.routes.v1.payments.release_lock", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.get_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    @patch("app.services.stripe_service.StripeService.create_booking_checkout")
    def test_checkout_unexpected_exception_returns_500(
        self,
        mock_create_checkout,
        mock_acquire_lock,
        mock_get_cached,
        mock_release_lock,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_acquire_lock.return_value = True
        mock_get_cached.return_value = None
        mock_create_checkout.side_effect = Exception("boom")

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_release_lock.assert_awaited_once()

    @patch("app.routes.v1.payments.set_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.release_lock", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.get_cached", new_callable=AsyncMock)
    @patch("app.routes.v1.payments.acquire_lock", new_callable=AsyncMock)
    @patch("app.services.stripe_service.StripeService.create_booking_checkout")
    def test_checkout_cache_write_failure_does_not_break(
        self,
        mock_create_checkout,
        mock_acquire_lock,
        mock_get_cached,
        mock_release_lock,
        mock_set_cached,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_acquire_lock.return_value = True
        mock_get_cached.return_value = None
        mock_set_cached.side_effect = Exception("cache unavailable")
        mock_create_checkout.return_value = CheckoutResponse(
            success=True,
            payment_intent_id="pi_success",
            status="requires_capture",
            amount=12000,
            application_fee=1440,
            client_secret=None,
            requires_action=False,
        )

        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"booking_id": str(ulid.ULID()), "payment_method_id": "pm_test"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payment_intent_id"] == "pi_success"
        mock_set_cached.assert_awaited_once()
        mock_release_lock.assert_awaited_once()

    def test_checkout_validation_error_returns_422(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.post(
            "/api/v1/payments/checkout",
            headers=auth_headers_student,
            json={"requested_credit_cents": -1},
        )

        assert response.status_code == HTTP_422_STATUS


class TestOnboardingEndpoints:
    """Tests for Stripe Connect onboarding endpoints."""

    @patch("app.services.stripe_service.StripeService.start_instructor_onboarding")
    def test_start_onboarding_success(
        self,
        mock_start_onboarding,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_start_onboarding.return_value = {
            "account_id": "acct_test123",
            "onboarding_url": "https://stripe.test/onboard",
            "already_onboarded": False,
        }

        response = client.post(
            "/api/v1/payments/connect/onboard",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["account_id"] == "acct_test123"
        assert data["onboarding_url"].startswith("https://")
        mock_start_onboarding.assert_called_once()

    def test_onboarding_status_requires_instructor(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.get("/api/v1/payments/connect/status", headers=auth_headers_student)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("app.services.stripe_service.StripeService.set_instructor_payout_schedule")
    def test_set_payout_schedule_monthly_anchor(
        self,
        mock_set_schedule,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_set_schedule.return_value = {
            "ok": True,
            "account_id": "acct_test123",
            "settings": {"interval": "monthly", "monthly_anchor": 1},
        }

        response = client.post(
            "/api/v1/payments/connect/payout-schedule",
            headers=auth_headers_instructor,
            params={"interval": "monthly"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["ok"] is True
        kwargs = mock_set_schedule.call_args.kwargs
        assert kwargs["interval"] == "monthly"
        assert kwargs["monthly_anchor"] == 1

    def test_payout_schedule_requires_instructor(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.post(
            "/api/v1/payments/connect/payout-schedule",
            headers=auth_headers_student,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("app.services.stripe_service.StripeService.get_instructor_dashboard_link")
    def test_get_dashboard_link_success(
        self,
        mock_dashboard_link,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_dashboard_link.return_value = {
            "dashboard_url": "https://stripe.test/dashboard",
            "expires_in_minutes": 5,
        }

        response = client.get(
            "/api/v1/payments/connect/dashboard",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["dashboard_url"].startswith("https://")

    def test_dashboard_requires_instructor(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.get(
            "/api/v1/payments/connect/dashboard",
            headers=auth_headers_student,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestInstantPayoutEndpoints:
    """Tests for instant payout endpoints."""

    @patch("app.routes.v1.payments.prometheus_metrics")
    @patch("app.services.stripe_service.StripeService.request_instructor_instant_payout")
    def test_request_instant_payout_success(
        self,
        mock_request_payout,
        mock_metrics,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_request_payout.return_value = {"ok": True, "payout_id": "po_test", "status": "paid"}

        response = client.post(
            "/api/v1/payments/connect/instant-payout",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["ok"] is True
        assert mock_metrics.inc_instant_payout_request.call_args_list == [call("attempt")]

    @patch("app.routes.v1.payments.prometheus_metrics")
    @patch("app.services.stripe_service.StripeService.request_instructor_instant_payout")
    def test_request_instant_payout_http_exception(
        self,
        mock_request_payout,
        mock_metrics,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_request_payout.side_effect = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Not eligible"
        )

        response = client.post(
            "/api/v1/payments/connect/instant-payout",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert mock_metrics.inc_instant_payout_request.call_args_list == [
            call("attempt"),
            call("error"),
        ]

    @patch("app.routes.v1.payments.prometheus_metrics")
    @patch("app.services.stripe_service.StripeService.request_instructor_instant_payout")
    def test_request_instant_payout_generic_exception(
        self,
        mock_request_payout,
        mock_metrics,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_request_payout.side_effect = Exception("Stripe down")

        from app.main import fastapi_app

        with TestClient(fastapi_app, raise_server_exceptions=False) as test_client:
            response = test_client.post(
                "/api/v1/payments/connect/instant-payout",
                headers=auth_headers_instructor,
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert mock_metrics.inc_instant_payout_request.call_args_list == [
            call("attempt"),
            call("error"),
        ]


class TestEarningsAndPayoutsEndpoints:
    """Tests for earnings and payouts endpoints."""

    @patch("app.services.stripe_service.StripeService.get_instructor_earnings_summary")
    def test_earnings_returns_summary(
        self,
        mock_summary,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_summary.return_value = {
            "total_earned": 12000,
            "total_fees": 1440,
            "booking_count": 3,
            "average_earning": 4000.0,
            "invoices": [],
        }

        response = client.get("/api/v1/payments/earnings", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_earned"] == 12000
        assert data["booking_count"] == 3

    def test_earnings_requires_instructor_role(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.get("/api/v1/payments/earnings", headers=auth_headers_student)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("app.services.stripe_service.StripeService.get_instructor_payout_history")
    def test_payouts_returns_history(
        self,
        mock_history,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_history.return_value = {
            "payouts": [],
            "total_paid_cents": 0,
            "total_pending_cents": 0,
            "payout_count": 0,
        }

        response = client.get("/api/v1/payments/payouts", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["payout_count"] == 0

    def test_payouts_requires_instructor_role(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.get("/api/v1/payments/payouts", headers=auth_headers_student)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("limit", [0, -1, 101, 999999])
    def test_payouts_limit_validation(
        self,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
        limit: int,
    ):
        response = client.get(
            f"/api/v1/payments/payouts?limit={limit}",
            headers=auth_headers_instructor,
        )

        assert response.status_code == HTTP_422_STATUS


class TestEarningsExport:
    """Tests for earnings export endpoint."""

    @patch("app.services.stripe_service.StripeService.generate_earnings_csv")
    def test_export_returns_csv(
        self,
        mock_export,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_export.return_value = (
            "Date,Student,Service,Duration (min),Lesson Price,Platform Fee,Net Earnings,Status,Payment ID\n"
        )

        response = client.post(
            "/api/v1/payments/earnings/export",
            headers=auth_headers_instructor,
            json={},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert response.text.startswith("Date,Student,Service")

    @patch("app.services.stripe_service.StripeService.generate_earnings_pdf")
    def test_export_returns_pdf(
        self,
        mock_export,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_export.return_value = b"%PDF-1.4\n%EOF"

        response = client.post(
            "/api/v1/payments/earnings/export",
            headers=auth_headers_instructor,
            json={"format": "pdf"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"].startswith("application/pdf")
        assert "attachment" in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF-1.4")

    def test_export_requires_instructor_role(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.post(
            "/api/v1/payments/earnings/export",
            headers=auth_headers_student,
            json={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("app.services.stripe_service.StripeService.generate_earnings_csv")
    def test_export_with_date_range(
        self,
        mock_export,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_export.return_value = "Date,Student,Service\n"

        response = client.post(
            "/api/v1/payments/earnings/export",
            headers=auth_headers_instructor,
            json={"start_date": "2025-01-01", "end_date": "2025-01-31"},
        )

        assert response.status_code == status.HTTP_200_OK
        _, kwargs = mock_export.call_args
        assert kwargs["start_date"] == date(2025, 1, 1)
        assert kwargs["end_date"] == date(2025, 1, 31)

    @patch("app.services.stripe_service.StripeService.generate_earnings_csv")
    def test_export_csv_has_correct_columns(
        self,
        mock_export,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_export.return_value = (
            "Date,Student,Service,Duration (min),Lesson Price,Platform Fee,Net Earnings,Status,Payment ID\n"
        )

        response = client.post(
            "/api/v1/payments/earnings/export",
            headers=auth_headers_instructor,
            json={},
        )

        assert response.status_code == status.HTTP_200_OK
        first_line = response.text.split("\n")[0]
        assert "Date" in first_line
        assert "Student" in first_line
        assert "Lesson Price" in first_line
        assert "Platform Fee" in first_line
        assert "Net Earnings" in first_line

    @patch("app.services.stripe_service.StripeService.generate_earnings_csv")
    def test_export_empty_when_no_earnings(
        self,
        mock_export,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_export.return_value = (
            "Date,Student,Service,Duration (min),Lesson Price,Platform Fee,Net Earnings,Status,Payment ID\n"
        )

        response = client.post(
            "/api/v1/payments/earnings/export",
            headers=auth_headers_instructor,
            json={},
        )

        assert response.status_code == status.HTTP_200_OK
        lines = response.text.strip().split("\n")
        assert len(lines) >= 1


class TestPaymentMethodEndpoints:
    """Tests for payment method endpoints."""

    @patch("app.services.stripe_service.StripeService.get_or_create_customer")
    @patch("app.services.stripe_service.StripeService.save_payment_method")
    def test_save_payment_method_success(
        self,
        mock_save_method,
        mock_get_customer,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_get_customer.return_value = MagicMock()
        mock_save_method.return_value = MagicMock(
            stripe_payment_method_id="pm_saved",
            last4="4242",
            brand="visa",
            is_default=True,
            created_at=datetime.now(),
        )

        response = client.post(
            "/api/v1/payments/methods",
            headers=auth_headers_student,
            json={"payment_method_id": "pm_saved", "set_as_default": True},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == "pm_saved"

    @patch("app.services.stripe_service.StripeService.delete_payment_method")
    def test_delete_payment_method_success(
        self,
        mock_delete,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_delete.return_value = True

        response = client.delete(
            "/api/v1/payments/methods/pm_ok",
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    @patch("app.services.stripe_service.StripeService.delete_payment_method")
    def test_delete_payment_method_not_found(
        self,
        mock_delete,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_delete.return_value = False

        response = client.delete(
            "/api/v1/payments/methods/pm_missing",
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("app.services.stripe_service.StripeService.delete_payment_method")
    def test_delete_payment_method_service_exception(
        self,
        mock_delete,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_delete.side_effect = ServiceException("Delete failed")

        response = client.delete(
            "/api/v1/payments/methods/pm_error",
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("app.services.stripe_service.StripeService.delete_payment_method")
    def test_delete_payment_method_unexpected_exception(
        self,
        mock_delete,
        client: TestClient,
        auth_headers_student: Dict[str, str],
    ):
        mock_delete.side_effect = Exception("boom")

        response = client.delete(
            "/api/v1/payments/methods/pm_boom",
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestIdentityEndpoints:
    """Tests for Stripe Identity endpoints."""

    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_success(
        self,
        mock_create_session,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_create_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }

        response = client.post(
            "/api/v1/payments/identity/session",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["verification_session_id"] == "vs_123"

    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_uses_configured_frontend_origin(
        self,
        mock_create_session,
        auth_headers_instructor: Dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ):
        from app.core import config as config_module
        from app.main import fastapi_app

        mock_create_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }
        monkeypatch.setattr(config_module.settings, "frontend_url", "https://app.example.com")
        monkeypatch.setattr(config_module.settings, "identity_return_path", "/identity/return")

        with TestClient(fastapi_app, base_url="https://app.example.com") as test_client:
            response = test_client.post(
                "/api/v1/payments/identity/session",
                headers={**auth_headers_instructor, "host": "app.example.com"},
            )

        assert response.status_code == status.HTTP_200_OK
        return_url = mock_create_session.call_args.kwargs["return_url"]
        assert return_url == "https://app.example.com/identity/return"

    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_service_exception(
        self,
        mock_create_session,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_create_session.side_effect = ServiceException("Identity error")

        response = client.post(
            "/api/v1/payments/identity/session",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("app.services.stripe_service.StripeService.create_identity_verification_session")
    def test_identity_session_unexpected_exception(
        self,
        mock_create_session,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_create_session.side_effect = Exception("boom")

        response = client.post(
            "/api/v1/payments/identity/session",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "Failed to create identity session"

    def test_identity_session_requires_instructor_role(
        self, client: TestClient, auth_headers_student: Dict[str, str]
    ):
        response = client.post(
            "/api/v1/payments/identity/session",
            headers=auth_headers_student,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_identity_session_origin_falls_back_to_configured_frontend(
        self, test_instructor: User, monkeypatch: pytest.MonkeyPatch
    ):
        from app.core import config as config_module
        from app.routes.v1.payments import create_identity_session

        monkeypatch.setattr(config_module.settings, "frontend_url", "https://frontend.example.com")
        monkeypatch.setattr(config_module.settings, "identity_return_path", "/identity/return")
        stripe_service = MagicMock()
        stripe_service.create_identity_verification_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }

        scope = {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/payments/identity/session",
            "raw_path": b"/api/v1/payments/identity/session",
            "query_string": b"",
            "headers": [],
            "server": ("api.local", 443),
            "client": ("127.0.0.1", 1234),
        }
        request = Request(scope)

        await create_identity_session(
            request=request,
            current_user=test_instructor,
            stripe_service=stripe_service,
        )

        return_url = stripe_service.create_identity_verification_session.call_args.kwargs["return_url"]
        expected_return_url = urljoin("https://frontend.example.com/", "identity/return")
        assert return_url == expected_return_url

    @pytest.mark.asyncio
    async def test_identity_session_origin_falls_back_to_base_url(
        self, test_instructor: User, monkeypatch: pytest.MonkeyPatch
    ):
        from app.core import config as config_module
        from app.routes.v1.payments import create_identity_session

        monkeypatch.setattr(config_module.settings, "frontend_url", "")
        monkeypatch.setattr(config_module.settings, "identity_return_path", "/identity/return")
        stripe_service = MagicMock()
        stripe_service.create_identity_verification_session.return_value = {
            "verification_session_id": "vs_123",
            "client_secret": "secret_123",
        }

        scope = {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/payments/identity/session",
            "raw_path": b"/api/v1/payments/identity/session",
            "query_string": b"",
            "headers": [],
            "server": ("api.local", 443),
            "client": ("127.0.0.1", 1234),
        }
        request = Request(scope)

        await create_identity_session(
            request=request,
            current_user=test_instructor,
            stripe_service=stripe_service,
        )

        return_url = stripe_service.create_identity_verification_session.call_args.kwargs["return_url"]
        expected_origin = str(request.base_url).rstrip("/")
        expected_return_url = urljoin(f"{expected_origin}/", "identity/return")
        assert return_url == expected_return_url

    @patch("app.services.stripe_service.StripeService.refresh_instructor_identity")
    def test_refresh_identity_status_success(
        self,
        mock_refresh,
        client: TestClient,
        auth_headers_instructor: Dict[str, str],
    ):
        mock_refresh.return_value = {"status": "verified", "verified": True}

        response = client.post(
            "/api/v1/payments/identity/refresh",
            headers=auth_headers_instructor,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["verified"] is True


class TestWebhookErrorCases:
    """Tests for webhook error and edge cases."""

    @patch("app.routes.v1.payments.settings")
    def test_webhook_missing_secrets_returns_500(
        self, mock_settings, client: TestClient
    ):
        mock_settings.webhook_secrets = []

        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content=b"{}",
            headers={"Content-Type": "application/json", "stripe-signature": "sig"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.v1.payments.settings")
    def test_webhook_connected_account_event(
        self,
        mock_settings,
        mock_handle_event,
        mock_construct_event,
        client: TestClient,
    ):
        mock_settings.webhook_secrets = ["whsec_test"]
        mock_construct_event.return_value = {
            "type": "payout.paid",
            "account": "acct_connected",
            "data": {"object": {"id": "po_test"}},
        }
        mock_handle_event.return_value = {"success": True}

        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content=b'{"type": "payout.paid"}',
            headers={"Content-Type": "application/json", "stripe-signature": "sig"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["event_type"] == "payout.paid"

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.v1.payments.settings")
    def test_webhook_uses_platform_secret_type(
        self,
        mock_settings,
        mock_handle_event,
        mock_construct_event,
        client: TestClient,
    ):
        mock_settings.webhook_secrets = ["whsec_platform"]
        mock_settings.stripe_webhook_secret = None
        mock_settings.stripe_webhook_secret_platform = _DummySecret("whsec_platform")
        mock_settings.stripe_webhook_secret_connect = None
        mock_construct_event.return_value = {"type": "payout.paid", "data": {"object": {"id": "po_test"}}}
        mock_handle_event.return_value = {"success": True}

        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content=b'{"type": "payout.paid"}',
            headers={"Content-Type": "application/json", "stripe-signature": "sig"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Event processed with platform secret"

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.v1.payments.settings")
    def test_webhook_uses_connect_secret_type(
        self,
        mock_settings,
        mock_handle_event,
        mock_construct_event,
        client: TestClient,
    ):
        mock_settings.webhook_secrets = ["whsec_connect"]
        mock_settings.stripe_webhook_secret = None
        mock_settings.stripe_webhook_secret_platform = None
        mock_settings.stripe_webhook_secret_connect = _DummySecret("whsec_connect")
        mock_construct_event.return_value = {"type": "payout.paid", "data": {"object": {"id": "po_test"}}}
        mock_handle_event.return_value = {"success": True}

        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content=b'{"type": "payout.paid"}',
            headers={"Content-Type": "application/json", "stripe-signature": "sig"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Event processed with connect secret"

    @patch("stripe.Webhook.construct_event")
    @patch("app.services.stripe_service.StripeService.handle_webhook_event")
    @patch("app.routes.v1.payments.settings")
    def test_webhook_uses_fallback_secret_type(
        self,
        mock_settings,
        mock_handle_event,
        mock_construct_event,
        client: TestClient,
    ):
        mock_settings.webhook_secrets = ["whsec_other"]
        mock_settings.stripe_webhook_secret = None
        mock_settings.stripe_webhook_secret_platform = None
        mock_settings.stripe_webhook_secret_connect = None
        mock_construct_event.return_value = {"type": "payout.paid", "data": {"object": {"id": "po_test"}}}
        mock_handle_event.return_value = {"success": True}

        response = client.post(
            "/api/v1/payments/webhooks/stripe",
            content=b'{"type": "payout.paid"}',
            headers={"Content-Type": "application/json", "stripe-signature": "sig"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Event processed with secret #1 secret"
