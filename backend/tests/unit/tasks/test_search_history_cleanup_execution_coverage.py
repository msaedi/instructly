"""
Tests for search_history_cleanup.py execution paths - targeting uncovered lines.

Covers lines: 53-90, 103-127 (task execution code paths).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCleanupSearchHistoryExecution:
    """Tests for cleanup_search_history task execution paths."""

    def test_successful_cleanup(self) -> None:
        """Test successful execution of cleanup task (lines 53-84)."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.side_effect = [
            {"soft_deleted_eligible": 10, "converted_guest_eligible": 5, "expired_guest_eligible": 3},
            {"soft_deleted_eligible": 0, "converted_guest_eligible": 0, "expired_guest_eligible": 0},
        ]
        mock_cleanup_service.cleanup_all.return_value = (10, 8)

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            result = cleanup_search_history.run()

            assert result["status"] == "success"
            assert result["soft_deleted_removed"] == 10
            assert result["guest_sessions_removed"] == 8
            assert "stats_before" in result
            assert "stats_after" in result
            assert "completed_at" in result
            mock_session.close.assert_called_once()

    def test_cleanup_logs_statistics(self) -> None:
        """Test that cleanup task logs before and after statistics."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        stats_before = {"soft_deleted_eligible": 100, "converted_guest_eligible": 50, "expired_guest_eligible": 0}
        stats_after = {"soft_deleted_eligible": 0, "converted_guest_eligible": 0, "expired_guest_eligible": 0}
        mock_cleanup_service.get_cleanup_statistics.side_effect = [stats_before, stats_after]
        mock_cleanup_service.cleanup_all.return_value = (100, 50)

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            result = cleanup_search_history.run()

            assert result["stats_before"] == stats_before
            assert result["stats_after"] == stats_after

    def test_cleanup_exception_path(self) -> None:
        """Test exception handling in cleanup task (lines 86-88)."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.side_effect = Exception("Database error")

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            with pytest.raises(Exception, match="Database error"):
                cleanup_search_history.run()

            mock_session.close.assert_called_once()

    def test_cleanup_session_closed_on_success(self) -> None:
        """Test that session is closed on successful cleanup (line 90)."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 0,
            "converted_guest_eligible": 0,
            "expired_guest_eligible": 0,
        }
        mock_cleanup_service.cleanup_all.return_value = (0, 0)

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            cleanup_search_history.run()

            mock_session.close.assert_called_once()

    def test_cleanup_with_zero_records(self) -> None:
        """Test cleanup when no records need to be deleted."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 0,
            "converted_guest_eligible": 0,
            "expired_guest_eligible": 0,
        }
        mock_cleanup_service.cleanup_all.return_value = (0, 0)

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            result = cleanup_search_history.run()

            assert result["soft_deleted_removed"] == 0
            assert result["guest_sessions_removed"] == 0


class TestDryRunExecution:
    """Tests for search_history_cleanup_dry_run task execution paths."""

    def test_successful_dry_run(self) -> None:
        """Test successful execution of dry run task (lines 103-121)."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 25,
            "converted_guest_eligible": 10,
            "expired_guest_eligible": 5,
        }

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            result = search_history_cleanup_dry_run.run()

            assert result["status"] == "dry_run"
            assert result["statistics"] == {
                "soft_deleted_eligible": 25,
                "converted_guest_eligible": 10,
                "expired_guest_eligible": 5,
            }
            assert result["would_delete"]["soft_deleted"] == 25
            assert result["would_delete"]["guest_sessions"] == 15  # 10 + 5
            assert "timestamp" in result
            mock_session.close.assert_called_once()

    def test_dry_run_exception_path(self) -> None:
        """Test exception handling in dry run task (lines 123-125)."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.side_effect = Exception("Stats error")

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            with pytest.raises(Exception, match="Stats error"):
                search_history_cleanup_dry_run.run()

            mock_session.close.assert_called_once()

    def test_dry_run_session_closed_on_success(self) -> None:
        """Test that session is closed on successful dry run (line 127)."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 0,
            "converted_guest_eligible": 0,
            "expired_guest_eligible": 0,
        }

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            search_history_cleanup_dry_run.run()

            mock_session.close.assert_called_once()

    def test_dry_run_calculates_would_delete_correctly(self) -> None:
        """Test that would_delete sums converted and expired guests."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 100,
            "converted_guest_eligible": 30,
            "expired_guest_eligible": 20,
        }

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            result = search_history_cleanup_dry_run.run()

            # guest_sessions = converted_guest_eligible + expired_guest_eligible
            assert result["would_delete"]["guest_sessions"] == 50  # 30 + 20


class TestSessionManagement:
    """Tests for proper session management."""

    def test_cleanup_creates_new_session(self) -> None:
        """Test that cleanup task creates a new database session."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 0,
            "converted_guest_eligible": 0,
            "expired_guest_eligible": 0,
        }
        mock_cleanup_service.cleanup_all.return_value = (0, 0)

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            cleanup_search_history.run()

            mock_session_local.assert_called_once()

    def test_dry_run_creates_new_session(self) -> None:
        """Test that dry run task creates a new database session."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        mock_session = MagicMock()
        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 0,
            "converted_guest_eligible": 0,
            "expired_guest_eligible": 0,
        }

        with patch("app.tasks.search_history_cleanup.SessionLocal") as mock_session_local, \
             patch("app.tasks.search_history_cleanup.SearchHistoryCleanupService") as mock_service_class:
            mock_session_local.return_value = mock_session
            mock_service_class.return_value = mock_cleanup_service

            search_history_cleanup_dry_run.run()

            mock_session_local.assert_called_once()
