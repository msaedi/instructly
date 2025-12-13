# backend/tests/unit/services/search/test_ranking_service.py
"""
Unit tests for ranking service.

Tests the 6-signal ranking algorithm:
1. Relevance (0.35) - hybrid_score from retrieval
2. Quality (0.25) - Bayesian-averaged ratings
3. Distance (0.15) - Proximity with decay curve
4. Price (0.10) - Budget fit scoring
5. Freshness (0.10) - Recent activity
6. Completeness (0.05) - Profile quality signals

Plus audience and skill boosts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from app.services.search.filter_service import FilteredCandidate
from app.services.search.query_parser import ParsedQuery
from app.services.search.ranking_service import (
    AUDIENCE_BOOST,
    SKILL_ADJACENT_BOOST,
    SKILL_BOOST,
    RankingService,
)


@pytest.fixture
def mock_db() -> Mock:
    """Create mock database session."""
    return Mock()


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock ranking repository with default return values."""
    repo = Mock()

    repo.get_global_average_rating.return_value = 4.2

    repo.get_instructor_metrics.return_value = {
        "inst_001": {
            "avg_rating": 4.8,
            "review_count": 25,
            "last_active_at": datetime.now(timezone.utc),
            "response_rate": 0.95,
            "has_photo": True,
            "has_bio": True,
            "has_background_check": True,
            "has_identity_verified": True,
        },
        "inst_002": {
            "avg_rating": 4.2,
            "review_count": 5,
            "last_active_at": datetime.now(timezone.utc) - timedelta(days=10),
            "response_rate": 0.7,
            "has_photo": True,
            "has_bio": False,
            "has_background_check": True,
            "has_identity_verified": False,
        },
    }

    repo.get_service_audience.return_value = {
        "svc_001": "kids",
        "svc_002": "both",
    }

    repo.get_service_skill_levels.return_value = {
        "svc_001": ["beginner", "intermediate"],
        "svc_002": ["all"],
    }

    repo.get_instructor_distances.return_value = {
        "inst_001": 2.5,
        "inst_002": 8.0,
    }

    return repo


@pytest.fixture
def ranking_service(mock_db: Mock, mock_repository: Mock) -> RankingService:
    """Create ranking service with mock dependencies."""
    return RankingService(mock_db, repository=mock_repository)


@pytest.fixture
def sample_candidates() -> List[FilteredCandidate]:
    """Create sample candidates for testing."""
    return [
        FilteredCandidate(
            service_id="svc_001",
            instructor_id="inst_001",
            hybrid_score=0.9,
            name="Piano for Kids",
            description="Fun piano lessons",
            price_per_hour=50,
            available_dates=[date.today()],
            earliest_available=date.today(),
        ),
        FilteredCandidate(
            service_id="svc_002",
            instructor_id="inst_002",
            hybrid_score=0.8,
            name="Guitar Lessons",
            description="Learn guitar",
            price_per_hour=60,
            available_dates=[date.today() + timedelta(days=1)],
            earliest_available=date.today() + timedelta(days=1),
        ),
    ]


class TestQualityScore:
    """Tests for Bayesian quality score calculation."""

    def test_bayesian_average_high_reviews(self, ranking_service: RankingService) -> None:
        """High review count should stay close to actual rating."""
        score = ranking_service._calculate_quality_score(4.8, 50)

        # Should be close to 4.8/5 = 0.96
        assert 0.90 < score < 0.98

    def test_bayesian_average_low_reviews(self, ranking_service: RankingService) -> None:
        """Low review count should pull toward global average."""
        score = ranking_service._calculate_quality_score(5.0, 2)

        # Should be pulled toward 4.2 average
        # (5.0 * 2 + 4.2 * 5) / 7 = 4.43
        expected = 4.43 / 5.0
        assert abs(score - expected) < 0.01

    def test_no_reviews_uses_global_average(self, ranking_service: RankingService) -> None:
        """No reviews should return global average."""
        score = ranking_service._calculate_quality_score(0, 0)

        expected = 4.2 / 5.0
        assert abs(score - expected) < 0.01


