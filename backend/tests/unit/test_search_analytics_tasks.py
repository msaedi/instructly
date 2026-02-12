# backend/tests/unit/test_search_analytics_tasks.py
"""
Unit tests for search analytics Celery tasks.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.search_event import SearchEvent
from app.tasks.search_analytics import (
    calculate_search_metrics,
    generate_search_insights,
    process_search_event,
)


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

    @patch("app.tasks.search_analytics.SearchEventRepository")
    @patch("app.tasks.search_analytics.get_db")
    def test_calculate_metrics_success(self, mock_get_db, mock_search_repo_class):
        """Test successful metrics calculation."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock repository instance
        mock_repo = MagicMock()
        mock_search_repo_class.return_value = mock_repo

        # Mock repository method results
        popular_searches = [
            {"query": "piano lessons", "search_count": 50, "avg_results": 12.5},
            {"query": "guitar teacher", "search_count": 30, "avg_results": 8.0},
        ]
        type_distribution = {
            "natural_language": 60,
            "category": 20,
            "service_pill": 15,
        }

        # Set up repository method returns
        mock_repo.get_popular_searches_with_avg_results.return_value = popular_searches
        mock_repo.get_search_type_distribution.return_value = type_distribution
        mock_repo.count_searches_since.return_value = 100
        mock_repo.count_searches_with_interactions.return_value = 40

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

    @patch("app.tasks.search_analytics.SearchEventRepository")
    @patch("app.tasks.search_analytics.get_db")
    def test_calculate_metrics_no_data(self, mock_get_db, mock_search_repo_class):
        """Test metrics calculation with no data."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock repository instance
        mock_repo = MagicMock()
        mock_search_repo_class.return_value = mock_repo

        # Mock empty results
        mock_repo.get_popular_searches_with_avg_results.return_value = []
        mock_repo.get_search_type_distribution.return_value = {}
        mock_repo.count_searches_since.return_value = 0
        mock_repo.count_searches_with_interactions.return_value = 0

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

    @patch("app.tasks.search_analytics.SearchEventRepository")
    @patch("app.tasks.search_analytics.get_db")
    def test_generate_insights_success(self, mock_get_db, mock_search_repo_class):
        """Test successful insights generation."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock repository
        mock_repo = MagicMock()
        mock_search_repo_class.return_value = mock_repo

        # Mock repository methods
        mock_repo.count_searches_since.return_value = 100
        mock_repo.count_searches_with_interactions.return_value = 60
        mock_repo.get_hourly_search_counts.return_value = [
            {"hour": 14, "search_count": 50},
            {"hour": 15, "search_count": 45},
            {"hour": 16, "search_count": 40},
        ]
        mock_repo.get_popular_searches.return_value = [
            {"search_query": "piano lessons", "frequency": 25, "last_searched": "2023-01-01T14:00:00"},
            {"search_query": "guitar lessons", "frequency": 20, "last_searched": "2023-01-01T15:00:00"},
        ]

        # Execute task
        result = generate_search_insights.run(7)

        # Verify structure
        assert result["period"]["days"] == 7
        assert "trending_searches" in result
        assert result["abandonment"]["rate"] == 40.0
        assert len(result["peak_search_hours"]) == 3
        assert result["peak_search_hours"][0]["hour"] == 14

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
        from app.repositories.search_event_repository import SearchEventRepository

        mock_db = MagicMock()
        repo = SearchEventRepository(mock_db)

        # Mock the search event query
        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 0
        mock_event.search_type = "natural_language"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        # No interactions
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_event, None]

        score = repo.calculate_search_quality_score(1)
        assert score < 50  # Penalty for no results

    def test_quality_score_with_interactions(self):
        """Test quality score for search with interactions."""
        from app.repositories.search_event_repository import SearchEventRepository

        mock_db = MagicMock()
        repo = SearchEventRepository(mock_db)

        # Mock the search event query
        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 10
        mock_event.search_type = "service_pill"

        # Has interactions
        mock_interaction = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_event, mock_interaction]

        score = repo.calculate_search_quality_score(1)
        assert score > 50  # Bonus for interactions and good result count

    def test_quality_score_too_many_results(self):
        """Test quality score for search with too many results."""
        from app.repositories.search_event_repository import SearchEventRepository

        mock_db = MagicMock()
        repo = SearchEventRepository(mock_db)

        # Mock the search event query
        mock_event = MagicMock(spec=SearchEvent)
        mock_event.id = 1
        mock_event.results_count = 100
        mock_event.search_type = "natural_language"

        # No interactions
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_event, None]

        score = repo.calculate_search_quality_score(1)
        assert score < 50  # Penalty for too many results
