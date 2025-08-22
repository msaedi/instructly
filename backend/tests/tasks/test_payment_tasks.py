"""
Tests for payment processing Celery tasks.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, call, patch

import pytest
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.payment import PaymentEvent
from app.tasks.payment_tasks import (
    capture_completed_lessons,
    check_authorization_health,
    process_scheduled_authorizations,
    retry_failed_authorizations,
)


class TestPaymentTasks:
    """Test suite for payment Celery tasks."""

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.tasks.payment_tasks.get_db")
    def test_process_scheduled_authorizations_success(self, mock_get_db, mock_stripe_service):
        """Test successful processing of scheduled authorizations."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock booking that needs authorization
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_test123"
        booking.booking_date = date.today()
        booking.start_time = time(14, 0)  # 2 PM
        booking.total_price = 100.00

        # Mock query to return the booking
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock Stripe service
        mock_stripe = mock_stripe_service.return_value
        mock_payment_intent = MagicMock()
        mock_payment_intent.id = "pi_test123"
        mock_stripe.create_payment_intent.return_value = mock_payment_intent

        # Mock payment repository
        mock_payment_repo = MagicMock()
        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            # Execute task
            result = process_scheduled_authorizations()

        # Verify results
        assert result["success"] == 1
        assert result["failed"] == 0
        assert booking.payment_intent_id == "pi_test123"
        assert booking.payment_status == "authorized"

        # Verify payment event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_succeeded"

        # Verify database commit
        mock_db.commit.assert_called_once()

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.tasks.payment_tasks.get_db")
    def test_process_scheduled_authorizations_failure(self, mock_get_db, mock_stripe_service):
        """Test handling of authorization failures."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_test123"
        booking.booking_date = date.today()
        booking.start_time = time(14, 0)
        booking.total_price = 100.00

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock Stripe service to raise exception
        mock_stripe = mock_stripe_service.return_value
        mock_stripe.create_payment_intent.side_effect = Exception("Card declined")

        # Mock payment repository
        mock_payment_repo = MagicMock()
        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            # Execute task
            result = process_scheduled_authorizations()

        # Verify results
        assert result["success"] == 0
        assert result["failed"] == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0]["error"] == "Card declined"
        assert booking.payment_status == "auth_failed"

        # Verify failure event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_failed"

    @patch("app.tasks.payment_tasks.get_db")
    def test_retry_failed_authorizations_success(self, mock_get_db):
        """Test successful retry of failed authorizations."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock booking with failed auth
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_test123"
        booking.booking_date = date.today() + timedelta(days=1)
        booking.total_price = 100.00

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock payment repository with retry count
        mock_payment_repo = MagicMock()
        mock_event = MagicMock()
        mock_event.event_type = "auth_failed"
        mock_payment_repo.get_payment_events_for_booking.return_value = [mock_event]

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                mock_stripe = mock_stripe_service.return_value
                mock_payment_intent = MagicMock()
                mock_payment_intent.id = "pi_retry123"
                mock_stripe.create_payment_intent.return_value = mock_payment_intent

                # Execute task
                result = retry_failed_authorizations()

        # Verify results
        assert result["retried"] == 1
        assert result["success"] == 1
        assert result["failed"] == 0
        assert result["abandoned"] == 0
        assert booking.payment_intent_id == "pi_retry123"
        assert booking.payment_status == "authorized"

    @patch("app.tasks.payment_tasks.get_db")
    def test_retry_failed_authorizations_abandon(self, mock_get_db):
        """Test abandoning bookings after too many retries."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_test123"
        booking.booking_date = date.today() + timedelta(days=1)

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock payment repository with 3 failed attempts
        mock_payment_repo = MagicMock()
        mock_events = [MagicMock(event_type="auth_failed") for _ in range(3)]
        mock_payment_repo.get_payment_events_for_booking.return_value = mock_events

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            # Execute task
            result = retry_failed_authorizations()

        # Verify results
        assert result["retried"] == 0
        assert result["abandoned"] == 1
        assert booking.payment_status == "auth_abandoned"

        # Verify abandonment event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_abandoned"

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_completed_lessons(self, mock_get_db, mock_stripe_service):
        """Test capturing payments for completed lessons."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock completed booking
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_test123"

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock Stripe service
        mock_stripe = mock_stripe_service.return_value
        mock_captured_intent = MagicMock()
        mock_captured_intent.amount_received = 10000  # $100 in cents
        mock_stripe.capture_payment_intent.return_value = mock_captured_intent

        # Mock payment repository
        mock_payment_repo = MagicMock()
        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            # Execute task
            result = capture_completed_lessons()

        # Verify results
        assert result["captured"] == 1
        assert result["failed"] == 0
        assert booking.payment_status == "captured"

        # Verify capture was called
        mock_stripe.capture_payment_intent.assert_called_once_with("pi_test123")

        # Verify capture event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "payment_captured"

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_healthy(self, mock_get_db):
        """Test health check when system is healthy."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock no overdue bookings
        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 0
        mock_db.query.return_value = mock_query

        # Mock recent authorization event
        mock_payment_repo = MagicMock()
        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            # Mock recent event
            mock_event = MagicMock()
            mock_event.created_at = datetime.utcnow() - timedelta(minutes=30)
            mock_query_event = MagicMock()
            mock_query_event.filter.return_value.order_by.return_value.first.return_value = mock_event
            mock_db.query.side_effect = [mock_query, mock_query_event]

            # Execute task
            result = check_authorization_health()

        # Verify results
        assert result["healthy"] is True
        assert result["overdue_authorizations"] == 0
        assert result["minutes_since_last_auth"] <= 31

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_unhealthy(self, mock_get_db):
        """Test health check when system has issues."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock many overdue bookings
        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 10
        mock_db.query.return_value = mock_query

        # Mock no recent authorization events
        mock_payment_repo = MagicMock()
        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            mock_query_event = MagicMock()
            mock_query_event.filter.return_value.order_by.return_value.first.return_value = None
            mock_db.query.side_effect = [mock_query, mock_query_event]

            # Execute task
            result = check_authorization_health()

        # Verify results
        assert result["healthy"] is False
        assert result["overdue_authorizations"] == 10
        assert result["minutes_since_last_auth"] is None