class TestDistanceScore:
    """Tests for distance score calculation."""

    def test_very_close_gets_perfect_score(self, ranking_service: RankingService) -> None:
        """<= 1km should get 1.0."""
        assert ranking_service._calculate_distance_score(0.5) == 1.0
        assert ranking_service._calculate_distance_score(1.0) == 1.0

    def test_medium_distance_linear_decay(self, ranking_service: RankingService) -> None:
        """1-10km should decay linearly to 0.5."""
        score = ranking_service._calculate_distance_score(5.5)

        # At 5.5km: 1.0 - ((5.5 - 1) / 9) * 0.5 = 1.0 - 0.25 = 0.75
        assert abs(score - 0.75) < 0.01

    def test_far_distance_slower_decay(self, ranking_service: RankingService) -> None:
        """> 10km should decay slower, min 0.2."""
        score_15km = ranking_service._calculate_distance_score(15)
        score_30km = ranking_service._calculate_distance_score(30)

        assert score_15km > 0.2
        assert score_30km >= 0.2

    def test_no_location_neutral_score(self, ranking_service: RankingService) -> None:
        """No location should return neutral 0.7."""
        assert ranking_service._calculate_distance_score(None) == 0.7


class TestPriceScore:
    """Tests for price score calculation."""

    def test_under_budget_perfect_score(self, ranking_service: RankingService) -> None:
        """< 70% of budget should get 1.0."""
        score = ranking_service._calculate_price_score(35, 100)
        assert score == 1.0

    def test_at_budget_minimum_score(self, ranking_service: RankingService) -> None:
        """At budget should get 0.7."""
        score = ranking_service._calculate_price_score(100, 100)
        assert abs(score - 0.7) < 0.01

    def test_over_budget_penalty(self, ranking_service: RankingService) -> None:
        """Over budget should get 0.5."""
        score = ranking_service._calculate_price_score(120, 100)
        assert score == 0.5

    def test_no_budget_neutral_score(self, ranking_service: RankingService) -> None:
        """No budget specified should return 0.7."""
        score = ranking_service._calculate_price_score(50, None)
        assert score == 0.7


class TestFreshnessScore:
    """Tests for freshness score calculation."""

    def test_active_today_perfect_score(self, ranking_service: RankingService) -> None:
        """Active today should get 1.0."""
        score = ranking_service._calculate_freshness_score(datetime.now(timezone.utc))
        assert score == 1.0

    def test_active_yesterday_perfect_score(self, ranking_service: RankingService) -> None:
        """Active yesterday should still get 1.0 (within 1 day)."""
        yesterday = datetime.now(timezone.utc) - timedelta(hours=20)
        score = ranking_service._calculate_freshness_score(yesterday)
        assert score == 1.0

    def test_active_last_week(self, ranking_service: RankingService) -> None:
        """Active in last 7 days should get 0.9."""
        last_week = datetime.now(timezone.utc) - timedelta(days=5)
        score = ranking_service._calculate_freshness_score(last_week)
        assert score == 0.9

    def test_active_last_month(self, ranking_service: RankingService) -> None:
        """Active in last 30 days should get 0.7."""
        last_month = datetime.now(timezone.utc) - timedelta(days=20)
        score = ranking_service._calculate_freshness_score(last_month)
        assert score == 0.7

    def test_inactive_long_time(self, ranking_service: RankingService) -> None:
        """Inactive > 90 days should get 0.3."""
        long_ago = datetime.now(timezone.utc) - timedelta(days=120)
        score = ranking_service._calculate_freshness_score(long_ago)
        assert score == 0.3

    def test_no_activity_neutral_score(self, ranking_service: RankingService) -> None:
        """No activity data should return 0.5."""
        score = ranking_service._calculate_freshness_score(None)
        assert score == 0.5


