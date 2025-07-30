# backend/tests/unit/test_search_analytics_tasks.py
"""
Unit tests for search analytics Celery tasks.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.search_event import SearchEvent
from app.tasks.search_analytics import calculate_search_metrics, generate_search_insights, process_search_event


class TestProcessSearchEvent:
    """Test process_search_event task."""

    @patch("app.tasks.search_analytics.get_db")
    def test_process_search_event_success(self, mock_get_db):
        """Test successful processing of search event."""
        # Mock database session and event
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 10
        mock_event.search_type = "natural_language"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        # Mock task
        task = MagicMock()
        task.request.retries = 0

        # Execute task
        result = process_search_event.run(1)

        # Verify
        assert result["status"] == "success"
        assert result["event_id"] == 1
        assert "quality_score" in result
        assert mock_event.quality_score is not None
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_process_search_event_not_found(self, mock_get_db):
        """Test processing non-existent event."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Event not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Execute task
        result = process_search_event.run(999)

        # Verify
        assert result["status"] == "error"
        assert "not found" in result["message"]
        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.process_search_event.retry")
    @patch("app.tasks.search_analytics.get_db")
    def test_process_search_event_retry_on_error(self, mock_get_db, mock_retry):
        """Test task retry on database error."""
        # Mock database error
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.side_effect = Exception("Database error")

        # Mock retry to prevent actual retry
        from celery.exceptions import Retry

        mock_retry.side_effect = Retry("Retry called")

        # Execute task and expect retry
        with pytest.raises(Retry):
            process_search_event.run(1)

        # Verify retry was called with correct parameters
        mock_retry.assert_called_once()
        call_args = mock_retry.call_args
        assert isinstance(call_args.kwargs["exc"], Exception)
        assert str(call_args.kwargs["exc"]) == "Database error"
        assert call_args.kwargs["countdown"] == 60
        mock_db.close.assert_called_once()


class TestCalculateSearchMetrics:
    """Test calculate_search_metrics task."""

    @patch("app.tasks.search_analytics.get_db")
    def test_calculate_metrics_success(self, mock_get_db):
        """Test successful metrics calculation."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock query results
        popular_searches = [
            ("piano lessons", 50, 12.5),
            ("guitar teacher", 30, 8.0),
        ]
        type_distribution = [
            ("natural_language", 60),
            ("category", 20),
            ("service_pill", 15),
        ]

        # Set up mock query chains
        mock_db.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = (
            popular_searches
        )
        mock_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = type_distribution
        mock_db.query.return_value.filter.return_value.count.side_effect = [100, 40]  # total, with interactions
        mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.count.return_value = 40

        # Execute task
        result = calculate_search_metrics.run(24)

        # Verify structure
        assert result["period"]["hours"] == 24
        assert len(result["popular_searches"]) == 2
        assert result["popular_searches"][0]["query"] == "piano lessons"
        assert result["search_type_distribution"]["natural_language"] == 60
        assert result["engagement"]["total_searches"] == 100
        assert result["engagement"]["conversion_rate"] == 40.0

        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_calculate_metrics_no_data(self, mock_get_db):
        """Test metrics calculation with no data."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock empty results
        mock_db.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.count.return_value = 0

        # Execute task
        result = calculate_search_metrics.run(24)

        # Verify empty results
        assert result["popular_searches"] == []
        assert result["search_type_distribution"] == {}
        assert result["engagement"]["total_searches"] == 0
        assert result["engagement"]["conversion_rate"] == 0

        mock_db.close.assert_called_once()


class TestGenerateSearchInsights:
    """Test generate_search_insights task."""

    @patch("app.tasks.search_analytics.get_db")
    def test_generate_insights_success(self, mock_get_db):
        """Test successful insights generation."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock abandonment calculation
        mock_db.query.return_value.filter.return_value.count.side_effect = [100, 60]  # total, with interactions
        mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.count.return_value = 60

        # Mock peak hours
        peak_hours = [(14, 50), (15, 45), (16, 40)]  # 2-4 PM peak
        mock_db.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = (
            peak_hours
        )

        # Execute task
        result = generate_search_insights.run(7)

        # Verify structure
        assert result["period"]["days"] == 7
        assert "trending_searches" in result
        assert result["abandonment"]["rate"] == 40.0
        assert len(result["peak_hours"]) == 3
        assert result["peak_hours"][0]["hour"] == 14

        mock_db.close.assert_called_once()

    @patch("app.tasks.search_analytics.get_db")
    def test_generate_insights_error_handling(self, mock_get_db):
        """Test insights generation with database error."""
        # Mock database error
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.side_effect = Exception("Database error")

        # Execute task and expect error
        with pytest.raises(Exception) as exc_info:
            generate_search_insights.run(7)

        assert "Database error" in str(exc_info.value)
        mock_db.close.assert_called_once()


class TestSearchQualityCalculation:
    """Test search quality score calculation."""

    def test_quality_score_no_results(self):
        """Test quality score for search with no results."""
        from app.tasks.search_analytics import _calculate_search_quality

        mock_db = MagicMock()
        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 0
        mock_event.search_type = "natural_language"

        # No interactions
        mock_db.query.return_value.filter.return_value.first.return_value = None

        score = _calculate_search_quality(mock_db, mock_event)
        assert score < 50  # Penalty for no results

    def test_quality_score_with_interactions(self):
        """Test quality score for search with interactions."""
        from app.tasks.search_analytics import _calculate_search_quality

        mock_db = MagicMock()
        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 10
        mock_event.search_type = "service_pill"

        # Has interactions
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()

        score = _calculate_search_quality(mock_db, mock_event)
        assert score > 50  # Bonus for interactions and good result count

    def test_quality_score_too_many_results(self):
        """Test quality score for search with too many results."""
        from app.tasks.search_analytics import _calculate_search_quality

        mock_db = MagicMock()
        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 100
        mock_event.search_type = "natural_language"

        # No interactions
        mock_db.query.return_value.filter.return_value.first.return_value = None

        score = _calculate_search_quality(mock_db, mock_event)
        assert score < 50  # Penalty for too many results
