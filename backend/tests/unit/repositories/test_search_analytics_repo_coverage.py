"""Unit coverage for SearchAnalyticsRepository – uncovered lines around L459,737-738,742,821,866,1061-1064,1073-1078,1199,1352."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.repositories.search_analytics_repository import SearchAnalyticsRepository


def _make_repo() -> tuple[SearchAnalyticsRepository, MagicMock]:
    mock_db = MagicMock()
    repo = SearchAnalyticsRepository(mock_db)
    return repo, mock_db


class TestGetMostEffectiveSearchType:
    """L459: get_most_effective_search_type returns None when no rows."""

    def test_returns_none_when_no_data(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.order_by.return_value = query
        query.first.return_value = None

        result = repo.get_most_effective_search_type(
            date.today() - timedelta(days=7), date.today()
        )
        assert result is None

    def test_returns_tuple_when_data_exists(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.order_by.return_value = query
        row = MagicMock()
        row.search_type = "natural_language"
        row.avg_results = 5.5
        query.first.return_value = row

        result = repo.get_most_effective_search_type(
            date.today() - timedelta(days=7), date.today()
        )
        assert result == ("natural_language", 5.5)


class TestGetCandidateCategoryTrends:
    """L737-738,742: exception path and empty fallback."""

    def test_candidate_category_trends_exception_fallback(self) -> None:
        repo, mock_db = _make_repo()

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom")
            result_query = MagicMock()
            result_query.filter.return_value = result_query
            result_query.group_by.return_value = result_query
            result_query.order_by.return_value = result_query
            result_query.all.return_value = []
            return result_query

        mock_db.query.side_effect = side_effect

        now = datetime.now(timezone.utc)
        result = repo.get_candidate_category_trends(now - timedelta(days=1), now)
        assert result == []


class TestGetServiceInstructorCounts:
    """L821: empty service_ids returns {}."""

    def test_returns_empty_for_no_ids(self) -> None:
        repo, mock_db = _make_repo()
        result = repo.get_service_instructor_counts([])
        assert result == {}


class TestCountCandidatesByScoreRange:
    """L866: max_score None path."""

    def test_no_upper_bound(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.scalar.return_value = 5

        now = datetime.now(timezone.utc)
        count = repo.count_candidates_by_score_range(
            now - timedelta(hours=1), now, min_score=0.5, max_score=None
        )
        assert count == 5

    def test_with_upper_bound(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.scalar.return_value = 3

        now = datetime.now(timezone.utc)
        count = repo.count_candidates_by_score_range(
            now - timedelta(hours=1), now, min_score=0.5, max_score=0.9
        )
        assert count == 3


class TestNlResolveClickTargets:
    """L1061-1064, L1073-1078: nl_resolve_click_targets fallback paths."""

    def test_service_id_is_already_catalog_id(self) -> None:
        """L1061-1064: service_id not in instructor_services, check service_catalog."""
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query

        call_count = {"n": 0}

        def filter_side_effect(*args, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                # InstructorService.service_catalog_id lookup returns None
                result.scalar.return_value = None
            elif call_count["n"] == 2:
                # ServiceCatalog.id lookup returns a match
                result.first.return_value = MagicMock()
            elif call_count["n"] == 3:
                # InstructorProfile.user_id lookup returns None
                result.scalar.return_value = None
            elif call_count["n"] == 4:
                # InstructorProfile.id lookup returns None
                result.first.return_value = None
            else:
                result.scalar.return_value = None
            return result

        query.filter.side_effect = filter_side_effect

        cat_id, prof_id = repo.nl_resolve_click_targets("catalog-01", "unknown-01")
        assert cat_id == "catalog-01"
        assert prof_id is None

    def test_instructor_id_is_already_profile_id(self) -> None:
        """L1073-1078: instructor_id not in user_id, check if it's profile_id."""
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query

        call_count = {"n": 0}

        def filter_side_effect(*args, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar.return_value = "catalog-01"
            elif call_count["n"] == 2:
                result.scalar.return_value = None
            elif call_count["n"] == 3:
                result.first.return_value = MagicMock()
            else:
                result.scalar.return_value = None
            return result

        query.filter.side_effect = filter_side_effect

        cat_id, prof_id = repo.nl_resolve_click_targets("svc-01", "profile-01")
        assert cat_id == "catalog-01"
        assert prof_id == "profile-01"


class TestNlGetTopQueriesByDateRange:
    """L1199: nl_get_top_queries_by_date_range returns [] when base_rows empty."""

    def test_returns_empty_when_no_queries(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.having.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        result = repo.nl_get_top_queries_by_date_range(
            date.today() - timedelta(days=7), date.today()
        )
        assert result == []


class TestNlGetSearchMetrics:
    """L1352: nl_get_search_metrics zero-result fallback."""

    def test_returns_zeros_when_no_searches(self) -> None:
        repo, mock_db = _make_repo()
        mock_result = MagicMock()
        mock_result.total_searches = 0
        mock_db.execute.return_value.first.return_value = mock_result

        result = repo.nl_get_search_metrics(days=7)
        assert result["total_searches"] == 0
        assert result["avg_latency_ms"] == 0.0

    def test_returns_zeros_when_result_none(self) -> None:
        repo, mock_db = _make_repo()
        mock_db.execute.return_value.first.return_value = None

        result = repo.nl_get_search_metrics(days=7)
        assert result["total_searches"] == 0