class TestCompletenessScore:
    """Tests for profile completeness score calculation."""

    def test_complete_profile_perfect_score(self, ranking_service: RankingService) -> None:
        """Complete profile should get 1.0."""
        metrics: Dict[str, Any] = {
            "has_photo": True,
            "has_bio": True,
            "has_background_check": True,
            "has_identity_verified": True,
            "response_rate": 0.95,
        }
        score = ranking_service._calculate_completeness_score(metrics)
        assert score == 1.0

    def test_incomplete_profile_partial_score(self, ranking_service: RankingService) -> None:
        """Incomplete profile should get partial score."""
        metrics: Dict[str, Any] = {
            "has_photo": True,
            "has_bio": False,
            "has_background_check": True,
            "has_identity_verified": False,
            "response_rate": 0.7,  # Below 80% threshold
        }
        # 2 components: has_photo + has_background_check = 0.4
        score = ranking_service._calculate_completeness_score(metrics)
        assert abs(score - 0.4) < 0.01

    def test_empty_profile_zero_score(self, ranking_service: RankingService) -> None:
        """Empty profile should get 0."""
        metrics: Dict[str, Any] = {}
        score = ranking_service._calculate_completeness_score(metrics)
        assert score == 0.0


class TestAudienceBoost:
    """Tests for audience boost calculation."""

    def test_exact_match_boost(self, ranking_service: RankingService) -> None:
        """Exact audience match should get boost."""
        boost = ranking_service._calculate_audience_boost("kids", "kids")
        assert boost == AUDIENCE_BOOST

    def test_both_matches_any(self, ranking_service: RankingService) -> None:
        """'both' audience should match any hint."""
        assert ranking_service._calculate_audience_boost("both", "kids") == AUDIENCE_BOOST
        assert ranking_service._calculate_audience_boost("both", "adults") == AUDIENCE_BOOST

    def test_mismatch_no_boost(self, ranking_service: RankingService) -> None:
        """Mismatched audience should get no boost."""
        boost = ranking_service._calculate_audience_boost("kids", "adults")
        assert boost == 0.0

    def test_no_hint_no_boost(self, ranking_service: RankingService) -> None:
        """No audience hint should get no boost."""
        boost = ranking_service._calculate_audience_boost("kids", None)
        assert boost == 0.0


class TestSkillBoost:
    """Tests for skill level boost calculation."""

    def test_exact_match_boost(self, ranking_service: RankingService) -> None:
        """Exact skill match should get full boost."""
        boost = ranking_service._calculate_skill_boost(["beginner"], "beginner")
        assert boost == SKILL_BOOST

    def test_all_skills_gets_boost(self, ranking_service: RankingService) -> None:
        """'all' skills should match any query."""
        boost = ranking_service._calculate_skill_boost(["all"], "advanced")
        assert boost == SKILL_BOOST

    def test_adjacent_intermediate_boost(self, ranking_service: RankingService) -> None:
        """Intermediate query should get small boost from beginner/advanced."""
        boost_beginner = ranking_service._calculate_skill_boost(["beginner"], "intermediate")
        boost_advanced = ranking_service._calculate_skill_boost(["advanced"], "intermediate")

        assert boost_beginner == SKILL_ADJACENT_BOOST
        assert boost_advanced == SKILL_ADJACENT_BOOST

    def test_no_match_no_boost(self, ranking_service: RankingService) -> None:
        """No skill match should get no boost."""
        boost = ranking_service._calculate_skill_boost(["beginner"], "advanced")
        assert boost == 0.0

    def test_no_query_skill_no_boost(self, ranking_service: RankingService) -> None:
        """No query skill should get no boost."""
        boost = ranking_service._calculate_skill_boost(["all"], None)
        assert boost == 0.0


