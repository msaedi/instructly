# backend/tests/unit/services/test_search_history_cleanup_service.py
"""
Unit tests for search_history_cleanup_service.py.

Targets missed lines:
- 71-73: Error handling in cleanup_soft_deleted_searches
- 89-90: Disabled cleanup with 0 days for guest sessions
- 121-123: Error handling in cleanup_old_guest_sessions
- 169, 178, 184: Statistics gathering with settings checks

Bug Analysis:
- No critical bugs found
- Error handling re-raises exceptions appropriately after logging
- Statistics collection is conditional on settings (intentional)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.search_history_cleanup_service import SearchHistoryCleanupService


class MockSearchHistoryRepository:
    """Mock repository for testing cleanup service."""

    def __init__(self):
        self.hard_delete_old_soft_deleted_calls = []
        self.delete_converted_guest_searches_calls = []
        self.delete_old_unconverted_guest_searches_calls = []
        self.should_raise = False
        self.raise_on_method: str | None = None

    def hard_delete_old_soft_deleted(self, days_old: int) -> int:
        self.hard_delete_old_soft_deleted_calls.append(days_old)
        if self.should_raise and self.raise_on_method == "hard_delete":
            raise RuntimeError("Database error during hard delete")
        return 5

    def delete_converted_guest_searches(self, days_old: int) -> int:
        self.delete_converted_guest_searches_calls.append(days_old)
        if self.should_raise and self.raise_on_method == "delete_converted":
            raise RuntimeError("Database error during delete converted")
        return 3

    def delete_old_unconverted_guest_searches(self, days_old: int) -> int:
        self.delete_old_unconverted_guest_searches_calls.append(days_old)
        return 2

    def count_soft_deleted_total(self) -> int:
        return 10

    def count_soft_deleted_eligible(self, days_old: int) -> int:
        return 5

    def count_total_guest_sessions(self) -> int:
        return 20

    def count_converted_guest_eligible(self, days_old: int) -> int:
        return 8

    def count_expired_guest_eligible(self, days_old: int) -> int:
        return 3


class TestCleanupSoftDeletedSearches:
    """Tests for cleanup_soft_deleted_searches method."""

    def test_cleanup_disabled_with_zero_retention(self, monkeypatch) -> None:
        """Test that cleanup returns 0 when retention is 0."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 0)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        result = service.cleanup_soft_deleted_searches()

        assert result == 0
        assert len(service.repository.hard_delete_old_soft_deleted_calls) == 0

    def test_cleanup_calls_repository_with_correct_days(self, monkeypatch) -> None:
        """Test that cleanup calls repository with settings value."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        result = service.cleanup_soft_deleted_searches()

        assert result == 5
        assert mock_repo.hard_delete_old_soft_deleted_calls == [30]

    def test_cleanup_handles_exception_and_reraises(self, monkeypatch) -> None:
        """Test that exceptions are logged and re-raised (lines 71-73)."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)

        mock_repo = MockSearchHistoryRepository()
        mock_repo.should_raise = True
        mock_repo.raise_on_method = "hard_delete"
        service.repository = mock_repo

        with pytest.raises(RuntimeError, match="Database error during hard delete"):
            service.cleanup_soft_deleted_searches()


class TestCleanupOldGuestSessions:
    """Tests for cleanup_old_guest_sessions method."""

    def test_cleanup_disabled_with_zero_purge_days(self, monkeypatch) -> None:
        """Test that cleanup returns 0 when purge days is 0 (lines 89-90)."""
        monkeypatch.setattr(settings, "guest_session_purge_days", 0)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        result = service.cleanup_old_guest_sessions()

        assert result == 0
        assert len(service.repository.delete_converted_guest_searches_calls) == 0

    def test_cleanup_calculates_correct_expiry(self, monkeypatch) -> None:
        """Test that expired days combines expiry + purge days."""
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        result = service.cleanup_old_guest_sessions()

        # Should delete 3 converted + 2 unconverted = 5
        assert result == 5
        assert mock_repo.delete_converted_guest_searches_calls == [30]
        assert mock_repo.delete_old_unconverted_guest_searches_calls == [37]  # 30 + 7

    def test_cleanup_handles_exception_and_reraises(self, monkeypatch) -> None:
        """Test that exceptions are logged and re-raised (lines 121-123)."""
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)

        mock_repo = MockSearchHistoryRepository()
        mock_repo.should_raise = True
        mock_repo.raise_on_method = "delete_converted"
        service.repository = mock_repo

        with pytest.raises(RuntimeError, match="Database error during delete converted"):
            service.cleanup_old_guest_sessions()


class TestCleanupAll:
    """Tests for cleanup_all method."""

    def test_cleanup_all_runs_both_cleanups(self, monkeypatch) -> None:
        """Test that cleanup_all runs both soft delete and guest session cleanup."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        soft_deleted, guest_sessions = service.cleanup_all()

        assert soft_deleted == 5
        assert guest_sessions == 5  # 3 + 2

    def test_cleanup_all_returns_zeros_when_disabled(self, monkeypatch) -> None:
        """Test cleanup_all with all settings disabled."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 0)
        monkeypatch.setattr(settings, "guest_session_purge_days", 0)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        soft_deleted, guest_sessions = service.cleanup_all()

        assert soft_deleted == 0
        assert guest_sessions == 0


