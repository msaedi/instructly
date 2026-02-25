"""Unit coverage for WebhookEventRepository – uncovered L48-50,74,93,116,178-182,216,219."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.repositories.webhook_event_repository import WebhookEventRepository


def _make_repo() -> tuple[WebhookEventRepository, MagicMock]:
    mock_db = MagicMock()
    repo = WebhookEventRepository(mock_db)
    return repo, mock_db


class TestListEventsWithTimeRange:
    """L48-50: start_time / end_time filters in list_events."""

    def test_list_events_with_start_time_only(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        start = datetime.now(timezone.utc)
        result = repo.list_events(start_time=start)
        assert result == []

    def test_list_events_with_end_time_only(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        end = datetime.now(timezone.utc)
        result = repo.list_events(end_time=end)
        assert result == []

    def test_list_events_with_both_time_boundaries(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        now = datetime.now(timezone.utc)
        result = repo.list_events(start_time=now - timedelta(hours=1), end_time=now)
        assert result == []


class TestCountEventsEdgeCases:
    """L74: elif branch in count_events (end_time is None, start_time is None)."""

    def test_count_events_default_since_cutoff(self) -> None:
        """L74: neither start_time nor end_time triggers since_hours cutoff."""
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        repo._execute_scalar = MagicMock(return_value=5)

        result = repo.count_events(since_hours=12)
        assert result == 5

    def test_count_events_start_time_skips_cutoff(self) -> None:
        """When start_time given, cutoff is NOT applied."""
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        repo._execute_scalar = MagicMock(return_value=3)

        result = repo.count_events(start_time=datetime.now(timezone.utc))
        assert result == 3

    def test_count_events_with_end_time_only(self) -> None:
        """When only end_time given but not start_time, cutoff is used."""
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        repo._execute_scalar = MagicMock(return_value=7)

        result = repo.count_events(end_time=datetime.now(timezone.utc))
        assert result == 7

    def test_count_events_returns_zero_for_none_scalar(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        repo._execute_scalar = MagicMock(return_value=None)

        assert repo.count_events() == 0


class TestSummarizeByStatusEdgeCases:
    """L93: elif in summarize_by_status."""

    def test_summarize_by_status_with_start_time(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = [("processed", 10)]

        result = repo.summarize_by_status(start_time=datetime.now(timezone.utc))
        assert result == {"processed": 10}

    def test_summarize_by_status_without_start_uses_cutoff(self) -> None:
        """L93: no start_time and no end_time means cutoff is used."""
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = [("failed", 2), (None, 1)]

        result = repo.summarize_by_status(since_hours=1)
        assert result["failed"] == 2
        assert result["unknown"] == 1


class TestSummarizeBySourceEdgeCases:
    """L116: elif in summarize_by_source."""

    def test_summarize_by_source_with_start_time(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = [("stripe", 5)]

        result = repo.summarize_by_source(start_time=datetime.now(timezone.utc))
        assert result == {"stripe": 5}

    def test_summarize_by_source_null_source(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = [(None, 3)]

        result = repo.summarize_by_source()
        assert result == {"unknown": 3}


class TestClaimForProcessing:
    """L178-182: SQLAlchemy error in claim_for_processing."""

    def test_claim_for_processing_success(self) -> None:
        repo, mock_db = _make_repo()
        row = MagicMock()
        mock_db.execute.return_value.first.return_value = row

        assert repo.claim_for_processing("evt-01") is True

    def test_claim_for_processing_no_match(self) -> None:
        repo, mock_db = _make_repo()
        mock_db.execute.return_value.first.return_value = None

        assert repo.claim_for_processing("evt-01") is False

    def test_claim_for_processing_raises_repo_exception(self) -> None:
        from sqlalchemy.exc import SQLAlchemyError

        from app.core.exceptions import RepositoryException

        repo, mock_db = _make_repo()
        mock_db.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(RepositoryException, match="claim"):
            repo.claim_for_processing("evt-01")


class TestGetFailedEventsTimeBranches:
    """L216,219: list_events_for_related_entity limit branch."""

    def test_list_events_for_related_entity_with_limit(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        result = repo.list_events_for_related_entity(
            related_entity_id="ent-01", limit=10
        )
        assert result == []

    def test_list_events_for_related_entity_no_limit(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        result = repo.list_events_for_related_entity(
            related_entity_id="ent-01", limit=None
        )
        assert result == []

    def test_list_events_for_related_entity_with_type(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        result = repo.list_events_for_related_entity(
            related_entity_id="ent-01",
            related_entity_type="booking",
        )
        assert result == []


class TestGetFailedEventsTimeFilters:
    """Cover time-range filters on get_failed_events."""

    def test_get_failed_events_with_start_time(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        result = repo.get_failed_events(start_time=datetime.now(timezone.utc))
        assert result == []

    def test_get_failed_events_with_end_time(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        repo._execute_query = MagicMock(return_value=[])

        result = repo.get_failed_events(end_time=datetime.now(timezone.utc))
        assert result == []