class TestRankingIntegration:
    """Integration tests for full ranking flow."""

    def test_ranks_candidates_by_score(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Candidates should be ranked by final score descending."""
        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(sample_candidates, query)

        assert len(result.results) == 2
        assert result.results[0].rank == 1
        assert result.results[1].rank == 2
        assert result.results[0].final_score >= result.results[1].final_score

    def test_urgency_high_sorts_by_availability(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Urgency=high should sort by earliest_available first."""
        query = ParsedQuery(
            original_query="piano asap",
            service_query="piano",
            urgency="high",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(sample_candidates, query)

        # Should be sorted by earliest_available first
        first_available = result.results[0].earliest_available
        second_available = result.results[1].earliest_available

        assert first_available is not None
        assert second_available is not None
        assert first_available <= second_available

    def test_includes_all_component_scores(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Result should include all component scores."""
        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(
            sample_candidates, query, user_location=(-73.95, 40.68)
        )

        for r in result.results:
            assert r.relevance_score >= 0
            assert r.quality_score >= 0
            assert r.distance_score >= 0
            assert r.price_score >= 0
            assert r.freshness_score >= 0
            assert r.completeness_score >= 0

    def test_empty_candidates_returns_empty_result(
        self,
        ranking_service: RankingService,
    ) -> None:
        """Empty candidates list should return empty result."""
        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates([], query)

        assert result.results == []
        assert result.total_results == 0

    def test_signals_used_includes_location_when_provided(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Signals used should include distance when location provided."""
        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(
            sample_candidates, query, user_location=(-73.95, 40.68)
        )

        assert "distance" in result.ranking_signals_used

    def test_signals_used_includes_price_when_budget_provided(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Signals used should include price when max_price provided."""
        query = ParsedQuery(
            original_query="piano under $100",
            service_query="piano",
            max_price=100,
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(sample_candidates, query)

        assert "price" in result.ranking_signals_used

    def test_preserves_soft_filter_metadata(
        self,
        ranking_service: RankingService,
    ) -> None:
        """Soft filter metadata should be preserved in ranked results."""
        soft_filtered_candidate = FilteredCandidate(
            service_id="svc_soft",
            instructor_id="inst_001",
            hybrid_score=0.85,
            name="Soft Piano",
            description="Soft filtered",
            price_per_hour=55,
            soft_filtered=True,
            soft_filter_reasons=["price_relaxed"],
        )

        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates([soft_filtered_candidate], query)

        assert len(result.results) == 1
        assert result.results[0].soft_filtered is True
        assert "price_relaxed" in result.results[0].soft_filter_reasons


class TestRankingWithBoosts:
    """Tests for ranking with audience and skill boosts."""

    def test_audience_boost_affects_ranking(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Matching audience should boost candidate score."""
        query = ParsedQuery(
            original_query="piano for kids",
            service_query="piano",
            audience_hint="kids",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(sample_candidates, query)

        # svc_001 has "kids" audience, should get boost
        svc_001_result = next(r for r in result.results if r.service_id == "svc_001")
        svc_002_result = next(r for r in result.results if r.service_id == "svc_002")

        assert svc_001_result.audience_boost == AUDIENCE_BOOST
        # svc_002 has "both" audience, also gets boost
        assert svc_002_result.audience_boost == AUDIENCE_BOOST

    def test_skill_boost_affects_ranking(
        self,
        ranking_service: RankingService,
        sample_candidates: List[FilteredCandidate],
    ) -> None:
        """Matching skill level should boost candidate score."""
        query = ParsedQuery(
            original_query="beginner piano",
            service_query="piano",
            skill_level="beginner",
            parsing_mode="regex",
        )

        result = ranking_service.rank_candidates(sample_candidates, query)

        # svc_001 has ["beginner", "intermediate"], should get full boost
        svc_001_result = next(r for r in result.results if r.service_id == "svc_001")
        # svc_002 has ["all"], also gets full boost
        svc_002_result = next(r for r in result.results if r.service_id == "svc_002")

        assert svc_001_result.skill_boost == SKILL_BOOST
        assert svc_002_result.skill_boost == SKILL_BOOST
