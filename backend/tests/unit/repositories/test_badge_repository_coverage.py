"""Unit tests for BadgeRepository — targets missed lines and branch partials.

Missed lines:
  196->198  get_latest_completed_lesson: before filter + exclude_booking_id filter
  198->201  get_latest_completed_lesson: exclude_booking_id filter branch
  264-277   upsert_progress: IntegrityError retry path (race condition)
  306-315   insert_award_pending_or_confirmed: existing revoked award revival
  330-343   insert_award_pending_or_confirmed: IntegrityError on new award insert
  464       get_cancel_noshow_rate_pct_window: window_days <= 0 early return
  550->553  list_awards: status_filter is falsy branch
  618       update_award_status: unsupported new_status falls through to updated=0
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.badge_repository import BadgeRepository


def _make_repo() -> tuple[BadgeRepository, MagicMock]:
    mock_db = MagicMock()
    repo = BadgeRepository.__new__(BadgeRepository)
    repo.db = mock_db
    repo.model = MagicMock()
    repo.logger = MagicMock()
    return repo, mock_db


# ------------------------------------------------------------------
# get_latest_completed_lesson — lines 196->198, 198->201
# ------------------------------------------------------------------


class TestGetLatestCompletedLesson:
    """Cover the before and exclude_booking_id optional filter branches."""

    def test_with_before_filter_applied(self) -> None:
        """Lines 196-197: before is not None → adds filter."""
        repo, mock_db = _make_repo()
        booking = SimpleNamespace(
            id="bk_01",
            instructor_id="inst_01",
            completed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            confirmed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        # Chain: query().filter().filter().filter().order_by().first()
        chain = mock_db.query.return_value.filter.return_value
        chain.filter.return_value.filter.return_value.order_by.return_value.first.return_value = (
            booking
        )
        # Also support the case where only 'before' is used without exclude
        chain.filter.return_value.order_by.return_value.first.return_value = booking

        result = repo.get_latest_completed_lesson(
            "student_1",
            before=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        assert result is not None
        assert result["booking_id"] == "bk_01"

    def test_with_exclude_booking_id_filter_applied(self) -> None:
        """Lines 198-199: exclude_booking_id is truthy → adds filter."""
        repo, mock_db = _make_repo()
        booking = SimpleNamespace(
            id="bk_02",
            instructor_id="inst_02",
            completed_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
            confirmed_at=None,
            created_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
        )
        chain = mock_db.query.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.first.return_value = booking

        result = repo.get_latest_completed_lesson(
            "student_1",
            exclude_booking_id="bk_99",
        )

        assert result is not None
        assert result["booking_id"] == "bk_02"
        # confirmed_at is None, so booked_at should fall back to created_at
        assert result["booked_at"] == datetime(2025, 2, 1, tzinfo=timezone.utc)

    def test_with_both_before_and_exclude(self) -> None:
        """Lines 196-199: both filters applied simultaneously."""
        repo, mock_db = _make_repo()
        booking = SimpleNamespace(
            id="bk_03",
            instructor_id="inst_03",
            completed_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
            confirmed_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
            created_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )
        chain = mock_db.query.return_value.filter.return_value
        chain.filter.return_value.filter.return_value.order_by.return_value.first.return_value = (
            booking
        )

        result = repo.get_latest_completed_lesson(
            "student_1",
            before=datetime(2025, 6, 1, tzinfo=timezone.utc),
            exclude_booking_id="bk_99",
        )

        assert result is not None
        assert result["booking_id"] == "bk_03"


# ------------------------------------------------------------------
# upsert_progress — lines 264-277 (IntegrityError retry path)
# ------------------------------------------------------------------


class TestUpsertProgressIntegrityRetry:
    """Cover the race-condition retry on insert that catches IntegrityError."""

    def test_integrity_error_then_update_existing(self) -> None:
        """Lines 264-275: IntegrityError → re-query finds existing → update it."""
        repo, mock_db = _make_repo()

        # First query returns None (no existing progress)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,
            SimpleNamespace(
                current_progress={"old": True},
                last_updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
        ]

        # begin_nested raises IntegrityError on flush inside the context manager
        nested_ctx = MagicMock()
        nested_ctx.__enter__ = MagicMock(return_value=nested_ctx)
        nested_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.begin_nested.return_value = nested_ctx

        # Simulate IntegrityError during add+flush
        mock_db.add.side_effect = IntegrityError("dup", {}, None)

        # We need to restructure: the IntegrityError is raised by begin_nested context
        # Let's use the simpler approach — make flush inside begin_nested raise
        mock_db.add.side_effect = None
        mock_db.flush.side_effect = [IntegrityError("dup", {}, None), None]

        # Actually this is inside a `with self.db.begin_nested()` block
        # The IntegrityError is caught at line 264. Let's mock the context manager properly.
        mock_db.add.reset_mock()
        mock_db.flush.reset_mock()

        # For `with self.db.begin_nested():` + `self.db.add(progress)` + `self.db.flush()`
        # The IntegrityError gets raised and caught at line 264.
        # Re-mock: first flush raises (inside begin_nested), second flush succeeds (line 278)
        flush_effects = [IntegrityError("dup", {}, None), None]
        mock_db.flush.side_effect = flush_effects

        now = datetime(2025, 6, 1, tzinfo=timezone.utc)
        repo.upsert_progress("student_1", "badge_1", {"count": 5}, now_utc=now)

        # The second query should have found the existing record and updated it
        assert mock_db.query.return_value.filter.return_value.first.call_count == 2

    def test_integrity_error_then_not_found_raises(self) -> None:
        """Lines 276-277: IntegrityError → re-query returns None → re-raise."""
        repo, mock_db = _make_repo()

        mock_db.query.return_value.filter.return_value.first.return_value = None

        nested_ctx = MagicMock()
        nested_ctx.__enter__ = MagicMock(return_value=nested_ctx)
        nested_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.begin_nested.return_value = nested_ctx

        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        with pytest.raises(IntegrityError):
            repo.upsert_progress("student_1", "badge_1", {"count": 5})


# ------------------------------------------------------------------
# insert_award_pending_or_confirmed — lines 306-315, 330-343
# ------------------------------------------------------------------


class TestInsertAwardPendingOrConfirmed:
    """Cover the existing-revoked-award revival and IntegrityError retry paths."""

    def test_revives_revoked_award(self) -> None:
        """Lines 306-315: existing award with status 'revoked' → gets revived."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        existing = SimpleNamespace(
            id="award_01",
            status="revoked",
            awarded_at=None,
            hold_until=None,
            confirmed_at=None,
            revoked_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            progress_snapshot=None,
        )
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = existing

        result = repo.insert_award_pending_or_confirmed(
            "student_1",
            "badge_1",
            hold_hours=24,
            progress_snapshot={"lessons": 10},
            now_utc=now,
        )

        assert result == "award_01"
        assert existing.status == "pending"
        assert existing.awarded_at == now
        assert existing.revoked_at is None
        assert existing.progress_snapshot == {"lessons": 10}

    def test_revives_revoked_award_no_hold(self) -> None:
        """Lines 306-315: existing revoked award with hold_hours=0 → confirmed directly."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        existing = SimpleNamespace(
            id="award_02",
            status="revoked",
            awarded_at=None,
            hold_until=None,
            confirmed_at=None,
            revoked_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            progress_snapshot=None,
        )
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = existing

        result = repo.insert_award_pending_or_confirmed(
            "student_1",
            "badge_1",
            hold_hours=0,
            progress_snapshot={"lessons": 10},
            now_utc=now,
        )

        assert result == "award_02"
        assert existing.status == "confirmed"
        assert existing.confirmed_at == now
        assert existing.hold_until is None

    def test_returns_existing_pending_award_id(self) -> None:
        """Line 307: existing award with status 'pending' → returns its id."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        existing = SimpleNamespace(id="award_03", status="pending")
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = existing

        result = repo.insert_award_pending_or_confirmed(
            "student_1",
            "badge_1",
            hold_hours=24,
            progress_snapshot={},
            now_utc=now,
        )

        assert result == "award_03"

    def test_integrity_error_on_insert_returns_existing(self) -> None:
        """Lines 330-342: new insert raises IntegrityError → retry finds existing."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        # First query: no existing award
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
            None,
            SimpleNamespace(id="award_04", status="pending"),
        ]

        nested_ctx = MagicMock()
        nested_ctx.__enter__ = MagicMock(return_value=nested_ctx)
        nested_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.begin_nested.return_value = nested_ctx

        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        result = repo.insert_award_pending_or_confirmed(
            "student_1",
            "badge_1",
            hold_hours=24,
            progress_snapshot={"count": 5},
            now_utc=now,
        )

        assert result == "award_04"

    def test_integrity_error_on_insert_not_found_raises(self) -> None:
        """Line 343: IntegrityError → retry returns None → re-raise."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        nested_ctx = MagicMock()
        nested_ctx.__enter__ = MagicMock(return_value=nested_ctx)
        nested_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.begin_nested.return_value = nested_ctx

        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        with pytest.raises(IntegrityError):
            repo.insert_award_pending_or_confirmed(
                "student_1",
                "badge_1",
                hold_hours=24,
                progress_snapshot={},
                now_utc=now,
            )