class TestGetCleanupStatistics:
    """Tests for get_cleanup_statistics method."""

    def test_statistics_with_all_settings_enabled(self, monkeypatch) -> None:
        """Test statistics gathering with all settings enabled."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        stats = service.get_cleanup_statistics()

        assert stats["total_soft_deleted"] == 10
        assert stats["soft_deleted_eligible"] == 5
        assert stats["total_guest_sessions"] == 20
        assert stats["converted_guest_eligible"] == 8
        assert stats["expired_guest_eligible"] == 3

    def test_statistics_soft_delete_disabled(self, monkeypatch) -> None:
        """Test statistics when soft_delete_retention_days is 0 (line 169)."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 0)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        stats = service.get_cleanup_statistics()

        # soft_deleted_eligible should remain 0 when retention is disabled
        assert stats["soft_deleted_eligible"] == 0
        # But total count should still be retrieved
        assert stats["total_soft_deleted"] == 10

    def test_statistics_guest_purge_disabled(self, monkeypatch) -> None:
        """Test statistics when guest_session_purge_days is 0 (line 178)."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 0)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        stats = service.get_cleanup_statistics()

        # converted_guest_eligible should remain 0 when purge is disabled
        assert stats["converted_guest_eligible"] == 0
        # expired_guest_eligible also should remain 0
        assert stats["expired_guest_eligible"] == 0

    def test_statistics_expiry_disabled(self, monkeypatch) -> None:
        """Test statistics when guest_session_expiry_days is 0 (line 184)."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 0)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        stats = service.get_cleanup_statistics()

        # expired_guest_eligible should remain 0 when expiry is disabled
        assert stats["expired_guest_eligible"] == 0
        # But converted should still be counted
        assert stats["converted_guest_eligible"] == 8

    def test_statistics_all_disabled(self, monkeypatch) -> None:
        """Test statistics with all cleanup settings disabled."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 0)
        monkeypatch.setattr(settings, "guest_session_purge_days", 0)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 0)

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)
        service.repository = MockSearchHistoryRepository()

        stats = service.get_cleanup_statistics()

        assert stats["soft_deleted_eligible"] == 0
        assert stats["converted_guest_eligible"] == 0
        assert stats["expired_guest_eligible"] == 0
        # Totals should still be counted
        assert stats["total_soft_deleted"] == 10
        assert stats["total_guest_sessions"] == 20


class TestServiceInitialization:
    """Tests for service initialization."""

    def test_service_inherits_from_base_service(self) -> None:
        """Test that service inherits from BaseService."""
        from app.services.base import BaseService

        assert issubclass(SearchHistoryCleanupService, BaseService)

    def test_service_creates_repository(self) -> None:
        """Test that service creates SearchHistoryRepository."""
        from app.repositories.search_history_repository import SearchHistoryRepository

        mock_db = MagicMock()
        service = SearchHistoryCleanupService(mock_db)

        assert isinstance(service.repository, SearchHistoryRepository)

    def test_service_has_measure_operation_decorators(self) -> None:
        """Test that cleanup methods have measure_operation decorators."""
        assert hasattr(SearchHistoryCleanupService.cleanup_soft_deleted_searches, "_is_measured")
        assert hasattr(SearchHistoryCleanupService.cleanup_old_guest_sessions, "_is_measured")
        assert hasattr(SearchHistoryCleanupService.cleanup_all, "_is_measured")
        assert hasattr(SearchHistoryCleanupService.get_cleanup_statistics, "_is_measured")


class TestTransactionHandling:
    """Tests for transaction handling in cleanup operations."""

    def test_cleanup_soft_deleted_uses_transaction(self, monkeypatch) -> None:
        """Test that soft deleted cleanup uses transaction context."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        service.cleanup_soft_deleted_searches()

        # Verify commit was called (transaction completed)
        mock_db.commit.assert_called()

    def test_cleanup_guest_sessions_uses_transaction(self, monkeypatch) -> None:
        """Test that guest sessions cleanup uses transaction context."""
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        service.cleanup_old_guest_sessions()

        # Verify commit was called
        mock_db.commit.assert_called()


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_cleanup_with_negative_retention_days(self, monkeypatch) -> None:
        """Test behavior with negative retention days (treated as falsy)."""
        # Note: In Python, negative numbers are truthy, so this tests that path
        monkeypatch.setattr(settings, "soft_delete_retention_days", -1)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        # Negative values are truthy, so cleanup should still run
        service.cleanup_soft_deleted_searches()

        # Repository will be called with -1
        assert -1 in mock_repo.hard_delete_old_soft_deleted_calls

    def test_cleanup_returns_correct_types(self, monkeypatch) -> None:
        """Test that cleanup methods return correct types."""
        monkeypatch.setattr(settings, "soft_delete_retention_days", 30)
        monkeypatch.setattr(settings, "guest_session_purge_days", 30)
        monkeypatch.setattr(settings, "guest_session_expiry_days", 7)

        mock_db = MagicMock()
        mock_db.commit = MagicMock()

        service = SearchHistoryCleanupService(mock_db)
        mock_repo = MockSearchHistoryRepository()
        service.repository = mock_repo

        soft_deleted = service.cleanup_soft_deleted_searches()
        guest_sessions = service.cleanup_old_guest_sessions()
        both = service.cleanup_all()
        stats = service.get_cleanup_statistics()

        assert isinstance(soft_deleted, int)
        assert isinstance(guest_sessions, int)
        assert isinstance(both, tuple)
        assert len(both) == 2
        assert isinstance(stats, dict)
