"""
Coverage tests for payment_repository.py targeting uncovered edge-case paths.

Covers: error handling in every repository method, edge cases with None/empty
parameters, IntegrityError propagation for connected accounts, and payout
event recording.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import RepositoryException


def _make_repo() -> Any:
    """Create PaymentRepository with mocked db session."""
    from app.repositories.payment_repository import PaymentRepository

    repo = PaymentRepository.__new__(PaymentRepository)
    repo.db = MagicMock()
    repo.model = MagicMock()
    repo.logger = MagicMock()
    return repo


@pytest.mark.unit
class TestCreateCustomerRecord:
    @patch("app.repositories.payment_repository.ulid")
    def test_success(self, mock_ulid):
        mock_ulid.ULID.return_value = "01TESTCUST000000000000001"
        repo = _make_repo()
        repo.create_customer_record("USER1", "cus_test123")
        repo.db.add.assert_called_once()
        repo.db.flush.assert_called_once()

    def test_failure_raises(self):
        repo = _make_repo()
        repo.db.add.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException, match="Failed to create customer record"):
            repo.create_customer_record("USER1", "cus_test123")


@pytest.mark.unit
class TestGetCustomerByUserId:
    def test_found(self):
        repo = _make_repo()
        mock_customer = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_customer
        result = repo.get_customer_by_user_id("USER1")
        assert result is mock_customer

    def test_not_found(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.get_customer_by_user_id("USER1")
        assert result is None

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("connection error")
        with pytest.raises(RepositoryException):
            repo.get_customer_by_user_id("USER1")


@pytest.mark.unit
class TestGetCustomerByStripeId:
    def test_found(self):
        repo = _make_repo()
        mock_customer = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_customer
        result = repo.get_customer_by_stripe_id("cus_test")
        assert result is mock_customer

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.get_customer_by_stripe_id("cus_test")


@pytest.mark.unit
class TestCreateConnectedAccountRecord:
    @patch("app.repositories.payment_repository.ulid")
    def test_success(self, mock_ulid):
        mock_ulid.ULID.return_value = "01TESTACCT000000000000001"
        repo = _make_repo()
        repo.create_connected_account_record("PROF1", "acct_test")
        repo.db.add.assert_called_once()
        repo.db.flush.assert_called_once()

    def test_integrity_error_propagates(self):
        from sqlalchemy.exc import IntegrityError

        repo = _make_repo()
        repo.db.add.side_effect = IntegrityError("", {}, Exception())
        with pytest.raises(IntegrityError):
            repo.create_connected_account_record("PROF1", "acct_test")

    def test_generic_error(self):
        repo = _make_repo()
        repo.db.add.side_effect = ValueError("unexpected")
        with pytest.raises(RepositoryException):
            repo.create_connected_account_record("PROF1", "acct_test")


@pytest.mark.unit
class TestGetConnectedAccountByInstructorId:
    def test_found(self):
        repo = _make_repo()
        mock_account = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_account
        result = repo.get_connected_account_by_instructor_id("PROF1")
        assert result is mock_account

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.get_connected_account_by_instructor_id("PROF1")


@pytest.mark.unit
class TestUpdateOnboardingStatus:
    def test_found(self):
        repo = _make_repo()
        mock_account = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_account
        result = repo.update_onboarding_status("acct_test", True)
        assert result is mock_account
        assert mock_account.onboarding_completed is True

    def test_not_found(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.update_onboarding_status("acct_test", True)
        assert result is None

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.update_onboarding_status("acct_test", True)


@pytest.mark.unit
class TestCreatePaymentRecord:
    @patch("app.repositories.payment_repository.ulid")
    def test_success(self, mock_ulid):
        mock_ulid.ULID.return_value = "01TESTPAY0000000000000001"
        repo = _make_repo()
        repo.create_payment_record("B1", "pi_test", 5000, 750)
        repo.db.add.assert_called_once()
        repo.db.flush.assert_called_once()

    @patch("app.repositories.payment_repository.ulid")
    def test_with_extra_fields(self, mock_ulid):
        mock_ulid.ULID.return_value = "01TESTPAY0000000000000002"
        repo = _make_repo()
        repo.create_payment_record(
            "B1", "pi_test", 5000, 750,
            base_price_cents=4500,
            instructor_tier_pct=Decimal("0.12"),
            instructor_payout_cents=3960,
        )
        repo.db.add.assert_called_once()

    def test_error(self):
        repo = _make_repo()
        repo.db.add.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.create_payment_record("B1", "pi_test", 5000, 750)


@pytest.mark.unit
class TestUpdatePaymentStatus:
    def test_found(self):
        repo = _make_repo()
        mock_payment = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_payment
        repo.update_payment_status("pi_test", "succeeded")
        assert mock_payment.status == "succeeded"

    def test_not_found(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.update_payment_status("pi_test", "succeeded")
        assert result is None

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.update_payment_status("pi_test", "succeeded")


@pytest.mark.unit
class TestGetPaymentByIntentId:
    def test_found(self):
        repo = _make_repo()
        mock_payment = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_payment
        result = repo.get_payment_by_intent_id("pi_test")
        assert result is mock_payment

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_payment_by_intent_id("pi_test")


@pytest.mark.unit
class TestGetPaymentByBookingId:
    def test_found(self):
        repo = _make_repo()
        mock_payment = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_payment
        result = repo.get_payment_by_booking_id("B1")
        assert result is mock_payment

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_payment_by_booking_id("B1")


@pytest.mark.unit
class TestGetPaymentIntentsForBooking:
    def test_success(self):
        repo = _make_repo()
        mock_list = [MagicMock(), MagicMock()]
        repo.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_list
        result = repo.get_payment_intents_for_booking("B1")
        assert len(result) == 2

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_payment_intents_for_booking("B1")


@pytest.mark.unit
class TestFindPaymentByBookingAndAmount:
    def test_found(self):
        repo = _make_repo()
        mock_payment = MagicMock()
        repo.db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_payment
        result = repo.find_payment_by_booking_and_amount("B1", 5000)
        assert result is mock_payment

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.find_payment_by_booking_and_amount("B1", 5000)


@pytest.mark.unit
class TestGetPaymentByBookingPrefix:
    def test_found(self):
        repo = _make_repo()
        mock_payment = MagicMock()
        repo.db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_payment
        result = repo.get_payment_by_booking_prefix("01TEST")
        assert result is mock_payment

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_payment_by_booking_prefix("01TEST")


@pytest.mark.unit
class TestRecordPayoutEvent:
    def test_success(self):
        repo = _make_repo()
        repo.record_payout_event(
            instructor_profile_id="PROF1",
            stripe_account_id="acct_test",
            payout_id="po_test",
            amount_cents=10000,
            status="paid",
            arrival_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
        )
        repo.db.add.assert_called_once()
        repo.db.flush.assert_called_once()

    def test_with_failure(self):
        repo = _make_repo()
        repo.record_payout_event(
            instructor_profile_id="PROF1",
            stripe_account_id="acct_test",
            payout_id="po_test",
            amount_cents=10000,
            status="failed",
            arrival_date=None,
            failure_code="insufficient_funds",
            failure_message="Not enough balance",
        )
        repo.db.add.assert_called_once()

    def test_error(self):
        repo = _make_repo()
        repo.db.add.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.record_payout_event(
                instructor_profile_id="PROF1",
                stripe_account_id="acct_test",
                payout_id="po_test",
                amount_cents=10000,
                status="paid",
                arrival_date=None,
            )


@pytest.mark.unit
class TestGetInstructorPayoutHistory:
    def test_success(self):
        repo = _make_repo()
        mock_list = [MagicMock()]
        repo.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_list
        result = repo.get_instructor_payout_history("PROF1")
        assert len(result) == 1

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_instructor_payout_history("PROF1")


@pytest.mark.unit
class TestGetConnectedAccountByStripeId:
    def test_found(self):
        repo = _make_repo()
        mock_account = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_account
        result = repo.get_connected_account_by_stripe_id("acct_test")
        assert result is mock_account

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_connected_account_by_stripe_id("acct_test")


@pytest.mark.unit
class TestSavePaymentMethod:
    def test_new_default(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        repo.db.query.return_value.filter.return_value.update.return_value = 0
        with patch("app.repositories.payment_repository.ulid") as mock_ulid:
            mock_ulid.ULID.return_value = "01TESTPM0000000000000001"
            repo.save_payment_method("USER1", "pm_test", "4242", "visa", is_default=True)
        repo.db.add.assert_called_once()

    def test_existing_method_set_default(self):
        repo = _make_repo()
        existing = MagicMock()
        existing.is_default = False
        repo.db.query.return_value.filter.return_value.first.return_value = existing
        repo.db.query.return_value.filter.return_value.update.return_value = 0
        repo.save_payment_method("USER1", "pm_test", "4242", "visa", is_default=True)
        assert existing.is_default is True

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.save_payment_method("USER1", "pm_test", "4242", "visa")


@pytest.mark.unit
class TestGetPaymentMethodsByUser:
    def test_success(self):
        repo = _make_repo()
        mock_list = [MagicMock(), MagicMock()]
        repo.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_list
        result = repo.get_payment_methods_by_user("USER1")
        assert len(result) == 2

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_payment_methods_by_user("USER1")


@pytest.mark.unit
class TestGetDefaultPaymentMethod:
    def test_found(self):
        repo = _make_repo()
        mock_method = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_method
        result = repo.get_default_payment_method("USER1")
        assert result is mock_method

    def test_not_found(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.get_default_payment_method("USER1")
        assert result is None

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("error")
        with pytest.raises(RepositoryException):
            repo.get_default_payment_method("USER1")


# ---------------------------------------------------------------------------
# Additional coverage tests targeting uncovered lines/branches
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetInstructorEarningsExportDateFilters:
    """Cover lines 928, 930: start_date and end_date filter branches."""

    def test_with_start_date_only(self):
        """Line 928: start_date is truthy, adds filter."""
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        from datetime import date
        result = repo.get_instructor_earnings_for_export(
            "INSTR1", start_date=date(2026, 1, 1), end_date=None
        )
        assert result == []

    def test_with_end_date_only(self):
        """Line 930: end_date is truthy, adds filter."""
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        from datetime import date
        result = repo.get_instructor_earnings_for_export(
            "INSTR1", start_date=None, end_date=date(2026, 12, 31)
        )
        assert result == []

    def test_with_both_dates(self):
        """Lines 928 + 930: both date filters applied."""
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        from datetime import date
        result = repo.get_instructor_earnings_for_export(
            "INSTR1",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assert result == []


@pytest.mark.unit
class TestGetInstructorEarningsExportStudentName:
    """Cover lines 938-948: student name formatting in export data."""

    def test_student_with_last_name(self):
        """Lines 940-946: student exists with last_name."""
        repo = _make_repo()

        payment = MagicMock()
        booking = MagicMock()
        booking.booking_date = "2026-03-15"
        booking.service_name = "Guitar"
        booking.duration_minutes = 60
        booking.hourly_rate = 50
        payment.amount = 5000
        payment.application_fee = 750
        payment.status = "succeeded"
        payment.stripe_payment_intent_id = "pi_test"
        payment.booking = booking

        student = MagicMock()
        student.first_name = "John"
        student.last_name = "Smith"
        booking.student = student

        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [payment]

        result = repo.get_instructor_earnings_for_export("INSTR1")
        assert len(result) == 1
        assert result[0]["student_name"] == "John S."

    def test_student_with_empty_last_name(self):
        """Lines 941-945: student with empty last_name."""
        repo = _make_repo()

        payment = MagicMock()
        booking = MagicMock()
        booking.booking_date = "2026-03-15"
        booking.service_name = "Piano"
        booking.duration_minutes = 30
        booking.hourly_rate = 40
        payment.amount = 2000
        payment.application_fee = 300
        payment.status = "succeeded"
        payment.stripe_payment_intent_id = "pi_test2"
        payment.booking = booking

        student = MagicMock()
        student.first_name = "Alice"
        student.last_name = ""
        booking.student = student

        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [payment]

        result = repo.get_instructor_earnings_for_export("INSTR1")
        assert result[0]["student_name"] == "Alice"

    def test_no_student(self):
        """Lines 938-946: student is None."""
        repo = _make_repo()

        payment = MagicMock()
        booking = MagicMock()
        booking.booking_date = "2026-03-15"
        booking.service_name = "Yoga"
        booking.duration_minutes = 45
        booking.hourly_rate = 35
        payment.amount = 2625
        payment.application_fee = 394
        payment.status = "succeeded"
        payment.stripe_payment_intent_id = "pi_test3"
        payment.booking = booking
        booking.student = None

        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [payment]

        result = repo.get_instructor_earnings_for_export("INSTR1")
        assert result[0]["student_name"] is None

    def test_no_booking_skipped(self):
        """Lines 935-936: payment has no booking."""
        repo = _make_repo()

        payment = MagicMock()
        payment.booking = None

        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [payment]

        result = repo.get_instructor_earnings_for_export("INSTR1")
        assert result == []

    def test_error_raises(self):
        """Lines 963-965: exception raises RepositoryException."""
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException, match="Failed to get instructor earnings export data"):
            repo.get_instructor_earnings_for_export("INSTR1")


@pytest.mark.unit
class TestCreatePaymentEventAuditFails:
    """Cover lines 1018-1019: audit logging failure is swallowed."""

    @patch("app.repositories.payment_repository.ulid")
    @patch("app.repositories.payment_repository.AuditService")
    def test_audit_raises_swallowed(self, mock_audit_cls, mock_ulid):
        mock_ulid.ULID.return_value = "01TESTEVT0000000000000001"
        repo = _make_repo()

        mock_audit = MagicMock()
        mock_audit.log.side_effect = Exception("audit failure")
        mock_audit_cls.return_value = mock_audit

        # Create event should still succeed
        repo.create_payment_event("B1", "auth_failed", {"error": "card_declined"})
        repo.db.add.assert_called_once()
        repo.db.flush.assert_called_once()


@pytest.mark.unit
class TestGetPaymentEventsForBookingWithLimit:
    """Cover line 1091: limit is not None."""

    def test_with_limit(self):
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.options.return_value.filter.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = repo.get_payment_events_for_booking("B1", limit=10)
        mock_query.limit.assert_called_once_with(10)
        assert result == []


@pytest.mark.unit
class TestGetPaymentEventsForUserFilters:
    """Cover lines 1130->1132, 1132->1134, 1136, 1138-1140."""

    def test_with_start_time(self):
        """Line 1130->1132: start_time is truthy."""
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        from datetime import datetime, timezone
        result = repo.get_payment_events_for_user(
            "USER1",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert result == []

    def test_with_end_time(self):
        """Line 1132->1134: end_time is truthy."""
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        from datetime import datetime, timezone
        result = repo.get_payment_events_for_user(
            "USER1",
            end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )
        assert result == []

    def test_with_limit(self):
        """Line 1136: limit is not None."""
        repo = _make_repo()
        mock_query = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value.filter.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        repo.get_payment_events_for_user("USER1", limit=5)
        mock_query.limit.assert_called_once_with(5)

    def test_error_raises(self):
        """Lines 1138-1140: error raises RepositoryException."""
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException, match="Failed to get payment events for user"):
            repo.get_payment_events_for_user("USER1")


@pytest.mark.unit
class TestListPaymentEventsByTypesError:
    """Cover lines 1183-1185: error raises RepositoryException."""

    def test_error_raises(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException, match="Failed to list payment events"):
            repo.list_payment_events_by_types(["auth_failed"])


@pytest.mark.unit
class TestCountPaymentEventsByTypesError:
    """Cover lines 1206-1208: error raises RepositoryException."""

    def test_error_raises(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException, match="Failed to count payment events"):
            repo.count_payment_events_by_types(["auth_failed"])
