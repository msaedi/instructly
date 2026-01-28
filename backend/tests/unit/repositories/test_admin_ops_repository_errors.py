"""Unit tests for AdminOpsRepository error handling paths."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.admin_ops_repository import AdminOpsRepository


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def repo(mock_db):
    """Create AdminOpsRepository with mock db."""
    return AdminOpsRepository(mock_db)


class TestAdminOpsRepositoryErrorHandling:
    """Test error handling paths in AdminOpsRepository."""

    def test_get_bookings_in_date_range_raises_on_db_error(self, repo, mock_db):
        """Test get_bookings_in_date_range_with_service raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Database connection failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_bookings_in_date_range_with_service(
                date(2024, 1, 1), date(2024, 1, 31)
            )

        assert "Failed to get bookings in date range" in str(exc_info.value)

    def test_get_first_booking_date_raises_on_db_error(self, repo, mock_db):
        """Test get_first_booking_date_for_student raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Query timeout")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_first_booking_date_for_student("student_123")

        assert "Failed to get first booking date" in str(exc_info.value)

    def test_get_recent_bookings_raises_on_db_error(self, repo, mock_db):
        """Test get_recent_bookings_with_details raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Connection pool exhausted")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_recent_bookings_with_details(
                cutoff=datetime.now(timezone.utc), status=None, limit=10
            )

        assert "Failed to get recent bookings" in str(exc_info.value)

    def test_count_pending_authorizations_raises_on_db_error(self, repo, mock_db):
        """Test count_pending_authorizations raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Table lock timeout")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_pending_authorizations(date.today())

        assert "Failed to count pending authorizations" in str(exc_info.value)

    def test_count_bookings_by_payment_raises_on_db_error(self, repo, mock_db):
        """Test count_bookings_by_payment_and_status raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Deadlock detected")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_bookings_by_payment_and_status("AUTHORIZED")

        assert "Failed to count bookings" in str(exc_info.value)

    def test_count_failed_payments_raises_on_db_error(self, repo, mock_db):
        """Test count_failed_payments raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Network partition")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_failed_payments(datetime.now(timezone.utc))

        assert "Failed to count failed payments" in str(exc_info.value)

    def test_count_refunded_bookings_raises_on_db_error(self, repo, mock_db):
        """Test count_refunded_bookings raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Disk full")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_refunded_bookings(datetime.now(timezone.utc))

        assert "Failed to count refunded bookings" in str(exc_info.value)

    def test_count_overdue_authorizations_raises_on_db_error(self, repo, mock_db):
        """Test count_overdue_authorizations raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Server unreachable")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_overdue_authorizations(
                datetime.now(timezone.utc), datetime.now(timezone.utc)
            )

        assert "Failed to count overdue authorizations" in str(exc_info.value)

    def test_count_overdue_captures_raises_on_db_error(self, repo, mock_db):
        """Test count_overdue_captures raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Index corruption")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_overdue_captures(datetime.now(timezone.utc))

        assert "Failed to count overdue captures" in str(exc_info.value)

    def test_sum_captured_amount_raises_on_db_error(self, repo, mock_db):
        """Test sum_captured_amount raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Memory limit exceeded")

        with pytest.raises(RepositoryException) as exc_info:
            repo.sum_captured_amount(datetime.now(timezone.utc))

        assert "Failed to sum captured amounts" in str(exc_info.value)

    def test_get_instructors_with_pending_payouts_raises_on_db_error(
        self, repo, mock_db
    ):
        """Test get_instructors_with_pending_payouts raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Join operation failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_instructors_with_pending_payouts(limit=10)

        assert "Failed to get pending payouts" in str(exc_info.value)

    def test_get_user_by_email_raises_on_db_error(self, repo, mock_db):
        """Test get_user_by_email_with_profile raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Invalid email index")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_user_by_email_with_profile("test@example.com")

        assert "Failed to get user by email" in str(exc_info.value)

    def test_get_user_by_phone_raises_on_db_error(self, repo, mock_db):
        """Test get_user_by_phone_with_profile raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Phone lookup failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_user_by_phone_with_profile("555-123-4567")

        assert "Failed to get user by phone" in str(exc_info.value)

    def test_get_user_by_id_raises_on_db_error(self, repo, mock_db):
        """Test get_user_by_id_with_profile raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("User table locked")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_user_by_id_with_profile("user_123")

        assert "Failed to get user by ID" in str(exc_info.value)

    def test_count_student_bookings_raises_on_db_error(self, repo, mock_db):
        """Test count_student_bookings raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Count aggregation failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_student_bookings("student_123")

        assert "Failed to count student bookings" in str(exc_info.value)

    def test_sum_student_spent_raises_on_db_error(self, repo, mock_db):
        """Test sum_student_spent raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Sum aggregation failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.sum_student_spent("student_123")

        assert "Failed to sum student spent" in str(exc_info.value)

    def test_count_instructor_completed_lessons_raises_on_db_error(self, repo, mock_db):
        """Test count_instructor_completed_lessons raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Instructor query failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.count_instructor_completed_lessons("instructor_123")

        assert "Failed to count completed lessons" in str(exc_info.value)

    def test_sum_instructor_earned_raises_on_db_error(self, repo, mock_db):
        """Test sum_instructor_earned raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Earnings sum failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.sum_instructor_earned("instructor_123")

        assert "Failed to sum instructor earned" in str(exc_info.value)

    def test_get_user_with_instructor_profile_raises_on_db_error(self, repo, mock_db):
        """Test get_user_with_instructor_profile raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("Profile join failed")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_user_with_instructor_profile("user_123")

        assert "Failed to get user with profile" in str(exc_info.value)

    def test_get_user_booking_history_raises_on_db_error(self, repo, mock_db):
        """Test get_user_booking_history raises RepositoryException on DB error."""
        mock_db.query.side_effect = SQLAlchemyError("History query timeout")

        with pytest.raises(RepositoryException) as exc_info:
            repo.get_user_booking_history("user_123", is_instructor=False, limit=10)

        assert "Failed to get booking history" in str(exc_info.value)


class TestAdminOpsRepositoryStatusFilter:
    """Test status filter branch in get_recent_bookings_with_details."""

    def test_get_recent_bookings_with_status_filter(self, repo, mock_db):
        """Test get_recent_bookings_with_details applies status filter correctly."""
        # Setup mock chain
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = repo.get_recent_bookings_with_details(
            cutoff=datetime.now(timezone.utc),
            status="confirmed",  # Pass status to hit line 120
            limit=10,
        )

        assert result == []
        # Verify filter was called (the status filter branch was executed)
        assert mock_query.filter.call_count >= 2  # cutoff filter + status filter
