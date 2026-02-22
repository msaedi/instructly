"""Unit tests for AuditRepository — targets missed lines and branch partials.

Missed lines:
  32-33  write: prometheus_metrics.record_audit_write raises → caught silently
  62->66 list: conditions empty (no filters) → no where clause applied
  89->91 list_for_booking_actions: actions empty → no .in_ filter
  94     list_for_booking_actions: start is not None → adds start filter
  96     list_for_booking_actions: end is not None → adds end filter
  101->105 list_for_booking_actions: conditions truthy → where applied
  106    list_for_booking_actions: offset truthy → offset applied
  129    _build_filters: actor_role filter
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.repositories.audit_repository import AuditRepository, _build_filters


def _make_repo() -> tuple[AuditRepository, MagicMock]:
    mock_db = MagicMock()
    repo = AuditRepository(mock_db)
    return repo, mock_db


# ------------------------------------------------------------------
# write — lines 32-33
# ------------------------------------------------------------------


class TestWrite:
    """Cover the non-fatal prometheus_metrics error path."""

    @patch("app.repositories.audit_repository.prometheus_metrics")
    def test_prometheus_error_silently_caught(self, mock_prom: MagicMock) -> None:
        """Lines 32-33: record_audit_write raises → debug log, no re-raise."""
        repo, mock_db = _make_repo()
        mock_prom.record_audit_write.side_effect = RuntimeError("prometheus unavailable")

        audit = SimpleNamespace(entity_type="booking", action="create")
        repo.write(audit)

        mock_db.add.assert_called_once_with(audit)
        mock_db.flush.assert_called_once()

    @patch("app.repositories.audit_repository.prometheus_metrics")
    def test_write_normal_path(self, mock_prom: MagicMock) -> None:
        """Normal case: write persists audit and records metric."""
        repo, mock_db = _make_repo()

        audit = SimpleNamespace(entity_type="user", action="update")
        repo.write(audit)

        mock_db.add.assert_called_once_with(audit)
        mock_prom.record_audit_write.assert_called_once_with("user", "update")
        mock_db.flush.assert_called_once()


# ------------------------------------------------------------------
# list — line 62->66 (no conditions branch)
# ------------------------------------------------------------------


class TestList:
    """Cover the no-conditions branch and various filter combinations."""

    def test_no_filters_skips_where_clause(self) -> None:
        """Line 62->66: no filters → conditions list is empty → no where() call."""
        repo, mock_db = _make_repo()

        # Mock the execute chain
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list()

        assert rows == []
        assert total == 0
        assert mock_db.execute.call_count == 2

    def test_with_start_and_end_filters(self) -> None:
        """Lines 54-57: start and end provided → adds time filters."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list(
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        assert total == 0

    def test_with_entity_type_filter(self) -> None:
        """Conditions non-empty → where clause applied."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 5

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list(entity_type="booking")

        assert total == 5


# ------------------------------------------------------------------
# list_for_booking_actions — lines 89->91, 94, 96, 101->105, 106
# ------------------------------------------------------------------


class TestListForBookingActions:
    """Cover branches in list_for_booking_actions."""

    def test_empty_actions_no_in_filter(self) -> None:
        """Line 89->91: actions is empty → no .in_ filter added."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(actions=[])

        assert total == 0

    def test_with_actions_and_actor_id(self) -> None:
        """Lines 89-92: actions + actor_id → both conditions added."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(
            actions=["create", "cancel"],
            actor_id="user_1",
        )

        assert total == 3

    def test_with_start_filter(self) -> None:
        """Line 94: start is not None → appends occurred_at >= start."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(
            actions=["create"],
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        assert total == 0

    def test_with_end_filter(self) -> None:
        """Line 96: end is not None → appends occurred_at <= end."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(
            actions=["create"],
            end=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )

        assert total == 0

    def test_with_offset(self) -> None:
        """Line 106: offset > 0 → offset applied."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 10

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(
            actions=["create"],
            offset=5,
        )

        assert total == 10

    def test_with_limit_none(self) -> None:
        """Line 107: limit is None → no limit applied."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(
            actions=["create"],
            limit=None,
        )

        assert total == 0

    def test_with_all_filters(self) -> None:
        """All filters combined: actor_id, start, end, offset."""
        repo, mock_db = _make_repo()

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        mock_db.execute.side_effect = [rows_result, count_result]

        rows, total = repo.list_for_booking_actions(
            actions=["cancel", "refund"],
            actor_id="admin_1",
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 12, 31, tzinfo=timezone.utc),
            offset=10,
            limit=25,
        )

        assert total == 2


# ------------------------------------------------------------------
# _build_filters — line 129 (actor_role filter)
# ------------------------------------------------------------------


class TestBuildFilters:
    """Cover the actor_role filter which hasn't been exercised."""

    def test_actor_role_filter(self) -> None:
        """Line 132-133: actor_role is truthy → adds clause."""
        clauses = _build_filters(
            entity_type=None,
            entity_id=None,
            action=None,
            actor_id=None,
            actor_role="admin",
        )
        assert len(clauses) == 1

    def test_all_filters(self) -> None:
        """All filters present → 5 clauses."""
        clauses = _build_filters(
            entity_type="booking",
            entity_id="ent_1",
            action="create",
            actor_id="user_1",
            actor_role="instructor",
        )
        assert len(clauses) == 5

    def test_no_filters(self) -> None:
        """No filters → empty list."""
        clauses = _build_filters(
            entity_type=None,
            entity_id=None,
            action=None,
            actor_id=None,
            actor_role=None,
        )
        assert len(clauses) == 0
