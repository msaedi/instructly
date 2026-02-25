"""
Coverage tests for ranking_service.py targeting uncovered lines and branches.

Targets:
  - L167-169: rank_candidates with repository override
  - L189: _rank_candidates_impl empty candidates
  - L270: perf log slow path
  - L385-386: _resolve_founding_boost with invalid value
  - L498: _calculate_freshness_score with date (not datetime)
  - L510: freshness score > 90 days
  - L598->601: _calculate_skill_boost intermediate adjacent
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.services.search.ranking_service import (
    AUDIENCE_BOOST,
    SKILL_ADJACENT_BOOST,
    SKILL_BOOST,
    RankingResult,
    RankingService,
)


def _make_ranking_service(repo: Mock | None = None) -> RankingService:
    """Create a RankingService with a mock repository."""
    if repo is None:
        repo = Mock()
        repo.get_global_average_rating.return_value = 4.0
        repo.get_instructor_metrics.return_value = {}
        repo.get_service_audiences.return_value = {}
        repo.get_service_skill_levels.return_value = {}
        repo.db = Mock()
    return RankingService(repository=repo)


def _make_candidate(
    *,
    service_id: str = "svc_1",
    instructor_id: str = "inst_1",
    hybrid_score: float = 0.8,
    price_per_hour: int = 50,
    name: str = "Piano",
    description: str | None = None,
    service_catalog_id: str = "cat_1",
) -> MagicMock:
    candidate = MagicMock()
    candidate.service_id = service_id
    candidate.instructor_id = instructor_id
    candidate.hybrid_score = hybrid_score
    candidate.price_per_hour = price_per_hour
    candidate.name = name
    candidate.description = description
    candidate.service_catalog_id = service_catalog_id
    candidate.soft_filtered = False
    candidate.soft_filter_reasons = []
    candidate.available_dates = []
    candidate.earliest_available = None
    return candidate


@pytest.mark.unit
class TestRankCandidatesEmpty:
    """Cover L160-161 and L188-189: empty candidates -> empty RankingResult."""

    def test_empty_candidates_returns_empty(self):
        svc = _make_ranking_service()
        result = svc.rank_candidates([], MagicMock())
        assert isinstance(result, RankingResult)
        assert result.total_results == 0
        assert result.results == []


@pytest.mark.unit
class TestRankCandidatesWithRepositoryOverride:
    """Cover L163-165: repository override path."""

    def test_repository_override_used(self):
        repo = Mock()
        repo.get_global_average_rating.return_value = 4.0
        repo.get_instructor_metrics.return_value = {
            "inst_1": {
                "avg_rating": 4.5,
                "review_count": 10,
                "last_active_at": datetime.now(timezone.utc),
                "response_rate": 80,
                "has_photo": True,
                "has_bio": True,
                "has_background_check": False,
                "has_identity_verified": False,
            }
        }
        repo.get_service_audiences.return_value = {}
        repo.get_service_skill_levels.return_value = {}
        repo.db = Mock()

        svc = RankingService(repository=repo)

        parsed = MagicMock()
        parsed.audience_hint = None
        parsed.skill_level = None
        parsed.max_price = None
        parsed.urgency = None

        candidate = _make_candidate()
        result = svc.rank_candidates([candidate], parsed)
        assert result.total_results == 1
        assert result.results[0].rank == 1


@pytest.mark.unit
class TestRankCandidatesImplEmpty:
    """Cover L188-189: _rank_candidates_impl with empty list."""

    def test_impl_empty(self):
        svc = _make_ranking_service()
        result = svc._rank_candidates_impl([], MagicMock())
        assert result.total_results == 0


@pytest.mark.unit
class TestResolveFoundingBoost:
    """Cover L385-386: invalid founding_search_boost value."""

    def test_valid_float(self):
        result = RankingService._resolve_founding_boost({"founding_search_boost": 1.5})
        assert result == 1.5

    def test_invalid_value_falls_back(self):
        """L385-386: TypeError/ValueError -> falls back to DEFAULT_PRICING_CONFIG."""
        result = RankingService._resolve_founding_boost({"founding_search_boost": "not_a_number"})
        assert isinstance(result, float)

    def test_missing_key_uses_default(self):
        result = RankingService._resolve_founding_boost({})
        assert isinstance(result, float)


@pytest.mark.unit
class TestCalculateFreshnessScore:
    """Cover L498, L510: freshness with date input and > 90 days."""

    def test_none_returns_half(self):
        svc = _make_ranking_service()
        assert svc._calculate_freshness_score(None) == 0.5

    def test_datetime_input(self):
        """L495-496: datetime instance -> uses .date()."""
        svc = _make_ranking_service()
        now = datetime.now(timezone.utc)
        score = svc._calculate_freshness_score(now)
        assert score == 1.0

    def test_date_input(self):
        """L498: date instance (not datetime) -> used directly."""
        svc = _make_ranking_service()
        today = datetime.now(timezone.utc).date()
        score = svc._calculate_freshness_score(today)  # type: ignore[arg-type]
        assert score == 1.0

    def test_7_days_ago(self):
        svc = _make_ranking_service()
        dt = datetime.now(timezone.utc) - timedelta(days=5)
        assert svc._calculate_freshness_score(dt) == 0.9

    def test_30_days_ago(self):
        svc = _make_ranking_service()
        dt = datetime.now(timezone.utc) - timedelta(days=20)
        assert svc._calculate_freshness_score(dt) == 0.7

    def test_90_days_ago(self):
        """L509-510: 31-90 days -> 0.5."""
        svc = _make_ranking_service()
        dt = datetime.now(timezone.utc) - timedelta(days=60)
        assert svc._calculate_freshness_score(dt) == 0.5

    def test_over_90_days(self):
        """L510: > 90 days -> 0.3."""
        svc = _make_ranking_service()
        dt = datetime.now(timezone.utc) - timedelta(days=120)
        assert svc._calculate_freshness_score(dt) == 0.3


@pytest.mark.unit
class TestCalculateSkillBoost:
    """Cover L598->601: intermediate adjacent boost."""

    def test_no_query_skill(self):
        svc = _make_ranking_service()
        assert svc._calculate_skill_boost(["beginner"], None) == 0.0

    def test_all_in_skills(self):
        svc = _make_ranking_service()
        assert svc._calculate_skill_boost(["all"], "beginner") == SKILL_BOOST

    def test_exact_match(self):
        svc = _make_ranking_service()
        assert svc._calculate_skill_boost(["beginner"], "beginner") == SKILL_BOOST

    def test_intermediate_adjacent_beginner(self):
        """L597-599: intermediate query + beginner in skills -> adjacent boost."""
        svc = _make_ranking_service()
        assert svc._calculate_skill_boost(["beginner"], "intermediate") == SKILL_ADJACENT_BOOST

    def test_intermediate_adjacent_advanced(self):
        svc = _make_ranking_service()
        assert svc._calculate_skill_boost(["advanced"], "intermediate") == SKILL_ADJACENT_BOOST

    def test_no_match_returns_zero(self):
        """L601: no match at all -> 0.0."""
        svc = _make_ranking_service()
        assert svc._calculate_skill_boost(["advanced"], "beginner") == 0.0


@pytest.mark.unit
class TestCalculateAudienceBoost:
    """Cover audience boost branches."""

    def test_no_query_audience(self):
        svc = _make_ranking_service()
        assert svc._calculate_audience_boost("adults", None) == 0.0

    def test_both_matches_any(self):
        svc = _make_ranking_service()
        assert svc._calculate_audience_boost("both", "kids") == AUDIENCE_BOOST

    def test_exact_audience_match(self):
        svc = _make_ranking_service()
        assert svc._calculate_audience_boost("kids", "kids") == AUDIENCE_BOOST

    def test_mismatch(self):
        svc = _make_ranking_service()
        assert svc._calculate_audience_boost("adults", "kids") == 0.0


@pytest.mark.unit
class TestPerfLogBranch:
    """Cover L270: perf logging when enabled."""

    @patch("app.services.search.ranking_service._PERF_LOG_ENABLED", True)
    @patch("app.services.search.ranking_service._PERF_LOG_SLOW_MS", 0)
    def test_perf_log_enabled_logs(self):
        """L269-270: when perf log enabled and total_ms >= threshold -> logs."""
        repo = Mock()
        repo.get_global_average_rating.return_value = 4.0
        repo.get_instructor_metrics.return_value = {
            "inst_1": {
                "avg_rating": 4.5,
                "review_count": 10,
                "last_active_at": datetime.now(timezone.utc),
                "response_rate": 80,
                "has_photo": True,
                "has_bio": True,
                "has_background_check": False,
                "has_identity_verified": False,
            }
        }
        repo.get_service_audiences.return_value = {}
        repo.get_service_skill_levels.return_value = {}
        repo.db = Mock()

        svc = RankingService(repository=repo)

        parsed = MagicMock()
        parsed.audience_hint = None
        parsed.skill_level = None
        parsed.max_price = None
        parsed.urgency = None

        candidate = _make_candidate()
        with patch("app.services.search.ranking_service.logger") as mock_logger:
            svc._rank_candidates_impl([candidate], parsed)
            # Perf log should have been called
            assert mock_logger.info.called
