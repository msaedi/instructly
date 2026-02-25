"""
Coverage tests for app/tasks/search_analytics.py — targeting uncovered lines:
  L142-144: calculate_search_metrics exception path
  L193-197: generate_search_insights get_hourly_search_counts AttributeError

Bug hunts:
  - Empty event list
  - Batch size boundary
  - Task error handling
"""

from unittest.mock import MagicMock, patch

import pytest


class TestProcessSearchEvent:
    @patch("app.tasks.search_analytics.get_db")
    def test_event_not_found(self, mock_get_db):
        """Event not found → returns error dict."""
        from app.tasks.search_analytics import process_search_event

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = process_search_event(event_id="nonexistent_01ABC")

        assert result["status"] == "error"
        assert "not found" in result["message"]
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_event_processed_successfully(self, mock_get_db):
        """Happy path: event is processed with quality score."""
        from app.tasks.search_analytics import process_search_event

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_event = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = mock_event
        mock_repo.calculate_search_quality_score.return_value = 0.85

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = process_search_event(event_id="event_01ABC")

        assert result["status"] == "success"
        assert result["quality_score"] == 0.85
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_event_processing_retries_on_error(self, mock_get_db):
        """Exception during processing → retry is called."""
        from app.tasks.search_analytics import process_search_event

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.get_by_id.side_effect = RuntimeError("DB error")

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            # The task will call self.retry, which raises Retry exception
            # Since we're calling the function directly, it will raise
            with pytest.raises(Exception):
                process_search_event(event_id="event_01ABC")
        mock_db.close.assert_called_once()


class TestCalculateSearchMetrics:
    @patch("app.tasks.search_analytics.get_db")
    def test_metrics_calculated_successfully(self, mock_get_db):
        """Happy path: metrics returned."""
        from app.tasks.search_analytics import calculate_search_metrics

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.get_popular_searches_with_avg_results.return_value = [
            {"query": "yoga", "count": 50}
        ]
        mock_repo.get_search_type_distribution.return_value = {"text": 80, "filter": 20}
        mock_repo.count_searches_since.return_value = 100
        mock_repo.count_searches_with_interactions.return_value = 30

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = calculate_search_metrics(hours_back=24)

        assert result["engagement"]["total_searches"] == 100
        assert result["engagement"]["conversion_rate"] == 30.0
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_metrics_zero_searches(self, mock_get_db):
        """No searches → conversion_rate is 0."""
        from app.tasks.search_analytics import calculate_search_metrics

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.get_popular_searches_with_avg_results.return_value = []
        mock_repo.get_search_type_distribution.return_value = {}
        mock_repo.count_searches_since.return_value = 0
        mock_repo.count_searches_with_interactions.return_value = 0

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = calculate_search_metrics(hours_back=24)

        assert result["engagement"]["conversion_rate"] == 0
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_metrics_exception_propagates(self, mock_get_db):
        """L142-144: Exception in metrics calculation → re-raised."""
        from app.tasks.search_analytics import calculate_search_metrics

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.get_popular_searches_with_avg_results.side_effect = RuntimeError("DB error")

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            with pytest.raises(RuntimeError, match="DB error"):
                calculate_search_metrics(hours_back=24)
        mock_db.close.assert_called_once()


class TestGenerateSearchInsights:
    @patch("app.tasks.search_analytics.get_db")
    def test_insights_generated_successfully(self, mock_get_db):
        """Happy path: insights returned."""
        from app.tasks.search_analytics import generate_search_insights

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.count_searches_since.return_value = 100
        mock_repo.count_searches_with_interactions.return_value = 70
        mock_repo.get_hourly_search_counts.return_value = [{"hour": 10, "count": 20}]
        mock_repo.get_popular_searches.return_value = [{"query": "piano", "count": 30}]

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = generate_search_insights(days_back=7)

        assert result["abandonment"]["rate"] == 30.0
        assert len(result["peak_search_hours"]) == 1
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_insights_zero_searches(self, mock_get_db):
        """No searches → abandonment_rate is 0."""
        from app.tasks.search_analytics import generate_search_insights

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.count_searches_since.return_value = 0
        mock_repo.count_searches_with_interactions.return_value = 0
        mock_repo.get_hourly_search_counts.return_value = []
        mock_repo.get_popular_searches.return_value = []

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = generate_search_insights(days_back=7)

        assert result["abandonment"]["rate"] == 0.0

    @patch("app.tasks.search_analytics.get_db")
    def test_insights_hourly_counts_attribute_error(self, mock_get_db):
        """L193-197: get_hourly_search_counts raises AttributeError → empty peak hours."""
        from app.tasks.search_analytics import generate_search_insights

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.count_searches_since.return_value = 50
        mock_repo.count_searches_with_interactions.return_value = 20
        mock_repo.get_hourly_search_counts.side_effect = AttributeError("missing method")
        mock_repo.get_popular_searches.return_value = []

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            result = generate_search_insights(days_back=7)

        assert result["peak_search_hours"] == []
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_insights_exception_propagates(self, mock_get_db):
        """Exception during insights → re-raised."""
        from app.tasks.search_analytics import generate_search_insights

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_repo = MagicMock()
        mock_repo.count_searches_since.side_effect = RuntimeError("DB error")

        with patch("app.tasks.search_analytics.SearchEventRepository", return_value=mock_repo):
            with pytest.raises(RuntimeError, match="DB error"):
                generate_search_insights(days_back=7)
        mock_db.close.assert_called_once()
