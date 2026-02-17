"""
Unit tests for account_lifecycle_service.py — targeting missed lines:
  115->119, 120, 155, 172->176, 177, 215, 224->228

These cover:
  - No cache_service (lines 115, 172, 224): cache invalidation is skipped
  - Token invalidation failure (lines 119-120, 176-177): logs warning
  - Student status change attempts (line 155): deactivate raises for students
  - Reactivate with student (line 215): raises ValidationException
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ValidationException
from app.services.account_lifecycle_service import AccountLifecycleService


@pytest.fixture
def mock_instructor():
    """Create a mock instructor user."""
    instructor = MagicMock()
    instructor.id = "01ABCDEFGHJKMNPQRSTVWXYZ01"
    instructor.is_instructor = True
    instructor.is_student = False
    instructor.is_account_active = True
    instructor.is_suspended = False
    instructor.is_deactivated = False
    instructor.account_status = "active"
    instructor.can_change_status_to.return_value = True
    instructor.can_login = True
    instructor.can_receive_bookings = True
    instructor.roles = [MagicMock(name="instructor")]
    return instructor


@pytest.fixture
def mock_student():
    """Create a mock student user."""
    student = MagicMock()
    student.id = "01ABCDEFGHJKMNPQRSTVWXYZ02"
    student.is_instructor = True  # must pass has_future_bookings check
    student.is_student = True
    student.is_account_active = True
    student.account_status = "active"
    student.can_change_status_to.return_value = False
    return student


class TestSuspendInstructorAccount:
    """Test suspend_instructor_account branches."""

    def test_suspend_without_cache_service(self, db, mock_instructor):
        """Lines 115->119: no cache_service means skip cache invalidation."""
        service = AccountLifecycleService(db, cache_service=None)

        # Mock the repositories
        service.booking_repository = MagicMock()
        service.booking_repository.get_instructor_future_bookings.return_value = []
        service.user_repository = MagicMock()
        service.user_repository.invalidate_all_tokens.return_value = True

        with patch.object(service, "transaction") as mock_txn:
            mock_txn.return_value.__enter__ = MagicMock()
            mock_txn.return_value.__exit__ = MagicMock(return_value=False)
            result = service.suspend_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["new_status"] == "suspended"

    def test_suspend_token_invalidation_failure(self, db, mock_instructor):
        """Lines 119-120: invalidate_all_tokens returns False → logs warning."""
        mock_cache = MagicMock()
        service = AccountLifecycleService(db, cache_service=mock_cache)
        service.booking_repository = MagicMock()
        service.booking_repository.get_instructor_future_bookings.return_value = []
        service.user_repository = MagicMock()
        service.user_repository.invalidate_all_tokens.return_value = False

        with patch.object(service, "transaction") as mock_txn:
            mock_txn.return_value.__enter__ = MagicMock()
            mock_txn.return_value.__exit__ = MagicMock(return_value=False)
            result = service.suspend_instructor_account(mock_instructor)

        # Should succeed despite token invalidation failure
        assert result["success"] is True
        service.user_repository.invalidate_all_tokens.assert_called_once_with(
            mock_instructor.id, trigger="suspension"
        )

    def test_suspend_student_raises_validation(self, db, mock_student):
        """Line 99: students cannot change their account status."""
        service = AccountLifecycleService(db)
        service.booking_repository = MagicMock()
        service.booking_repository.get_instructor_future_bookings.return_value = []
        service.user_repository = MagicMock()

        with pytest.raises(ValidationException, match="Students cannot change"):
            service.suspend_instructor_account(mock_student)


class TestDeactivateInstructorAccount:
    """Test deactivate_instructor_account branches."""

    def test_deactivate_without_cache_service(self, db, mock_instructor):
        """Lines 172->176: no cache_service means skip cache invalidation."""
        service = AccountLifecycleService(db, cache_service=None)
        service.booking_repository = MagicMock()
        service.booking_repository.get_instructor_future_bookings.return_value = []
        service.user_repository = MagicMock()
        service.user_repository.invalidate_all_tokens.return_value = True

        with patch.object(service, "transaction") as mock_txn:
            mock_txn.return_value.__enter__ = MagicMock()
            mock_txn.return_value.__exit__ = MagicMock(return_value=False)
            result = service.deactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["new_status"] == "deactivated"

    def test_deactivate_token_invalidation_failure(self, db, mock_instructor):
        """Lines 176-177: invalidate_all_tokens returns False → logs warning."""
        mock_cache = MagicMock()
        service = AccountLifecycleService(db, cache_service=mock_cache)
        service.booking_repository = MagicMock()
        service.booking_repository.get_instructor_future_bookings.return_value = []
        service.user_repository = MagicMock()
        service.user_repository.invalidate_all_tokens.return_value = False

        with patch.object(service, "transaction") as mock_txn:
            mock_txn.return_value.__enter__ = MagicMock()
            mock_txn.return_value.__exit__ = MagicMock(return_value=False)
            result = service.deactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        service.user_repository.invalidate_all_tokens.assert_called_once_with(
            mock_instructor.id, trigger="deactivation"
        )

    def test_deactivate_student_raises_validation(self, db, mock_student):
        """Line 155: students cannot deactivate."""
        service = AccountLifecycleService(db)
        service.booking_repository = MagicMock()
        service.booking_repository.get_instructor_future_bookings.return_value = []
        service.user_repository = MagicMock()

        with pytest.raises(ValidationException, match="Students cannot change"):
            service.deactivate_instructor_account(mock_student)

    def test_deactivate_invalid_transition_non_student(self, db, mock_instructor):
        """Line 155 else: invalid transition for non-student instructor."""
        mock_instructor.can_change_status_to.return_value = False
        mock_instructor.is_student = False
        service = AccountLifecycleService(db)
        service.booking_repository = MagicMock()
        service.user_repository = MagicMock()

        with pytest.raises(ValidationException, match="Invalid status transition to deactivated"):
            service.deactivate_instructor_account(mock_instructor)


class TestReactivateInstructorAccount:
    """Test reactivate_instructor_account branches."""

    def test_reactivate_without_cache_service(self, db, mock_instructor):
        """Lines 224->228: no cache_service means skip cache invalidation."""
        mock_instructor.is_account_active = False
        mock_instructor.account_status = "suspended"
        service = AccountLifecycleService(db, cache_service=None)
        service.booking_repository = MagicMock()
        service.user_repository = MagicMock()

        with patch.object(service, "transaction") as mock_txn:
            mock_txn.return_value.__enter__ = MagicMock()
            mock_txn.return_value.__exit__ = MagicMock(return_value=False)
            result = service.reactivate_instructor_account(mock_instructor)

        assert result["success"] is True
        assert result["new_status"] == "active"

    def test_reactivate_student_raises_validation(self, db, mock_student):
        """Line 215: students cannot reactivate."""
        mock_student.is_account_active = False
        service = AccountLifecycleService(db)
        service.booking_repository = MagicMock()
        service.user_repository = MagicMock()

        with pytest.raises(ValidationException, match="Students cannot change"):
            service.reactivate_instructor_account(mock_student)

    def test_reactivate_already_active_raises_validation(self, db, mock_instructor):
        """Line 209: already active account raises ValidationException."""
        mock_instructor.is_account_active = True
        service = AccountLifecycleService(db)
        service.booking_repository = MagicMock()
        service.user_repository = MagicMock()

        with pytest.raises(ValidationException, match="Account is already active"):
            service.reactivate_instructor_account(mock_instructor)

    def test_reactivate_invalid_transition_non_student(self, db, mock_instructor):
        """Line 215 else: invalid transition for non-student."""
        mock_instructor.is_account_active = False
        mock_instructor.can_change_status_to.return_value = False
        mock_instructor.is_student = False
        service = AccountLifecycleService(db)
        service.booking_repository = MagicMock()
        service.user_repository = MagicMock()

        with pytest.raises(ValidationException, match="Invalid status transition to active"):
            service.reactivate_instructor_account(mock_instructor)