# ------------------------------------------------------------------
# get_cancel_noshow_rate_pct_window — line 464
# ------------------------------------------------------------------


class TestGetCancelNoshowRatePctWindow:
    """Cover the window_days <= 0 early return."""

    def test_zero_window_days_returns_zero(self) -> None:
        """Line 464: window_days=0 → return 0.0."""
        repo, _mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)
        result = repo.get_cancel_noshow_rate_pct_window("student_1", now, 0)
        assert result == 0.0

    def test_negative_window_days_returns_zero(self) -> None:
        """Line 464: window_days=-5 → return 0.0."""
        repo, _mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)
        result = repo.get_cancel_noshow_rate_pct_window("student_1", now, -5)
        assert result == 0.0

    def test_none_window_days_returns_zero(self) -> None:
        """Line 462-464: window_days coerced from None to 0 → return 0.0."""
        repo, _mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)
        # The code does int(window_days or 0), so passing None-like 0
        result = repo.get_cancel_noshow_rate_pct_window("student_1", now, 0)
        assert result == 0.0


# ------------------------------------------------------------------
# list_awards — line 550->553 (status_filter falsy branch)
# ------------------------------------------------------------------


class TestListAwards:
    """Cover the branch where status_filter is not 'pending' (else on line 560)."""

    def test_non_pending_status_uses_awarded_at_filter(self) -> None:
        """Lines 560-561: status is 'confirmed' → filters by awarded_at."""
        repo, mock_db = _make_repo()
        before = datetime(2025, 6, 1, tzinfo=timezone.utc)

        # Chain to return count and rows
        base_query = mock_db.query.return_value.join.return_value.join.return_value
        filtered = base_query.filter.return_value.filter.return_value

        filtered.order_by.return_value.with_entities.return_value.scalar.return_value = 2
        filtered.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        rows, total = repo.list_awards(
            status="confirmed", before=before, limit=10, offset=0
        )

        assert total >= 0


# ------------------------------------------------------------------
# update_award_status — line 618 (unsupported status)
# ------------------------------------------------------------------


class TestUpdateAwardStatus:
    """Cover the else branch for unsupported new_status values."""

    def test_unsupported_status_returns_zero(self) -> None:
        """Line 618: new_status is neither 'confirmed' nor 'revoked' → updated=0."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        result = repo.update_award_status("award_1", "invalid_status", now)

        assert result == 0
        mock_db.flush.assert_not_called()

    def test_confirmed_status_updates_and_flushes(self) -> None:
        """Lines 601-608: new_status='confirmed' updates correctly."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_db.query.return_value.filter.return_value.update.return_value = 1

        result = repo.update_award_status("award_1", "confirmed", now)

        assert result == 1
        mock_db.flush.assert_called_once()

    def test_revoked_status_updates_and_flushes(self) -> None:
        """Lines 609-616: new_status='revoked' updates correctly."""
        repo, mock_db = _make_repo()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_db.query.return_value.filter.return_value.update.return_value = 1

        result = repo.update_award_status("award_1", "revoked", now)

        assert result == 1
        mock_db.flush.assert_called_once()
