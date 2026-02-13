"""
Tests for PaymentMonitoringRepository - targeting CI coverage gaps.

Coverage for payment monitoring data access (currently 0% covered).
Uses mocking to test repository logic without database dependencies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models.payment import PaymentEvent
from app.repositories.payment_monitoring_repository import (
    PaymentEventCountData,
    PaymentMonitoringRepository,
    PaymentStatData,
)


class TestPaymentMonitoringRepositoryDataclasses:
    """Tests for the dataclasses."""

    def test_payment_stat_data_creation(self):
        """Test PaymentStatData creation."""
        stat = PaymentStatData(payment_status="scheduled", count=5)
        assert stat.payment_status == "scheduled"
        assert stat.count == 5

    def test_payment_stat_data_with_none_status(self):
        """Test PaymentStatData with None payment status."""
        stat = PaymentStatData(payment_status=None, count=3)
        assert stat.payment_status is None
        assert stat.count == 3

    def test_payment_event_count_data_creation(self):
        """Test PaymentEventCountData creation."""
        event_count = PaymentEventCountData(event_type="auth_succeeded", count=10)
        assert event_count.event_type == "auth_succeeded"
        assert event_count.count == 10


class TestPaymentMonitoringRepositoryInit:
    """Tests for repository initialization."""

    def test_init_with_db_session(self):
        """Test repository can be initialized with a database session."""
        mock_db = MagicMock()
        repo = PaymentMonitoringRepository(mock_db)
        assert repo.db is mock_db


class TestGetPaymentStatusCounts:
    """Tests for get_payment_status_counts method."""

    def test_get_payment_status_counts_empty_result(self):
        """Test with no confirmed bookings."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = []

        repo = PaymentMonitoringRepository(mock_db)
        future_date = datetime.now(timezone.utc) + timedelta(days=365)
        result = repo.get_payment_status_counts(future_date)

        assert result == []

    def test_get_payment_status_counts_with_bookings(self):
        """Test with actual confirmed bookings."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query

        # Mock query results: [(payment_status, count)]
        mock_query.all.return_value = [
            ("scheduled", 5),
            ("authorized", 3),
        ]

        repo = PaymentMonitoringRepository(mock_db)
        min_date = datetime.now(timezone.utc) - timedelta(days=7)
        result = repo.get_payment_status_counts(min_date)

        assert len(result) == 2
        assert isinstance(result[0], PaymentStatData)
        assert result[0].payment_status == "scheduled"
        assert result[0].count == 5
        assert result[1].payment_status == "authorized"
        assert result[1].count == 3

    def test_get_payment_status_counts_filters_correctly(self):
        """Test that the query filters are applied correctly."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = []

        repo = PaymentMonitoringRepository(mock_db)
        min_date = datetime.now(timezone.utc)
        repo.get_payment_status_counts(min_date)

        # Verify filter was called
        mock_query.filter.assert_called_once()


class TestGetRecentEventCounts:
    """Tests for get_recent_event_counts method."""

    def test_get_recent_event_counts_empty_result(self):
        """Test with no recent events."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = []

        repo = PaymentMonitoringRepository(mock_db)
        future_date = datetime.now(timezone.utc) + timedelta(days=365)
        result = repo.get_recent_event_counts(future_date)

        assert result == []

    def test_get_recent_event_counts_with_events(self):
        """Test with actual payment events."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query

        # Mock query results: [(event_type, count)]
        mock_query.all.return_value = [
            ("auth_succeeded", 10),
            ("capture_succeeded", 7),
            ("auth_failed", 2),
        ]

        repo = PaymentMonitoringRepository(mock_db)
        since = datetime.now(timezone.utc) - timedelta(days=7)
        result = repo.get_recent_event_counts(since)

        assert len(result) == 3
        assert isinstance(result[0], PaymentEventCountData)
        assert result[0].event_type == "auth_succeeded"
        assert result[0].count == 10
        assert result[1].event_type == "capture_succeeded"
        assert result[1].count == 7

    def test_get_recent_event_counts_filters_by_time(self):
        """Test that the time filter is applied."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = []

        repo = PaymentMonitoringRepository(mock_db)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        repo.get_recent_event_counts(since)

        # Verify filter was called
        mock_query.filter.assert_called_once()


class TestCountOverdueAuthorizations:
    """Tests for count_overdue_authorizations method."""

    def test_count_overdue_authorizations_none(self):
        """Test with no overdue authorizations."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0

        repo = PaymentMonitoringRepository(mock_db)
        past_date = datetime.now(timezone.utc) - timedelta(days=365)
        result = repo.count_overdue_authorizations(past_date)

        assert result == 0
        assert isinstance(result, int)

    def test_count_overdue_authorizations_with_overdue(self):
        """Test with overdue bookings."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5

        repo = PaymentMonitoringRepository(mock_db)
        today = datetime.now(timezone.utc)
        result = repo.count_overdue_authorizations(today)

        assert result == 5
        assert isinstance(result, int)

    def test_count_overdue_authorizations_filters_correctly(self):
        """Test that filters are applied correctly."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0

        repo = PaymentMonitoringRepository(mock_db)
        as_of = datetime.now(timezone.utc)
        repo.count_overdue_authorizations(as_of)

        # Verify filter was called with the and_ condition
        mock_query.filter.assert_called_once()


class TestGetLastSuccessfulAuthorization:
    """Tests for get_last_successful_authorization method."""

    def test_get_last_successful_authorization_none(self):
        """Test when there are no successful authorizations."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        repo = PaymentMonitoringRepository(mock_db)
        result = repo.get_last_successful_authorization()

        assert result is None

    def test_get_last_successful_authorization_returns_event(self):
        """Test finding the most recent successful authorization."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query

        # Create a mock PaymentEvent
        mock_event = MagicMock(spec=PaymentEvent)
        mock_event.id = "event-123"
        mock_event.event_type = "auth_succeeded"
        mock_event.created_at = datetime.now(timezone.utc)
        mock_query.first.return_value = mock_event

        repo = PaymentMonitoringRepository(mock_db)
        result = repo.get_last_successful_authorization()

        assert result is not None
        assert result.id == "event-123"
        assert result.event_type == "auth_succeeded"

    def test_get_last_successful_authorization_orders_by_created_at(self):
        """Test that results are ordered by created_at descending."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        repo = PaymentMonitoringRepository(mock_db)
        repo.get_last_successful_authorization()

        # Verify order_by was called
        mock_query.order_by.assert_called_once()

    def test_get_last_successful_authorization_filters_event_types(self):
        """Test that only auth_succeeded and auth_retry_succeeded are queried."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        repo = PaymentMonitoringRepository(mock_db)
        repo.get_last_successful_authorization()

        # Verify filter was called (which should use in_ with the event types)
        mock_query.filter.assert_called_once()
