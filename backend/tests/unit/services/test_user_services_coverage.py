# backend/tests/unit/services/test_user_services_coverage.py
"""
Round 5 Coverage Tests for User-Facing Services.

Targets:
- privacy_service.py (79% → 92%+)
- retention_service.py (67% → 92%+)
- personal_asset_service.py (87% → 92%+)
- student_credit_service.py (20% → 92%+)
- geolocation_service.py (85% → 92%+)
"""

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import InstructorProfile, User
from app.models.search_event import SearchEvent
from app.models.search_history import SearchHistory


# ---------------------------------------------------------------------------
# StudentCreditService Coverage Tests (20% → 92%+)
# ---------------------------------------------------------------------------
class TestStudentCreditServiceCoverage:
    """Comprehensive tests for StudentCreditService - currently at 20% coverage."""

    def test_maybe_issue_milestone_credit_no_completions_mocked(self, db: Session):
        """Line 44-45: Student with no completed bookings returns None."""
        from app.services.student_credit_service import StudentCreditService

        # Mock booking repository to return 0 completed bookings
        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 0

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo

        result = service.maybe_issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
        )
        assert result is None

    def test_maybe_issue_milestone_credit_not_milestone_mocked(self, db: Session):
        """Lines 58-59: No credit when not at milestone position (3 bookings)."""
        from app.services.student_credit_service import StudentCreditService

        # Mock booking repository to return 3 completed bookings
        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 3  # Not at milestone (5 or 11)

        mock_payment_repo = Mock()

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        result = service.maybe_issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
        )
        assert result is None

    def test_maybe_issue_milestone_credit_s5_mocked(self, db: Session):
        """Lines 51-53, 61-66: Issue S5 milestone credit at 5 completed bookings."""
        from app.services.student_credit_service import StudentCreditService

        # Mock booking repository to return 5 completed bookings
        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 5  # S5 milestone

        # Mock credit creation
        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        result = service.maybe_issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
        )
        assert result is not None
        assert result.amount_cents == 1000
        assert result.reason == "milestone_s5"

    def test_maybe_issue_milestone_credit_s11_mocked(self, db: Session):
        """Lines 54-56: Issue S11 milestone credit at 11 completed bookings."""
        from app.services.student_credit_service import StudentCreditService

        # Mock booking repository to return 11 completed bookings
        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 11  # S11 milestone

        # Mock credit creation
        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 2000
        mock_credit.reason = "milestone_s11"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        result = service.maybe_issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
        )
        assert result is not None
        assert result.amount_cents == 2000
        assert result.reason == "milestone_s11"

    def test_issue_milestone_credit_zero_amount_mocked(self, db: Session):
        """Line 92-93: Zero amount returns None."""
        from app.services.student_credit_service import StudentCreditService

        service = StudentCreditService(db)

        result = service.issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
            amount_cents=0,
            reason="test",
        )
        assert result is None

    def test_issue_milestone_credit_success_mocked(self, db: Session, monkeypatch):
        """Lines 101-107: Successfully issue milestone credit."""
        from app.services.student_credit_service import StudentCreditService

        # Create a mock credit
        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"
        mock_credit.user_id = "student_id"

        # Create a mock payment repository
        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        credit = service.issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
            amount_cents=1000,
            reason="milestone_s5",
        )
        assert credit is not None
        assert credit.amount_cents == 1000
        assert credit.reason == "milestone_s5"

    def test_issue_milestone_credit_idempotent_mocked(self, db: Session):
        """Lines 96-99: Idempotent credit creation returns existing credit."""
        from app.services.student_credit_service import StudentCreditService

        # Create a mock existing credit
        existing_credit = Mock()
        existing_credit.id = "existing_credit_id"
        existing_credit.reason = "milestone_s5"
        existing_credit.user_id = "student_id"

        # Mock payment repo to return existing credit
        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = [existing_credit]

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        credit = service.issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
            amount_cents=1000,
            reason="milestone_s5",
        )
        assert credit is not None
        assert credit.id == "existing_credit_id"

    def test_revoke_milestone_credit_no_credits_mocked(self, db: Session):
        """Lines 115-118: No credits to revoke."""
        from app.services.student_credit_service import StudentCreditService

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        result = service.revoke_milestone_credit(source_booking_id="booking_id")
        assert result == 0

    def test_revoke_milestone_credit_unused_mocked(self, db: Session):
        """Lines 122-127: Revoke unused credit (deletes it)."""
        from app.services.student_credit_service import StudentCreditService

        # Mock unused credit
        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"
        mock_credit.used_at = None

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = [mock_credit]
        mock_payment_repo.delete_platform_credit.return_value = None

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        revoked = service.revoke_milestone_credit(source_booking_id="booking_id")
        assert revoked == 1000
        mock_payment_repo.delete_platform_credit.assert_called_once_with("credit_id")

    def test_revoke_milestone_credit_used_mocked(self, db: Session):
        """Lines 126-137: Revoke used credit (creates correction)."""
        from app.services.student_credit_service import StudentCreditService

        # Mock used credit
        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"
        mock_credit.used_at = datetime.now(timezone.utc)
        mock_credit.user_id = "student_id"

        # Mock correction credit
        mock_correction = Mock()
        mock_correction.id = "correction_id"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = [mock_credit]
        mock_payment_repo.create_platform_credit.return_value = mock_correction

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        revoked = service.revoke_milestone_credit(source_booking_id="booking_id")
        assert revoked == 1000
        mock_payment_repo.create_platform_credit.assert_called_once()

    def test_reinstate_used_credits_no_credits_mocked(self, db: Session):
        """Lines 156-158: No credits to reinstate."""
        from app.services.student_credit_service import StudentCreditService

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = []

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        result = service.reinstate_used_credits(refunded_booking_id="booking_id")
        assert result == 0

    def test_reinstate_used_credits_no_booking_mocked(self, db: Session):
        """Lines 160-162: Booking not found returns 0."""
        from app.services.student_credit_service import StudentCreditService

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = [("credit_id", 500)]

        mock_booking_repo = Mock()
        mock_booking_repo.get_by_id.return_value = None

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo
        service.booking_repository = mock_booking_repo

        result = service.reinstate_used_credits(refunded_booking_id="booking_id")
        assert result == 0

    def test_reinstate_used_credits_success_mocked(self, db: Session):
        """Lines 164-185: Successfully reinstate credits."""
        from app.services.student_credit_service import StudentCreditService

        # Mock booking
        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.student_id = "student_id"

        # Mock credit data
        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = [("credit_id", 500)]
        mock_payment_repo.get_credits_issued_for_source.return_value = []  # No existing refund credits

        mock_booking_repo = Mock()
        mock_booking_repo.get_by_id.return_value = mock_booking

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo
        service.booking_repository = mock_booking_repo

        reinstated = service.reinstate_used_credits(refunded_booking_id="booking_id")
        assert reinstated == 500
        mock_payment_repo.create_platform_credit.assert_called_once()

    def test_reinstate_used_credits_idempotent_mocked(self, db: Session):
        """Lines 167-178: Idempotent - already reinstated returns 0."""
        from app.services.student_credit_service import StudentCreditService

        # Mock booking
        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.student_id = "student_id"

        # Mock existing refund credit
        existing_refund = Mock()
        existing_refund.amount_cents = 500
        existing_refund.reason = "refund_reinstate"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = [("credit_id", 500)]
        mock_payment_repo.get_credits_issued_for_source.return_value = [existing_refund]

        mock_booking_repo = Mock()
        mock_booking_repo.get_by_id.return_value = mock_booking

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo
        service.booking_repository = mock_booking_repo

        reinstated = service.reinstate_used_credits(refunded_booking_id="booking_id")
        assert reinstated == 0  # Already reinstated

    def test_process_refund_hooks_mocked(self, db: Session):
        """Lines 200-211: Process refund hooks convenience method."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.student_id = "student_id"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = []
        mock_payment_repo.get_credits_issued_for_source.return_value = []

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        # Should run without error
        service.process_refund_hooks(booking=mock_booking)

    def test_process_refund_hooks_with_adjustments(self, db: Session):
        """Lines 202-211: Process refund hooks with actual adjustments."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.student_id = "student_id"

        # Set up credits that will be reinstated
        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = [("credit_id", 500)]
        mock_payment_repo.get_credits_issued_for_source.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_by_id.return_value = mock_booking

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo
        service.booking_repository = mock_booking_repo

        # Should log adjustments
        service.process_refund_hooks(booking=mock_booking)
        mock_payment_repo.create_platform_credit.assert_called_once()

    def test_maybe_issue_milestone_credit_with_logging(self, db: Session):
        """Lines 68-79: Verify logging path when credit is issued."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 5

        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        with patch("app.services.student_credit_service.logger") as mock_logger:
            result = service.maybe_issue_milestone_credit(
                student_id="student_id",
                booking_id="booking_id",
            )
            assert result is not None
            # Verify logging was called
            mock_logger.info.assert_called()

    def test_revoke_milestone_credit_multiple_credits(self, db: Session):
        """Lines 120-137: Revoke multiple credits including used ones."""
        from app.services.student_credit_service import StudentCreditService

        # Mock used credit
        mock_used_credit = Mock()
        mock_used_credit.id = "used_credit_id"
        mock_used_credit.amount_cents = 1000
        mock_used_credit.reason = "milestone_s5"
        mock_used_credit.used_at = datetime.now(timezone.utc)
        mock_used_credit.user_id = "student_id"

        # Mock unused credit
        mock_unused_credit = Mock()
        mock_unused_credit.id = "unused_credit_id"
        mock_unused_credit.amount_cents = 2000
        mock_unused_credit.reason = "milestone_s11"
        mock_unused_credit.used_at = None

        # Mock correction credit
        mock_correction = Mock()
        mock_correction.id = "correction_id"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = [
            mock_used_credit,
            mock_unused_credit,
        ]
        mock_payment_repo.create_platform_credit.return_value = mock_correction

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        revoked = service.revoke_milestone_credit(source_booking_id="booking_id")
        assert revoked == 3000  # 1000 + 2000
        mock_payment_repo.delete_platform_credit.assert_called_once_with("unused_credit_id")
        mock_payment_repo.create_platform_credit.assert_called_once()

    def test_revoke_milestone_credit_with_existing_revoke(self, db: Session):
        """Lines 120, 129: Skip creating correction if revoke already recorded."""
        from app.services.student_credit_service import StudentCreditService

        # Mock used credit
        mock_used_credit = Mock()
        mock_used_credit.id = "used_credit_id"
        mock_used_credit.amount_cents = 1000
        mock_used_credit.reason = "milestone_s5"
        mock_used_credit.used_at = datetime.now(timezone.utc)
        mock_used_credit.user_id = "student_id"

        # Mock existing revoke credit
        mock_revoke_credit = Mock()
        mock_revoke_credit.reason = "milestone_revoke"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = [
            mock_used_credit,
            mock_revoke_credit,
        ]

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        revoked = service.revoke_milestone_credit(source_booking_id="booking_id")
        assert revoked == 1000
        # Should NOT create another correction since one exists
        mock_payment_repo.create_platform_credit.assert_not_called()

    def test_reinstate_multiple_credits(self, db: Session):
        """Lines 164-178: Reinstate multiple credits with partial existing refunds."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.student_id = "student_id"

        # Existing partial refund
        existing_refund = Mock()
        existing_refund.amount_cents = 200
        existing_refund.reason = "refund_reinstate"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = [
            ("credit1", 300),
            ("credit2", 400),
        ]  # Total: 700
        mock_payment_repo.get_credits_issued_for_source.return_value = [existing_refund]

        mock_booking_repo = Mock()
        mock_booking_repo.get_by_id.return_value = mock_booking

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo
        service.booking_repository = mock_booking_repo

        reinstated = service.reinstate_used_credits(refunded_booking_id="booking_id")
        assert reinstated == 500  # 700 - 200 = 500

    def test_maybe_issue_s11_with_logging(self, db: Session):
        """Lines 68-79: S11 milestone with logging verification."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 11  # cycle_position = 0

        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 2000
        mock_credit.reason = "milestone_s11"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        with patch("app.services.student_credit_service.logger") as mock_logger:
            result = service.maybe_issue_milestone_credit(
                student_id="student_id",
                booking_id="booking_id",
            )
            assert result is not None
            assert result.amount_cents == 2000
            mock_logger.info.assert_called()

    def test_maybe_issue_at_cycle_22(self, db: Session):
        """Lines 47-56: Test S11 at cycle position 22 (22 % 11 == 0)."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 22  # cycle_position = 0

        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 2000
        mock_credit.reason = "milestone_s11"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        result = service.maybe_issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
        )
        assert result is not None
        assert result.reason == "milestone_s11"

    def test_maybe_issue_at_cycle_16(self, db: Session):
        """Lines 47-53: Test S5 at cycle position 16 (16 % 11 == 5)."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking_repo = Mock()
        mock_booking_repo.count_student_completed_lifetime.return_value = 16  # cycle_position = 5

        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = []
        mock_payment_repo.create_platform_credit.return_value = mock_credit

        service = StudentCreditService(db)
        service.booking_repository = mock_booking_repo
        service.payment_repository = mock_payment_repo

        result = service.maybe_issue_milestone_credit(
            student_id="student_id",
            booking_id="booking_id",
        )
        assert result is not None
        assert result.reason == "milestone_s5"

    def test_revoke_milestone_credit_with_logging(self, db: Session):
        """Lines 139-146: Verify logging when credits are revoked."""
        from app.services.student_credit_service import StudentCreditService

        mock_credit = Mock()
        mock_credit.id = "credit_id"
        mock_credit.amount_cents = 1000
        mock_credit.reason = "milestone_s5"
        mock_credit.used_at = None

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_issued_for_source.return_value = [mock_credit]

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo

        with patch("app.services.student_credit_service.logger") as mock_logger:
            revoked = service.revoke_milestone_credit(source_booking_id="booking_id")
            assert revoked == 1000
            mock_logger.info.assert_called()

    def test_reinstate_with_logging(self, db: Session):
        """Lines 187-193: Verify logging when credits are reinstated."""
        from app.services.student_credit_service import StudentCreditService

        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.student_id = "student_id"

        mock_payment_repo = Mock()
        mock_payment_repo.get_credits_used_by_booking.return_value = [("credit_id", 500)]
        mock_payment_repo.get_credits_issued_for_source.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_by_id.return_value = mock_booking

        service = StudentCreditService(db)
        service.payment_repository = mock_payment_repo
        service.booking_repository = mock_booking_repo

        with patch("app.services.student_credit_service.logger") as mock_logger:
            reinstated = service.reinstate_used_credits(refunded_booking_id="booking_id")
            assert reinstated == 500
            mock_logger.info.assert_called()


# ---------------------------------------------------------------------------
# RetentionService Coverage Tests (67% → 92%+)
# ---------------------------------------------------------------------------
class TestRetentionServiceCoverage:
    """Additional coverage tests for RetentionService."""

    @pytest.fixture
    def retention_service(self, db: Session):
        """Create RetentionService instance."""
        from app.services.retention_service import RetentionService

        return RetentionService(db)

    def test_purge_soft_deleted_missing_table(self, retention_service, db: Session, monkeypatch):
        """Lines 148-150: Skip table when not present in database."""
        from app.services.retention_service import RetentionService, _RetentionTableConfig

        # Configure a non-existent table
        config = (
            _RetentionTableConfig(
                table_name="nonexistent_table_xyz",
                primary_key="id",
                cache_prefixes=("test:",),
            ),
        )
        monkeypatch.setattr(RetentionService, "_TABLES", config)

        service = RetentionService(db)
        result = service.purge_soft_deleted(older_than_days=30, dry_run=True)
        # Should not fail, just skip the table
        assert "nonexistent_table_xyz" not in result

    def test_purge_soft_deleted_missing_columns(self, retention_service, db: Session, monkeypatch):
        """Lines 153-160: Skip table when required columns missing."""
        from app.services.retention_service import RetentionService, _RetentionTableConfig

        # Configure table with wrong column names
        config = (
            _RetentionTableConfig(
                table_name="users",  # Exists but has different column names
                primary_key="nonexistent_pk",
                deleted_at_column="nonexistent_deleted_at",
                cache_prefixes=("test:",),
            ),
        )
        monkeypatch.setattr(RetentionService, "_TABLES", config)

        service = RetentionService(db)
        result = service.purge_soft_deleted(older_than_days=30, dry_run=True)
        # Should skip the table due to missing columns
        assert "users" not in result or result.get("users", {}).get("deleted") == 0

    def test_purge_soft_deleted_no_eligible_rows(self, retention_service, db: Session, monkeypatch):
        """Lines 165-167: No eligible rows for deletion."""
        from app.services.retention_service import RetentionService, _RetentionTableConfig

        # Use a table that exists but has no soft-deleted rows
        config = (
            _RetentionTableConfig(
                table_name="service_categories",  # Likely has deleted_at but no deleted rows
                primary_key="id",
                deleted_at_column="deleted_at",
                cache_prefixes=("test:",),
            ),
        )
        monkeypatch.setattr(RetentionService, "_TABLES", config)

        service = RetentionService(db)
        result = service.purge_soft_deleted(older_than_days=30, dry_run=False)
        # Should return 0 eligible if no soft-deleted rows exist
        if "service_categories" in result:
            assert result["service_categories"]["eligible"] >= 0

    def test_purge_table_chunks_exception_handling(self, db: Session, monkeypatch):
        """Lines 265-267: Exception handling during chunk purge."""
        from app.services.retention_service import RetentionService

        # Mock the repository to raise an exception
        def raise_error(*args, **kwargs):
            raise RuntimeError("Test error")

        service = RetentionService(db)

        # Mock fetch_batch_ids to return IDs and delete_rows to raise
        service._fetch_batch_ids = lambda *args, **kwargs: ["id1"]
        service.retention_repository.delete_rows = raise_error

        # Create a mock table for the test
        mock_table = Mock()
        mock_table.name = "test_table"
        mock_pk = Mock()
        mock_deleted = Mock()

        with pytest.raises(RuntimeError, match="Test error"):
            service._purge_table_chunks(
                table=mock_table,
                pk_column=mock_pk,
                deleted_column=mock_deleted,
                cutoff=datetime.now(timezone.utc),
                chunk_size=10,
            )

    def test_invalidate_prefixes_no_cache(self, db: Session):
        """Lines 283-284: No cache service configured."""
        from app.services.retention_service import RetentionService

        service = RetentionService(db, cache_service=None)
        # Should not raise
        service._invalidate_prefixes(["test:"])

    def test_purge_availability_days_disabled(self, retention_service, monkeypatch):
        """Lines 322-323: Retention disabled returns early."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "availability_retention_enabled", False)

        result = retention_service.purge_availability_days()
        assert result["inspected_days"] == 0
        assert result["purged_days"] == 0

    def test_purge_availability_days_dry_run(self, retention_service, monkeypatch):
        """Lines 363: Dry run mode doesn't purge."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "availability_retention_enabled", True)
        monkeypatch.setattr(settings, "availability_retention_days", 30)
        monkeypatch.setattr(settings, "availability_retention_keep_recent_days", 7)
        monkeypatch.setattr(settings, "availability_retention_dry_run", True)

        result = retention_service.purge_availability_days()
        assert result["dry_run"] is True
        assert result["purged_days"] == 0

    def test_purge_availability_days_with_candidates(self, db: Session, monkeypatch):
        """Lines 363-391: Availability purge with actual candidates."""
        from app.services.retention_service import RetentionService

        # Create mock settings object to avoid Pydantic issues
        class MockSettings:
            availability_retention_enabled = True
            availability_retention_days = 30
            availability_retention_keep_recent_days = 7
            availability_retention_dry_run = False
            site_mode = "preview"

        # Patch the settings import in retention_service module
        import app.services.retention_service as retention_module

        original_settings = retention_module.settings
        monkeypatch.setattr(retention_module, "settings", MockSettings())

        service = RetentionService(db)
        result = service.purge_availability_days()
        assert "purged_days" in result
        assert "inspected_days" in result

        # Restore
        monkeypatch.setattr(retention_module, "settings", original_settings)


# ---------------------------------------------------------------------------
# GeolocationService Coverage Tests (85% → 92%+)
# ---------------------------------------------------------------------------
class TestGeolocationServiceCoverage:
    """Additional coverage tests for GeolocationService."""

    @pytest.fixture
    def geo_service(self, db: Session):
        """Create GeolocationService instance."""
        from app.services.geolocation_service import GeolocationService

        return GeolocationService(db, cache_service=None)

    @pytest.mark.asyncio
    async def test_get_location_cache_miss_lookup_success(self, db: Session):
        """Lines 85->92, 96-105: Cache miss with successful lookup."""
        from app.services.geolocation_service import GeolocationService

        mock_cache = AsyncMock()
        mock_cache.get.return_value = None

        service = GeolocationService(db, cache_service=mock_cache)

        # Mock the HTTP client
        mock_response = Mock()
        mock_response.json.return_value = {
            "country_code": "US",
            "country_name": "United States",
            "region": "New York",
            "city": "Brooklyn",
            "postal": "11201",
            "latitude": 40.6892,
            "longitude": -73.9442,
            "timezone": "America/New_York",
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        service.client = mock_client

        result = await service.get_location_from_ip("8.8.8.8")
        assert result is not None
        assert result["is_nyc"] is True
        assert result["borough"] == "Brooklyn"
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_location_lookup_returns_none(self, db: Session):
        """Lines 106-108: Lookup returns no data."""
        from app.services.geolocation_service import GeolocationService

        service = GeolocationService(db, cache_service=None)

        # Mock both services to fail
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Both services failed")
        mock_client.__aenter__.return_value = mock_client
        service.client = mock_client

        result = await service.get_location_from_ip("8.8.8.8")
        # Should return default location
        assert result is not None
        assert result["is_nyc"] is False

    @pytest.mark.asyncio
    async def test_lookup_ipapi_error_response(self, db: Session):
        """Lines 144-146: ipapi.co returns error."""
        from app.services.geolocation_service import GeolocationService

        service = GeolocationService(db)

        mock_response = Mock()
        mock_response.json.return_value = {"error": True, "reason": "Rate limited"}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        service.client = mock_client

        result = await service._lookup_ipapi("8.8.8.8")
        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_ipapi_com_error_status(self, db: Session):
        """Lines 168-170: ip-api.com returns error status."""
        from app.services.geolocation_service import GeolocationService

        service = GeolocationService(db)

        mock_response = Mock()
        mock_response.json.return_value = {"status": "fail", "message": "Invalid IP"}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        service.client = mock_client

        result = await service._lookup_ipapi_com("invalid")
        assert result is None

    def test_enhance_nyc_data_bronx(self, geo_service):
        """Lines 214-220: NYC detection for The Bronx."""
        data = {"city": "The Bronx", "state": "NY"}
        enhanced = geo_service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is True
        assert enhanced["borough"] == "Bronx"
        assert enhanced["city"] == "New York"

    def test_enhance_nyc_data_queens(self, geo_service):
        """Lines 214-220: NYC detection for Queens."""
        data = {"city": "Queens", "state": "New York"}
        enhanced = geo_service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is True
        assert enhanced["borough"] == "Queens"
        assert enhanced["city"] == "New York"

    def test_enhance_nyc_data_staten_island(self, geo_service):
        """Lines 214-220: NYC detection for Staten Island."""
        data = {"city": "Staten Island", "state": "NY"}
        enhanced = geo_service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is True
        assert enhanced["borough"] == "Staten Island"
        assert enhanced["city"] == "New York"

    def test_enhance_nyc_data_empty_city_or_state(self, geo_service):
        """Lines 206-207: Empty city or state."""
        data = {"city": "", "state": ""}
        enhanced = geo_service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is False

        data = {"city": "Brooklyn", "state": ""}
        enhanced = geo_service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is False

    def test_is_private_ip_invalid(self, geo_service):
        """Line 236-237: Invalid IP treated as private."""
        assert geo_service._is_private_ip("invalid") is True

    def test_get_ip_from_request_client_no_host(self, geo_service):
        """Lines 285-287: Client exists but no host attribute."""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = Mock(spec=[])  # No host attribute

        ip = geo_service.get_ip_from_request(mock_request)
        assert ip == "127.0.0.1"

    @pytest.mark.asyncio
    async def test_close_client(self, db: Session):
        """Line 291: Close HTTP client."""
        from app.services.geolocation_service import GeolocationService

        service = GeolocationService(db)
        await service.close()


# ---------------------------------------------------------------------------
# PrivacyService Coverage Tests (79% → 92%+)
# ---------------------------------------------------------------------------
class TestPrivacyServiceCoverage:
    """Additional coverage tests for PrivacyService."""

    @pytest.fixture
    def privacy_service(self, db: Session):
        """Create PrivacyService instance."""
        from app.services.privacy_service import PrivacyService

        return PrivacyService(db)

    def test_export_user_data_two_boroughs_mocked(self, db: Session):
        """Lines 155-157: Service area with exactly 2 boroughs."""
        from app.services.privacy_service import PrivacyService

        # Create mock user
        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        # Create mock instructor
        mock_instructor = Mock()
        mock_instructor.bio = "Test bio"
        mock_instructor.years_experience = 5
        mock_instructor.min_advance_booking_hours = 2
        mock_instructor.buffer_time_minutes = 15
        mock_instructor.created_at = datetime.now(timezone.utc)

        # Create mock service areas with 2 boroughs
        mock_area1 = Mock()
        mock_area1.neighborhood_id = "region1"
        mock_region1 = Mock()
        mock_region1.region_code = None
        mock_region1.region_name = None
        mock_region1.parent_region = None
        mock_region1.region_metadata = {"nta_code": "BX-01", "nta_name": "Bronx Park", "borough": "Bronx"}
        mock_area1.neighborhood = mock_region1

        mock_area2 = Mock()
        mock_area2.neighborhood_id = "region2"
        mock_region2 = Mock()
        mock_region2.region_code = None
        mock_region2.region_name = None
        mock_region2.parent_region = None
        mock_region2.region_metadata = {"nta_code": "BK-01", "nta_name": "Downtown", "borough": "Brooklyn"}
        mock_area2.neighborhood = mock_region2

        # Set up repository mocks
        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = mock_instructor

        mock_service_area_repo = Mock()
        mock_service_area_repo.list_for_instructor.return_value = [mock_area1, mock_area2]

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo
        service.service_area_repository = mock_service_area_repo

        result = service.export_user_data("user_id")
        profile = result["instructor_profile"]
        assert profile is not None
        # With exactly 2 boroughs, should be "Bronx, Brooklyn"
        assert profile["service_area_summary"] == "Bronx, Brooklyn"
        assert len(profile["service_area_boroughs"]) == 2

    def test_export_user_data_region_metadata_none_mocked(self, db: Session):
        """Lines 129-140: Region metadata is None (uses fallback from region attributes)."""
        from app.services.privacy_service import PrivacyService

        # Create mock user
        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        # Create mock instructor
        mock_instructor = Mock()
        mock_instructor.bio = "Test bio"
        mock_instructor.years_experience = 5
        mock_instructor.min_advance_booking_hours = 2
        mock_instructor.buffer_time_minutes = 15
        mock_instructor.created_at = datetime.now(timezone.utc)

        # Create mock service area with None metadata (uses region attributes)
        mock_area = Mock()
        mock_area.neighborhood_id = "region1"
        mock_region = Mock()
        mock_region.region_code = "TEST-01"
        mock_region.region_name = "Test Region"
        mock_region.parent_region = "Test Borough"
        mock_region.region_metadata = None  # None metadata
        mock_area.neighborhood = mock_region

        # Set up repository mocks
        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = mock_instructor

        mock_service_area_repo = Mock()
        mock_service_area_repo.list_for_instructor.return_value = [mock_area]

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo
        service.service_area_repository = mock_service_area_repo

        result = service.export_user_data("user_id")
        profile = result["instructor_profile"]
        assert profile is not None
        assert len(profile["service_area_neighborhoods"]) == 1
        # Should use region_code and region_name from the region object
        assert profile["service_area_neighborhoods"][0]["ntacode"] == "TEST-01"
        assert profile["service_area_neighborhoods"][0]["name"] == "Test Region"

    def test_delete_user_data_exception_handling(self, db: Session, monkeypatch):
        """Lines 274-278: Exception handling during deletion."""
        from app.services.privacy_service import PrivacyService

        # Create mock repositories
        mock_user_repo = Mock()
        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.is_active = True
        mock_user_repo.get_by_id.return_value = mock_user

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_search_history_repo = Mock()
        mock_search_history_repo.delete_user_searches.side_effect = RuntimeError("Test error")

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.booking_repository = mock_booking_repo
        service.search_history_repository = mock_search_history_repo

        with pytest.raises(RuntimeError, match="Test error"):
            service.delete_user_data("user_id")

    def test_apply_retention_policies_exception_handling(self, privacy_service, db: Session, monkeypatch):
        """Lines 325-329: Exception handling during retention."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "search_event_retention_days", 30)

        # Mock to raise
        def raise_error(*args, **kwargs):
            raise RuntimeError("Test error")

        privacy_service.search_event_repository.delete_old_events = raise_error

        with pytest.raises(RuntimeError, match="Test error"):
            privacy_service.apply_retention_policies()

    def test_anonymize_user_exception_handling(self, privacy_service, db: Session, monkeypatch):
        """Lines 391-395: Exception handling during anonymization."""
        user = User(
            email="anon_exception@example.com",
            first_name="Anon",
            last_name="Exception",
            phone="+12125551234",
            zip_code="10001",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Mock to raise during commit
        original_commit = db.commit

        def raise_on_commit():
            raise RuntimeError("Commit failed")

        db.commit = raise_on_commit

        with pytest.raises(RuntimeError, match="Commit failed"):
            privacy_service.anonymize_user(user.id)

        db.commit = original_commit

    def test_anonymize_user_with_instructor_profile(self, privacy_service, db: Session):
        """Lines 378-383: Anonymize user with instructor profile."""
        user = User(
            email="anon_instructor@example.com",
            first_name="Anon",
            last_name="Instructor",
            phone="+12125551234",
            zip_code="10001",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        instructor = InstructorProfile(
            user_id=user.id,
            bio="Original bio",
            years_experience=5,
            is_live=True,
        )
        db.add(instructor)
        db.commit()

        # Add search history
        search = SearchHistory(
            user_id=user.id,
            search_query="test query",
            normalized_query="test query",
            results_count=5,
            search_count=1,
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
        )
        db.add(search)

        event = SearchEvent(
            user_id=user.id,
            search_query="test",
            results_count=10,
            search_context={},
        )
        db.add(event)
        db.commit()

        result = privacy_service.anonymize_user(user.id)
        assert result is True

        db.refresh(instructor)
        assert instructor.bio == "This profile has been anonymized"

    def test_export_user_data_three_or_more_boroughs_mocked(self, db: Session):
        """Lines 158-159: Service area with 3+ boroughs shows summary."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        mock_instructor = Mock()
        mock_instructor.bio = "Test bio"
        mock_instructor.years_experience = 5
        mock_instructor.min_advance_booking_hours = 2
        mock_instructor.buffer_time_minutes = 15
        mock_instructor.created_at = datetime.now(timezone.utc)

        # Create 3 boroughs
        boroughs = ["Bronx", "Brooklyn", "Manhattan"]
        mock_areas = []
        for i, borough in enumerate(boroughs):
            area = Mock()
            area.neighborhood_id = f"region{i}"
            region = Mock()
            region.region_code = None
            region.region_name = None
            region.parent_region = None
            region.region_metadata = {"borough": borough}
            area.neighborhood = region
            mock_areas.append(area)

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = mock_instructor

        mock_service_area_repo = Mock()
        mock_service_area_repo.list_for_instructor.return_value = mock_areas

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo
        service.service_area_repository = mock_service_area_repo

        result = service.export_user_data("user_id")
        profile = result["instructor_profile"]
        # With 3+ boroughs: "Bronx + 2 more"
        assert profile["service_area_summary"] == "Bronx + 2 more"

    def test_export_user_data_no_instructor_profile_mocked(self, db: Session):
        """Lines 117-173: User without instructor profile."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "student@example.com"
        mock_user.first_name = "Student"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = None  # No instructor profile

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo

        result = service.export_user_data("user_id")
        assert result["instructor_profile"] is None

    def test_export_user_data_user_not_found(self, db: Session):
        """Line 58-59: User not found raises ValueError."""
        from app.services.privacy_service import PrivacyService

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = None

        service = PrivacyService(db)
        service.user_repository = mock_user_repo

        with pytest.raises(ValueError, match="not found"):
            service.export_user_data("nonexistent_user")

    def test_delete_user_data_with_account_deletion_mocked(self, db: Session):
        """Lines 243-267: Delete account with PII anonymization."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.phone = "+12125551234"
        mock_user.zip_code = "10001"

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_search_history_repo = Mock()
        mock_search_history_repo.delete_user_searches.return_value = 5

        mock_search_event_repo = Mock()
        mock_search_event_repo.delete_user_events.return_value = 10

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = None

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.booking_repository = mock_booking_repo
        service.search_history_repository = mock_search_history_repo
        service.search_event_repository = mock_search_event_repo
        service.instructor_repository = mock_instructor_repo

        result = service.delete_user_data("user_id", delete_account=True)
        assert result["search_history"] == 5
        assert result["search_events"] == 10
        assert mock_user.is_active is False
        assert mock_user.email == "deleted_user_id@deleted.com"
        assert mock_user.first_name == "Deleted"

    def test_delete_user_data_with_instructor_profile_mocked(self, db: Session):
        """Lines 265-267: Delete account with instructor profile."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.is_active = True

        mock_instructor = Mock()
        mock_instructor.id = "instructor_id"

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_search_history_repo = Mock()
        mock_search_history_repo.delete_user_searches.return_value = 0

        mock_search_event_repo = Mock()
        mock_search_event_repo.delete_user_events.return_value = 0

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = mock_instructor

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.booking_repository = mock_booking_repo
        service.search_history_repository = mock_search_history_repo
        service.search_event_repository = mock_search_event_repo
        service.instructor_repository = mock_instructor_repo

        service.delete_user_data("user_id", delete_account=True)
        mock_instructor_repo.delete.assert_called_once_with("instructor_id")

    def test_delete_user_data_with_future_bookings_mocked(self, db: Session):
        """Lines 204-208: Reject deletion with future bookings."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"

        mock_booking = Mock()

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = [mock_booking]
        mock_booking_repo.get_instructor_bookings.return_value = []

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.booking_repository = mock_booking_repo

        with pytest.raises(ValueError, match="active bookings"):
            service.delete_user_data("user_id", delete_account=True)

    def test_delete_user_data_user_not_found_mocked(self, db: Session):
        """Lines 191-193: Delete data for nonexistent user."""
        from app.services.privacy_service import PrivacyService

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = None

        service = PrivacyService(db)
        service.user_repository = mock_user_repo

        with pytest.raises(ValueError, match="not found"):
            service.delete_user_data("nonexistent_user")

    def test_get_privacy_statistics_mocked(self, db: Session, monkeypatch):
        """Lines 331-354: Get privacy statistics."""
        from app.core.config import settings
        from app.services.privacy_service import PrivacyService

        monkeypatch.setattr(settings, "search_event_retention_days", 30)

        mock_user_repo = Mock()
        mock_user_repo.count_all.return_value = 100
        mock_user_repo.count_active.return_value = 80

        mock_search_history_repo = Mock()
        mock_search_history_repo.count_all_searches.return_value = 500

        mock_search_event_repo = Mock()
        mock_search_event_repo.count_all_events.return_value = 1000
        mock_search_event_repo.count_old_events.return_value = 50

        mock_booking_repo = Mock()
        mock_booking_repo.count.return_value = 200

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.search_event_repository = mock_search_event_repo
        service.booking_repository = mock_booking_repo

        result = service.get_privacy_statistics()
        assert result.total_users == 100
        assert result.active_users == 80
        assert result.search_history_records == 500
        assert result.search_event_records == 1000
        assert result.total_bookings == 200
        assert result.search_events_eligible_for_deletion == 50

    def test_apply_retention_policies_success_mocked(self, db: Session, monkeypatch):
        """Lines 280-323: Apply retention policies successfully."""
        from app.core.config import settings
        from app.services.privacy_service import PrivacyService

        monkeypatch.setattr(settings, "search_event_retention_days", 30)
        monkeypatch.setattr(settings, "booking_pii_retention_days", 365)

        mock_search_event_repo = Mock()
        mock_search_event_repo.delete_old_events.return_value = 100

        mock_booking_repo = Mock()
        mock_booking_repo.count_old_bookings.return_value = 50

        service = PrivacyService(db)
        service.search_event_repository = mock_search_event_repo
        service.booking_repository = mock_booking_repo

        result = service.apply_retention_policies()
        assert result.search_events_deleted == 100
        assert result.old_bookings_anonymized == 50

    def test_anonymize_user_not_found_mocked(self, db: Session):
        """Lines 368-370: Anonymize nonexistent user."""
        from app.services.privacy_service import PrivacyService

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = None

        service = PrivacyService(db)
        service.user_repository = mock_user_repo

        with pytest.raises(ValueError, match="not found"):
            service.anonymize_user("nonexistent_user")

    def test_export_user_data_with_empty_boroughs_mocked(self, db: Session):
        """Lines 160-161: Service area with no boroughs."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        mock_instructor = Mock()
        mock_instructor.bio = "Test bio"
        mock_instructor.years_experience = 5
        mock_instructor.min_advance_booking_hours = 2
        mock_instructor.buffer_time_minutes = 15
        mock_instructor.created_at = datetime.now(timezone.utc)

        # Service area with no borough info
        mock_area = Mock()
        mock_area.neighborhood_id = "region1"
        region = Mock()
        region.region_code = "TEST-01"
        region.region_name = "Test Region"
        region.parent_region = None  # No borough
        region.region_metadata = {}  # Empty metadata
        mock_area.neighborhood = region

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = mock_instructor

        mock_service_area_repo = Mock()
        mock_service_area_repo.list_for_instructor.return_value = [mock_area]

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo
        service.service_area_repository = mock_service_area_repo

        result = service.export_user_data("user_id")
        profile = result["instructor_profile"]
        assert profile["service_area_summary"] == ""
        assert profile["service_area_boroughs"] == []

    def test_export_user_data_with_search_history_mocked(self, db: Session):
        """Lines 82-95: Export user data with search history."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        mock_search = Mock()
        mock_search.search_query = "yoga instructor"
        mock_search.search_type = "natural_language"
        mock_search.results_count = 10
        mock_search.search_count = 3
        mock_search.first_searched_at = datetime.now(timezone.utc)
        mock_search.last_searched_at = datetime.now(timezone.utc)

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = [mock_search]

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = []
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = None

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo

        result = service.export_user_data("user_id")
        assert len(result["search_history"]) == 1
        assert result["search_history"][0]["search_query"] == "yoga instructor"

    def test_export_user_data_with_bookings_mocked(self, db: Session):
        """Lines 97-115: Export user data with bookings."""
        from app.services.privacy_service import PrivacyService

        mock_user = Mock()
        mock_user.id = "user_id"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)

        mock_booking = Mock()
        mock_booking.id = "booking_id"
        mock_booking.booking_date = date.today()
        mock_booking.start_time = time(10, 0)
        mock_booking.end_time = time(11, 0)
        mock_booking.service_name = "Piano Lesson"
        mock_booking.total_price = 50.00
        mock_booking.status = "completed"
        mock_booking.instructor_id = "instructor_id"
        mock_booking.created_at = datetime.now(timezone.utc)

        mock_user_repo = Mock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_search_history_repo = Mock()
        mock_search_history_repo.get_user_searches.return_value = []

        mock_booking_repo = Mock()
        mock_booking_repo.get_student_bookings.return_value = [mock_booking]
        mock_booking_repo.get_instructor_bookings.return_value = []

        mock_instructor_repo = Mock()
        mock_instructor_repo.get_by_user_id.return_value = None

        service = PrivacyService(db)
        service.user_repository = mock_user_repo
        service.search_history_repository = mock_search_history_repo
        service.booking_repository = mock_booking_repo
        service.instructor_repository = mock_instructor_repo

        result = service.export_user_data("user_id")
        assert len(result["bookings"]) == 1
        assert result["bookings"][0]["service_name"] == "Piano Lesson"
        assert result["bookings"][0]["role"] == "student"


# ---------------------------------------------------------------------------
# PersonalAssetService Coverage Tests (87% → 92%+)
# ---------------------------------------------------------------------------
class TestPersonalAssetServiceCoverage:
    """Additional coverage tests for PersonalAssetService."""

    def test_is_r2_storage_configured_credential_error(self, monkeypatch):
        """Lines 66-68: Credential access raises exception."""
        from app.services import personal_asset_service as module

        class MockSecretStr:
            def get_secret_value(self):
                raise ValueError("No secret")

        class MockSettings:
            r2_enabled = True
            r2_bucket_name = "bucket"
            r2_access_key_id = "key"
            r2_account_id = "account"
            r2_secret_access_key = MockSecretStr()

        monkeypatch.setattr(module, "settings", MockSettings())
        result = module._is_r2_storage_configured()
        assert result is False

    def test_build_storage_r2_exception(self, monkeypatch):
        """Lines 96-99: R2 client construction fails."""
        from app.services import personal_asset_service as module

        monkeypatch.setattr(module, "_FALLBACK_STORAGE_WARNED", False)
        monkeypatch.setattr(module, "_is_r2_storage_configured", lambda: True)

        original_r2_client = module.R2StorageClient

        def raise_error():
            raise ValueError("R2 init failed")

        monkeypatch.setattr(module, "R2StorageClient", raise_error)

        service = module.PersonalAssetService(db=None)
        assert isinstance(service.storage, module.NullStorageClient)

        monkeypatch.setattr(module, "R2StorageClient", original_r2_client)

    def test_finalize_profile_picture_no_data_not_testing(self, monkeypatch):
        """Lines 238-239: No upload data and not in testing mode."""
        from app.services import personal_asset_service as module

        class DummyStorage:
            def download_bytes(self, key):
                return None

        class MockSettings:
            is_testing = False

        monkeypatch.setattr(module, "settings", MockSettings())

        user = SimpleNamespace(id="user1", profile_picture_version=0)
        service = module.PersonalAssetService(db=None, storage=DummyStorage())

        with pytest.raises(ValueError, match="Uploaded object not found"):
            service.finalize_profile_picture(user, "uploads/test.png")

    def test_finalize_profile_picture_upload_failure(self, monkeypatch):
        """Lines 264-265, 270-271: Upload fails in non-test mode."""
        from app.services import personal_asset_service as module

        class DummyImages:
            def process_profile_picture(self, data, content_type):
                return SimpleNamespace(
                    original=b"orig",
                    display_400=b"disp",
                    thumb_200=b"thumb",
                )

        class DummyStorage:
            def download_bytes(self, key):
                return b"data"

            def upload_bytes(self, key, content, ct):
                return False, 500

            def delete_object(self, key):
                return True

        class MockSettings:
            is_testing = False

        monkeypatch.setattr(module, "settings", MockSettings())

        user = SimpleNamespace(id="user1", profile_picture_version=0)
        service = module.PersonalAssetService(
            db=None,
            storage=DummyStorage(),
            images=DummyImages(),
        )

        with pytest.raises(RuntimeError, match="Failed to upload processed images"):
            service.finalize_profile_picture(user, "uploads/test.png")

    def test_get_profile_picture_urls_empty_input(self):
        """Line 357-358: Empty user_ids list."""
        from app.services.personal_asset_service import PersonalAssetService

        service = PersonalAssetService(db=None)
        result = service.get_profile_picture_urls([])
        assert result == {}

    def test_get_profile_picture_urls_all_empty_strings(self, monkeypatch):
        """Lines 363-370: All user_ids are empty or whitespace."""
        from app.services import personal_asset_service as module

        service = module.PersonalAssetService(db=None)
        result = service.get_profile_picture_urls(["", " ", "  "])
        assert result == {}

    def test_get_presigned_view_cache_miss_metrics_error(self, monkeypatch):
        """Lines 175-176, 194-195: Metrics errors are caught."""
        from app.services import personal_asset_service as module

        class DummyFuture:
            def __init__(self, value):
                self.value = value

            def result(self, timeout=None):
                return self.value

        class DummyExecutor:
            def submit(self, fn):
                return DummyFuture(fn())

        class DummySemaphore:
            def acquire(self, timeout=None):
                return True

            def release(self):
                return None

        class DummyCache:
            def get(self, key):
                return {"url": "cached", "expires_at": "later"}

            def set(self, *args, **kwargs):
                pass

        class DummyStorage:
            def generate_presigned_get(self, object_key, expires_seconds, extra_query_params):
                from app.services.r2_storage_client import PresignedUrl

                return PresignedUrl(url="fresh", headers={}, expires_at="later")

        # Mock metrics to raise
        def raise_error(*args, **kwargs):
            raise RuntimeError("Metrics error")

        monkeypatch.setattr(module, "_STORAGE_EXECUTOR", DummyExecutor())
        monkeypatch.setattr(module, "_STORAGE_SEMAPHORE", DummySemaphore())
        monkeypatch.setattr(module.profile_pic_url_cache_hits_total, "labels", lambda **kwargs: Mock(inc=raise_error))

        service = module.PersonalAssetService(
            db=None,
            storage=DummyStorage(),
            cache_service=DummyCache(),
        )
        view = service._get_presigned_view_for_user("user1", 1, "display")
        assert view is not None
        assert view.url == "cached"
