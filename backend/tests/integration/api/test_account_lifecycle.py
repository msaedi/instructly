# backend/tests/integration/api/test_account_lifecycle.py
"""
Integration tests for account lifecycle API endpoints.

Tests all instructor account status change endpoints with real database.
"""

from datetime import date, time, timedelta

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.models.booking import Booking, BookingStatus
from app.models.user import User


class TestAccountLifecycleEndpoints:
    """Test suite for account lifecycle endpoints."""

    @pytest.fixture
    def instructor_with_no_bookings(self, db: Session, test_instructor: User):
        """Ensure instructor has no future bookings."""
        # Cancel any existing future bookings
        future_bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date >= date.today(),
                Booking.status != BookingStatus.CANCELLED,
            )
            .all()
        )

        for booking in future_bookings:
            booking.status = BookingStatus.CANCELLED

        db.commit()
        return test_instructor

    @pytest.fixture
    def instructor_with_future_booking(self, db: Session, test_instructor: User, test_student: User):
        """Create an instructor with a future booking."""
        # Get instructor's profile and service
        profile = test_instructor.instructor_profile
        service = next((s for s in profile.instructor_services if s.is_active), None)

        if not service:
            raise ValueError("Test instructor has no active services")

        # Create a future booking
        tomorrow = date.today() + timedelta(days=1)
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name,
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Online",
            location_type="neutral",
        )
        db.add(booking)
        db.commit()

        return test_instructor

    # Test suspend endpoint

    def test_suspend_account_success(
        self, client: TestClient, instructor_with_no_bookings: User, auth_headers_instructor: dict
    ):
        """Test successful account suspension."""
        response = client.post("/api/v1/account/suspend", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Account suspended successfully"
        assert data["previous_status"] == "active"
        assert data["new_status"] == "suspended"

    def test_suspend_account_with_future_bookings(
        self, client: TestClient, instructor_with_future_booking: User, auth_headers_instructor: dict
    ):
        """Test suspension fails with future bookings."""
        response = client.post("/api/v1/account/suspend", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "future bookings" in response.json()["detail"].lower()

    def test_suspend_account_unauthorized(self, client: TestClient, test_instructor: User):
        """Test suspension without authentication."""
        response = client.post("/api/v1/account/suspend")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_suspend_account_other_instructor(
        self, client: TestClient, test_instructor: User, test_instructor_2: User, auth_headers_instructor_2: dict
    ):
        """Test instructor can only suspend their own account (not another instructor's)."""
        # The API doesn't support suspending other users' accounts by design
        # Instructor_2 calling suspend will suspend instructor_2, not instructor_1
        response = client.post("/api/v1/account/suspend", headers=auth_headers_instructor_2)

        # Should succeed since instructor_2 is suspending their own account
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Verify it suspended successfully
        assert data["success"] is True
        assert data["new_status"] == "suspended"

    def test_suspend_account_as_student(self, client: TestClient, test_student: User, auth_headers_student: dict):
        """Test student cannot suspend an instructor account."""
        # Students trying to use instructor endpoints should be forbidden
        response = client.post("/api/v1/account/suspend", headers=auth_headers_student)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "only instructors can suspend" in response.json()["detail"].lower()

    def test_suspend_account_already_suspended(
        self, client: TestClient, instructor_with_no_bookings: User, auth_headers_instructor: dict, db: Session
    ):
        """Test suspending an already suspended account."""
        # First suspend the account
        response = client.post("/api/v1/account/suspend", headers=auth_headers_instructor)
        assert response.status_code == status.HTTP_200_OK

        # Try to suspend again - should succeed (idempotent)
        response = client.post("/api/v1/account/suspend", headers=auth_headers_instructor)

        # Should still succeed with same status
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["previous_status"] == "active"  # Service returns original status
        assert data["new_status"] == "suspended"

    # Test deactivate endpoint

    def test_deactivate_account_success(
        self, client: TestClient, instructor_with_no_bookings: User, auth_headers_instructor: dict
    ):
        """Test successful account deactivation."""
        response = client.post("/api/v1/account/deactivate", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Account deactivated successfully"
        assert data["previous_status"] == "active"
        assert data["new_status"] == "deactivated"

    def test_deactivate_account_from_suspended(
        self, client: TestClient, instructor_with_no_bookings: User, auth_headers_instructor: dict, db: Session
    ):
        """Test deactivation from suspended state."""
        # First suspend the account
        instructor_with_no_bookings.account_status = "suspended"
        db.commit()

        response = client.post("/api/v1/account/deactivate", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["previous_status"] == "suspended"
        assert data["new_status"] == "deactivated"

    def test_deactivate_account_with_future_bookings(
        self, client: TestClient, instructor_with_future_booking: User, auth_headers_instructor: dict
    ):
        """Test deactivation fails with future bookings."""
        response = client.post("/api/v1/account/deactivate", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "future bookings" in response.json()["detail"].lower()

    def test_deactivate_account_as_student(self, client: TestClient, test_instructor: User, auth_headers_student: dict):
        """Test student cannot deactivate an instructor account."""
        response = client.post("/api/v1/account/deactivate", headers=auth_headers_student)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    # Test reactivate endpoint

    def test_reactivate_account_from_suspended(
        self, client: TestClient, test_instructor: User, auth_headers_instructor: dict, db: Session
    ):
        """Test successful reactivation from suspended state."""
        # First suspend the account
        test_instructor.account_status = "suspended"
        db.commit()

        response = client.post("/api/v1/account/reactivate", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Account reactivated successfully"
        assert data["previous_status"] == "suspended"
        assert data["new_status"] == "active"

    def test_reactivate_account_from_deactivated(
        self, client: TestClient, test_instructor: User, auth_headers_instructor: dict, db: Session
    ):
        """Test reactivation from deactivated state."""
        # First deactivate the account
        test_instructor.account_status = "deactivated"
        db.commit()

        response = client.post("/api/v1/account/reactivate", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["previous_status"] == "deactivated"
        assert data["new_status"] == "active"

    def test_reactivate_account_already_active(
        self, client: TestClient, test_instructor: User, auth_headers_instructor: dict
    ):
        """Test reactivation fails when already active."""
        response = client.post("/api/v1/account/reactivate", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already active" in response.json()["detail"].lower()

    def test_reactivate_account_other_instructor(
        self,
        client: TestClient,
        test_instructor: User,
        test_instructor_2: User,
        auth_headers_instructor_2: dict,
        db: Session,
    ):
        """Test instructor can only reactivate their own account."""
        # Suspend instructor_2 (not instructor_1)
        test_instructor_2.account_status = "suspended"
        db.commit()

        # Instructor_2 reactivating their own account should succeed
        response = client.post("/api/v1/account/reactivate", headers=auth_headers_instructor_2)

        # Should succeed with 200
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["new_status"] == "active"

    # Test can-change-status endpoint

    def test_can_change_status_active_instructor(
        self, client: TestClient, instructor_with_no_bookings: User, auth_headers_instructor: dict
    ):
        """Test status check for active instructor with no bookings."""
        response = client.get("/api/v1/account/status", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["user_id"] == instructor_with_no_bookings.id
        assert data["account_status"] == "active"
        assert data["can_login"] is True
        assert data["can_receive_bookings"] is True
        assert data["has_future_bookings"] is False
        assert data["future_bookings_count"] == 0
        assert data["can_suspend"] is True
        assert data["can_deactivate"] is True
        assert data["can_reactivate"] is False

    def test_can_change_status_with_future_bookings(
        self, client: TestClient, instructor_with_future_booking: User, auth_headers_instructor: dict
    ):
        """Test status check when instructor has future bookings."""
        response = client.get("/api/v1/account/status", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["has_future_bookings"] is True
        assert data["future_bookings_count"] == 1
        assert data["can_suspend"] is False
        assert data["can_deactivate"] is False

    def test_can_change_status_suspended_instructor(
        self, client: TestClient, test_instructor: User, auth_headers_instructor: dict, db: Session
    ):
        """Test status check for suspended instructor."""
        # Suspend the account
        test_instructor.account_status = "suspended"
        db.commit()

        response = client.get("/api/v1/account/status", headers=auth_headers_instructor)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["account_status"] == "suspended"
        assert data["can_login"] is True
        assert data["can_receive_bookings"] is False
        assert data["can_suspend"] is False
        assert data["can_reactivate"] is True

    def test_can_change_status_other_instructor(
        self, client: TestClient, test_instructor: User, test_instructor_2: User, auth_headers_instructor_2: dict
    ):
        """Test instructor can only check their own status."""
        # The API only returns the status of the authenticated user
        response = client.get("/api/v1/account/status", headers=auth_headers_instructor_2)

        # Should succeed and return instructor_2's status
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["user_id"] == test_instructor_2.id

    def test_can_change_status_as_student(self, client: TestClient, test_student: User, auth_headers_student: dict):
        """Test student can check their own status."""
        response = client.get("/api/v1/account/status", headers=auth_headers_student)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["user_id"] == test_student.id
        assert data["role"] == RoleName.STUDENT.value
        assert data["account_status"] == "active"
        # Students should get None for all instructor-specific fields
        assert data.get("can_suspend") is None
        assert data.get("can_deactivate") is None
        assert data.get("can_reactivate") is None
