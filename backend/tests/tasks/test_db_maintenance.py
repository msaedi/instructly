"""Unit tests for db_maintenance Celery tasks (0% → target ~100%)."""

from unittest.mock import MagicMock, patch


class TestAnalyzeHighChurnTables:
    """Tests for analyze_high_churn_tables task."""

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_analyze_success(self, mock_get_session):
        """Test ANALYZE runs successfully on all high-churn tables."""
        from app.tasks.db_maintenance import analyze_high_churn_tables

        mock_db = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        analyze_high_churn_tables()

        mock_db.execute.assert_called_once()
        sql_arg = mock_db.execute.call_args[0][0]
        assert "ANALYZE background_jobs" in str(sql_arg)

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_analyze_handles_exception(self, mock_get_session):
        """Test ANALYZE logs warning on failure and does not raise."""
        from app.tasks.db_maintenance import analyze_high_churn_tables

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("connection lost")
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        analyze_high_churn_tables()

        mock_db.execute.assert_called_once()

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_analyze_iterates_all_tables(self, mock_get_session):
        """Test that ANALYZE is attempted for each table in _HIGH_CHURN_TABLES."""
        from app.tasks.db_maintenance import _HIGH_CHURN_TABLES, analyze_high_churn_tables

        mock_db = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        analyze_high_churn_tables()

        assert mock_db.execute.call_count == len(_HIGH_CHURN_TABLES)


class TestCleanupStale2faSetups:
    """Tests for cleanup_stale_2fa_setups task."""

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_cleanup_with_rows_affected(self, mock_get_session):
        """Test cleanup commits and logs when rows are affected."""
        from app.tasks.db_maintenance import cleanup_stale_2fa_setups

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        cleanup_stale_2fa_setups()

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_cleanup_with_no_rows_affected(self, mock_get_session):
        """Test cleanup commits but doesn't log count when 0 rows affected."""
        from app.tasks.db_maintenance import cleanup_stale_2fa_setups

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        cleanup_stale_2fa_setups()

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_cleanup_handles_exception(self, mock_get_session):
        """Test cleanup logs warning on failure and does not raise."""
        from app.tasks.db_maintenance import cleanup_stale_2fa_setups

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB write failed")
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        cleanup_stale_2fa_setups()

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_not_called()

    @patch("app.tasks.db_maintenance.get_db_session")
    def test_cleanup_sql_contains_expected_clauses(self, mock_get_session):
        """Test the UPDATE statement targets the right conditions."""
        from app.tasks.db_maintenance import cleanup_stale_2fa_setups

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        cleanup_stale_2fa_setups()

        sql_arg = str(mock_db.execute.call_args[0][0])
        assert "UPDATE users" in sql_arg
        assert "totp_enabled = false" in sql_arg
        assert "totp_secret IS NOT NULL" in sql_arg
        assert "two_factor_setup_at < :cutoff" in sql_arg

        params = mock_db.execute.call_args[0][1]
        assert "cutoff" in params
