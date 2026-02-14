# backend/tests/unit/services/test_account_lifecycle_service.py
"""
Unit tests for AccountLifecycleService.

Tests all account status transitions and business rules with mocked dependencies.
Follows the repository pattern with mocked repositories.
"""

from datetime import date, timedelta
from unittest.mock import Mock, patch

import pytest

from app.core.enums import RoleName
from app.core.exceptions import BusinessRuleException, ValidationException
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.services.account_lifecycle_service import AccountLifecycleService


class TestAccountLifecycleServiceUnit:
    """Unit tests for AccountLifecycleService with mocked dependencies."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock()
        db.commit = Mock()
        db.add = Mock()
        db.flush = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def mock_booking_repository(self):
        """Create a mock booking repository."""
        repository = Mock()
        repository.get_instructor_future_bookings = Mock(return_value=[])
        return repository

    @pytest.fixture
    def mock_user_repository(self):
        """Create a mock user repository."""
        repository = Mock()
        repository.update = Mock(return_value=True)
        return repository

    @pytest.fixture
    def mock_cache_service(self):
        """Create a mock cache service."""
        cache = Mock()
        cache.delete_pattern = Mock()
        return cache

    @pytest.fixture
    def service(self, mock_db, mock_cache_service):
        """Create AccountLifecycleService with mocked dependencies."""
        with patch("app.repositories.factory.RepositoryFactory") as mock_factory:
            # Mock the factory methods
            mock_booking_repo = Mock()
            mock_booking_repo.get_instructor_future_bookings = Mock(return_value=[])
            mock_factory.create_booking_repository.return_value = mock_booking_repo

            mock_user_repo = Mock()
            mock_user_repo.update = Mock(return_value=True)
            mock_factory.create_base_repository.return_value = mock_user_repo

            service = AccountLifecycleService(mock_db, mock_cache_service)
            service.booking_repository = mock_booking_repo
            service.user_repository = mock_user_repo

            # Mock the transaction context manager
            service.transaction = Mock()
            service.transaction.return_value.__enter__ = Mock()
            service.transaction.return_value.__exit__ = Mock(return_value=None)

            return service

    @pytest.fixture
    def mock_instructor(self):
        """Create a mock instructor user."""
        instructor = Mock(spec=User)

        mock_instructor_role = Mock()

        mock_instructor_role.name = RoleName.INSTRUCTOR

        instructor.roles = [mock_instructor_role]
        instructor.id = 1
        instructor.email = "instructor@example.com"
        instructor.first_name = ("Test",)
        _last_name = "Instructor"
        instructor.account_status = "active"
        instructor.is_instructor = True
        instructor.is_student = False
        instructor.is_account_active = True
        instructor.is_suspended = False
        instructor.is_deactivated = False
        instructor.can_receive_bookings = True
        instructor.can_login = True
        instructor.can_change_status_to = Mock(return_value=True)
        return instructor

    @pytest.fixture
    def mock_student(self):
        """Create a mock student user."""
        student = Mock(spec=User)

        mock_student_role = Mock()

        mock_student_role.name = RoleName.STUDENT

        student.roles = [mock_student_role]
        student.id = 2
        student.email = "student@example.com"
        student.first_name = ("Test",)
        _last_name = "Student"
        student.account_status = "active"
        student.is_instructor = False
        student.is_student = True
        student.can_change_status_to = Mock(return_value=False)
        return student

    @pytest.fixture
    def mock_future_booking(self):
        """Create a mock future booking."""
        booking = Mock(spec=Booking)
        booking.id = 1
        booking.booking_date = date.today() + timedelta(days=7)
        booking.status = BookingStatus.CONFIRMED
        booking.student_name = "Test Student"
        booking.service_name = "Piano Lessons"
        return booking

    # Test has_future_bookings method

    def test_has_future_bookings_none(self, service, mock_instructor):
        """Test checking future bookings when none exist."""
        service.booking_repository.get_instructor_future_bookings.return_value = []

        has_bookings, bookings = service.has_future_bookings(mock_instructor)

        assert has_bookings is False
        assert bookings == []
        service.booking_repository.get_instructor_future_bookings.assert_called_once_with(
            instructor_id=mock_instructor.id, exclude_cancelled=True
        )

    def test_has_future_bookings_exists(self, service, mock_instructor, mock_future_booking):
        """Test checking future bookings when they exist."""
        service.booking_repository.get_instructor_future_bookings.return_value = [mock_future_booking]

        has_bookings, bookings = service.has_future_bookings(mock_instructor)

        assert has_bookings is True
        assert len(bookings) == 1
        assert bookings[0] == mock_future_booking

    def test_has_future_bookings_student_error(self, service, mock_student):
        """Test that students cannot check future bookings."""
        with pytest.raises(ValidationException) as exc_info:
            service.has_future_bookings(mock_student)

        assert "Only instructors can be checked for future bookings" in str(exc_info.value)

    # Test suspend_instructor_account method

    def test_suspend_account_success(self, service, mock_instructor):
        """Test successful account suspension."""
        mock_instructor.account_status = "active"
        service.booking_repository.get_instructor_future_bookings.return_value = []

        result = service.suspend_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["message"] == "Account suspended successfully"
        assert result["previous_status"] == "active"
        assert result["new_status"] == "suspended"

        service.user_repository.update.assert_called_once_with(mock_instructor.id, account_status="suspended")
        service.user_repository.invalidate_all_tokens.assert_called_once_with(
            mock_instructor.id,
            trigger="suspension",
        )
        service.cache_service.delete_pattern.assert_any_call(f"instructor:{mock_instructor.id}:*")
        service.cache_service.delete_pattern.assert_any_call(f"availability:instructor:{mock_instructor.id}:*")

    def test_suspend_account_with_future_bookings(self, service, mock_instructor, mock_future_booking):
        """Test suspension fails with future bookings."""
        service.booking_repository.get_instructor_future_bookings.return_value = [mock_future_booking]

        with pytest.raises(BusinessRuleException) as exc_info:
            service.suspend_instructor_account(mock_instructor)

        assert "Cannot suspend account: instructor has 1 future bookings" in str(exc_info.value)
        service.user_repository.update.assert_not_called()

    def test_suspend_account_student_error(self, service, mock_student):
        """Test that students cannot suspend their account."""
        mock_student.can_change_status_to.return_value = False

        with pytest.raises(ValidationException) as exc_info:
            service.suspend_instructor_account(mock_student)

        assert "Students cannot change their account status" in str(exc_info.value)

    def test_suspend_account_invalid_transition(self, service, mock_instructor):
        """Test invalid status transition to suspended."""
        mock_instructor.is_student = False
        mock_instructor.can_change_status_to.return_value = False

        with pytest.raises(ValidationException) as exc_info:
            service.suspend_instructor_account(mock_instructor)

        assert "Invalid status transition to suspended" in str(exc_info.value)

    # Test deactivate_instructor_account method

    def test_deactivate_account_success(self, service, mock_instructor):
        """Test successful account deactivation."""
        mock_instructor.account_status = "active"
        service.booking_repository.get_instructor_future_bookings.return_value = []

        result = service.deactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["message"] == "Account deactivated successfully"
        assert result["previous_status"] == "active"
        assert result["new_status"] == "deactivated"

        service.user_repository.update.assert_called_once_with(mock_instructor.id, account_status="deactivated")
        service.cache_service.delete_pattern.assert_any_call(f"instructor:{mock_instructor.id}:*")
        service.cache_service.delete_pattern.assert_any_call(f"availability:instructor:{mock_instructor.id}:*")

    def test_deactivate_account_from_suspended(self, service, mock_instructor):
        """Test deactivation from suspended state."""
        mock_instructor.account_status = "suspended"
        service.booking_repository.get_instructor_future_bookings.return_value = []

        result = service.deactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["previous_status"] == "suspended"
        assert result["new_status"] == "deactivated"

    def test_deactivate_account_with_future_bookings(self, service, mock_instructor, mock_future_booking):
        """Test deactivation fails with future bookings."""
        service.booking_repository.get_instructor_future_bookings.return_value = [mock_future_booking]

        with pytest.raises(BusinessRuleException) as exc_info:
            service.deactivate_instructor_account(mock_instructor)

        assert "Cannot deactivate account: instructor has 1 future bookings" in str(exc_info.value)
        service.user_repository.update.assert_not_called()

    def test_deactivate_account_student_error(self, service, mock_student):
        """Test that students cannot deactivate their account."""
        mock_student.can_change_status_to.return_value = False

        with pytest.raises(ValidationException) as exc_info:
            service.deactivate_instructor_account(mock_student)

        assert "Students cannot change their account status" in str(exc_info.value)

    # Test reactivate_instructor_account method

    def test_reactivate_account_from_suspended(self, service, mock_instructor):
        """Test successful reactivation from suspended state."""
        mock_instructor.account_status = "suspended"
        mock_instructor.is_account_active = False
        mock_instructor.is_suspended = True

        result = service.reactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["message"] == "Account reactivated successfully"
        assert result["previous_status"] == "suspended"
        assert result["new_status"] == "active"

        service.user_repository.update.assert_called_once_with(mock_instructor.id, account_status="active")
        service.cache_service.delete_pattern.assert_any_call(f"instructor:{mock_instructor.id}:*")
        service.cache_service.delete_pattern.assert_any_call(f"availability:instructor:{mock_instructor.id}:*")

    def test_reactivate_account_already_active(self, service, mock_instructor):
        """Test reactivation fails when already active."""
        mock_instructor.is_account_active = True

        with pytest.raises(ValidationException) as exc_info:
            service.reactivate_instructor_account(mock_instructor)

        assert "Account is already active" in str(exc_info.value)
        service.user_repository.update.assert_not_called()

    def test_reactivate_account_from_deactivated(self, service, mock_instructor):
        """Test reactivation from deactivated state succeeds."""
        mock_instructor.account_status = "deactivated"
        mock_instructor.is_account_active = False
        mock_instructor.is_deactivated = True
        mock_instructor.can_change_status_to.return_value = True

        result = service.reactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["previous_status"] == "deactivated"
        assert result["new_status"] == "active"

    def test_reactivate_account_student_error(self, service, mock_student):
        """Test that students cannot reactivate their account."""
        mock_student.is_account_active = False
        mock_student.can_change_status_to.return_value = False

        with pytest.raises(ValidationException) as exc_info:
            service.reactivate_instructor_account(mock_student)

        assert "Students cannot change their account status" in str(exc_info.value)

    # Test get_account_status method

    def test_get_account_status_instructor_active(self, service, mock_instructor):
        """Test getting status for active instructor."""
        mock_instructor.account_status = "active"
        mock_instructor.is_account_active = True
        mock_instructor.can_receive_bookings = True
        mock_instructor.can_login = True
        service.booking_repository.get_instructor_future_bookings.return_value = []

        result = service.get_account_status(mock_instructor)

        assert result["user_id"] == mock_instructor.id
        assert result["role"] == RoleName.INSTRUCTOR
        assert result["account_status"] == "active"
        assert result["can_login"] is True
        assert result["can_receive_bookings"] is True
        assert result["is_active"] is True
        assert result["is_suspended"] is False
        assert result["is_deactivated"] is False
        assert result["has_future_bookings"] is False
        assert result["future_bookings_count"] == 0
        assert result["can_suspend"] is True
        assert result["can_deactivate"] is True
        assert result["can_reactivate"] is False

    def test_get_account_status_instructor_suspended(self, service, mock_instructor):
        """Test getting status for suspended instructor."""
        mock_instructor.account_status = "suspended"
        mock_instructor.is_account_active = False
        mock_instructor.is_suspended = True
        mock_instructor.can_receive_bookings = False
        mock_instructor.can_login = True
        service.booking_repository.get_instructor_future_bookings.return_value = []

        result = service.get_account_status(mock_instructor)

        assert result["account_status"] == "suspended"
        assert result["can_login"] is True
        assert result["can_receive_bookings"] is False
        assert result["is_active"] is False
        assert result["is_suspended"] is True
        assert result["can_suspend"] is False
        assert result["can_deactivate"] is True
        assert result["can_reactivate"] is True

    def test_get_account_status_instructor_with_future_bookings(self, service, mock_instructor, mock_future_booking):
        """Test getting status when instructor has future bookings."""
        service.booking_repository.get_instructor_future_bookings.return_value = [mock_future_booking]

        result = service.get_account_status(mock_instructor)

        assert result["has_future_bookings"] is True
        assert result["future_bookings_count"] == 1
        assert result["can_suspend"] is False
        assert result["can_deactivate"] is False

    def test_get_account_status_student(self, service, mock_student):
        """Test getting status for student."""
        mock_student.account_status = "active"
        mock_student.is_account_active = True
        mock_student.can_receive_bookings = False
        mock_student.can_login = True

        result = service.get_account_status(mock_student)

        assert result["user_id"] == mock_student.id
        assert result["role"] == RoleName.STUDENT
        assert result["account_status"] == "active"
        assert result["can_login"] is True
        assert result["can_receive_bookings"] is False
        # Should not have instructor-specific fields
        assert "has_future_bookings" not in result
        assert "can_suspend" not in result
        assert "can_deactivate" not in result
        assert "can_reactivate" not in result
