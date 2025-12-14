# backend/app/services/search/ranking_service.py
"""
Ranking service for NL search results.
Combines multiple signals to produce final ranked results.

Ranking Formula:
    final_score = (
        0.35 × relevance +
        0.25 × quality +
        0.15 × distance +
        0.10 × price +
        0.10 × freshness +
        0.05 × completeness
    ) + audience_boost + skill_boost

Design notes:
- Bayesian averaging for quality score (handles low review counts)
- Audience hint and skill level are additive boosts, not weights
- Tie-breaking: quality → price → distance → tenure
- Urgency="high" overrides to sort by earliest availability
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.search.filter_service import FilteredCandidate
    from app.services.search.query_parser import ParsedQuery

from app.repositories.ranking_repository import RankingRepository

logger = logging.getLogger(__name__)

# Ranking weights
WEIGHT_RELEVANCE = 0.35
WEIGHT_QUALITY = 0.25
WEIGHT_DISTANCE = 0.15
WEIGHT_PRICE = 0.10
WEIGHT_FRESHNESS = 0.10
WEIGHT_COMPLETENESS = 0.05

# Boosts
AUDIENCE_BOOST = 0.1
SKILL_BOOST = 0.05
SKILL_ADJACENT_BOOST = 0.02

# Bayesian averaging parameters
BAYESIAN_MIN_REVIEWS = 5


@dataclass
class RankedResult:
    """A ranked search result with all scoring details."""

    # Identity
    service_id: str
    instructor_id: str

    # Service data
    name: str
    description: Optional[str]
    price_per_hour: int

    # Final ranking
    final_score: float
    rank: int  # 1-based position

    # Component scores (for transparency/debugging)
    relevance_score: float
    quality_score: float
    distance_score: float
    price_score: float
    freshness_score: float
    completeness_score: float

    # Boosts applied
    audience_boost: float = 0.0
    skill_boost: float = 0.0

    # From filtering
    soft_filtered: bool = False
    soft_filter_reasons: List[str] = field(default_factory=list)

    # Availability
    available_dates: List[date] = field(default_factory=list)
    earliest_available: Optional[date] = None


@dataclass
class RankingResult:
    """Result of the ranking phase."""

    results: List[RankedResult]
    total_results: int
    ranking_signals_used: List[str] = field(default_factory=list)


class RankingService:
    """
    Service for ranking search results by multiple signals.

    Ranking Formula:
    final_score = (
        0.35 × relevance +
        0.25 × quality +
        0.15 × distance +
        0.10 × price +
        0.10 × freshness +
        0.05 × completeness
    ) + audience_boost + skill_boost

    Signals:
    1. Relevance (0.35) - hybrid_score from retrieval phase
    2. Quality (0.25) - Bayesian-averaged ratings
    3. Distance (0.15) - Proximity to user with decay curve
    4. Price (0.10) - Budget fit scoring
    5. Freshness (0.10) - Recent activity scoring
    6. Completeness (0.05) - Profile quality signals
    """

    def __init__(
        self,
        db: "Session",
        repository: Optional[RankingRepository] = None,
    ) -> None:
        self.db = db
        self.repository = repository or RankingRepository(db)
        self._global_avg_rating: Optional[float] = None

    @property
    def global_avg_rating(self) -> float:
        """Lazy-load global average rating."""
        if self._global_avg_rating is None:
            self._global_avg_rating = self.repository.get_global_average_rating()
        return self._global_avg_rating

    def rank_candidates(
        self,
        candidates: List["FilteredCandidate"],
        parsed_query: "ParsedQuery",
        user_location: Optional[Tuple[float, float]] = None,  # (lng, lat)
    ) -> RankingResult:
        """
        Rank filtered candidates by multiple signals.

        Args:
            candidates: Filtered candidates from Phase 6
            parsed_query: Parsed query with constraints
            user_location: User's (lng, lat) for distance scoring

        Returns:
            RankingResult with sorted results and metadata
        """
        if not candidates:
            return RankingResult(results=[], total_results=0)

        # Collect IDs for batch queries
        instructor_ids = list({c.instructor_id for c in candidates})
        service_ids = [c.service_id for c in candidates]

        # Fetch all metrics in batch
        instructor_metrics = self.repository.get_instructor_metrics(instructor_ids)
        # Audience + skill are boosts only; skip these queries unless hints are present.
        service_audiences: Dict[str, str] = {}
        service_skills: Dict[str, List[str]] = {}
        if parsed_query.audience_hint:
            service_audiences = self.repository.get_service_audience(service_ids)
        if parsed_query.skill_level:
            service_skills = self.repository.get_service_skill_levels(service_ids)

        # Get distances if user location provided
        distances: Dict[str, float] = {}
        if user_location:
            lng, lat = user_location
            distances = self.repository.get_instructor_distances(instructor_ids, lng, lat)

        # Score each candidate
        scored: List[RankedResult] = []
        for candidate in candidates:
            metrics = instructor_metrics.get(candidate.instructor_id, {})
            audience = service_audiences.get(candidate.service_id, "both")
            skills = service_skills.get(candidate.service_id, ["all"])
            distance_km = distances.get(candidate.instructor_id)

            result = self._score_candidate(
                candidate,
                metrics,
                audience,
                skills,
                distance_km,
                parsed_query,
            )
            scored.append(result)

        # Sort by final_score descending
        scored.sort(key=lambda r: r.final_score, reverse=True)

        # Handle special sort orders
        if parsed_query.urgency == "high":
            # Sort by earliest available first, then by score
            scored.sort(
                key=lambda r: (
                    r.earliest_available or date.max,
                    -r.final_score,
                )
            )

        # Assign ranks
        for i, result in enumerate(scored):
            result.rank = i + 1

        # Determine which signals were used
        signals_used = ["relevance", "quality", "freshness", "completeness"]
        if user_location:
            signals_used.append("distance")
        if parsed_query.max_price:
            signals_used.append("price")

        return RankingResult(
            results=scored,
            total_results=len(scored),
            ranking_signals_used=signals_used,
        )

    def _score_candidate(
        self,
        candidate: "FilteredCandidate",
        metrics: Dict[str, Any],
        audience: str,
        skills: List[str],
        distance_km: Optional[float],
        parsed_query: "ParsedQuery",
    ) -> RankedResult:
        """Calculate all scores for a single candidate."""

        # 1. Relevance score (from retrieval)
        relevance_score = candidate.hybrid_score

        # 2. Quality score (Bayesian average)
        quality_score = self._calculate_quality_score(
            metrics.get("avg_rating", 0),
            metrics.get("review_count", 0),
        )

        # 3. Distance score
        distance_score = self._calculate_distance_score(distance_km)

        # 4. Price score
        price_score = self._calculate_price_score(
            candidate.price_per_hour,
            parsed_query.max_price,
        )

        # 5. Freshness score
        freshness_score = self._calculate_freshness_score(metrics.get("last_active_at"))

        # 6. Completeness score
        completeness_score = self._calculate_completeness_score(metrics)

        # Calculate weighted sum
        base_score = (
            WEIGHT_RELEVANCE * relevance_score
            + WEIGHT_QUALITY * quality_score
            + WEIGHT_DISTANCE * distance_score
            + WEIGHT_PRICE * price_score
            + WEIGHT_FRESHNESS * freshness_score
            + WEIGHT_COMPLETENESS * completeness_score
        )

        # Apply boosts
        audience_boost = self._calculate_audience_boost(audience, parsed_query.audience_hint)
        skill_boost = self._calculate_skill_boost(skills, parsed_query.skill_level)

        final_score = base_score + audience_boost + skill_boost

        return RankedResult(
            service_id=candidate.service_id,
            instructor_id=candidate.instructor_id,
            name=candidate.name,
            description=candidate.description,
            price_per_hour=candidate.price_per_hour,
            final_score=final_score,
            rank=0,  # Set later after sorting
            relevance_score=relevance_score,
            quality_score=quality_score,
            distance_score=distance_score,
            price_score=price_score,
            freshness_score=freshness_score,
            completeness_score=completeness_score,
            audience_boost=audience_boost,
            skill_boost=skill_boost,
            soft_filtered=candidate.soft_filtered,
            soft_filter_reasons=list(candidate.soft_filter_reasons),
            available_dates=list(candidate.available_dates),
            earliest_available=candidate.earliest_available,
        )

    def _calculate_quality_score(
        self,
        avg_rating: float,
        review_count: int,
    ) -> float:
        """
        Calculate quality score using Bayesian averaging.

        Formula: (R × v + C × m) / (v + m)
        Where:
          R = instructor's rating
          v = review count
          C = global average rating
          m = minimum reviews for confidence

        Returns:
            Normalized score 0-1
        """
        if review_count == 0:
            # No reviews - use global average
            return self.global_avg_rating / 5.0

        r_rating = avg_rating
        v_count = review_count
        c_global = self.global_avg_rating
        m_min = BAYESIAN_MIN_REVIEWS

        bayesian_avg = (r_rating * v_count + c_global * m_min) / (v_count + m_min)

        # Normalize to 0-1
        return bayesian_avg / 5.0

    def _calculate_distance_score(
        self,
        distance_km: Optional[float],
    ) -> float:
        """
        Calculate distance score with decay curve.

        <= 1km: 1.0
        1-10km: linear decay to 0.5
        > 10km: slower decay to 0.2

        Returns:
            Score 0.2-1.0 based on distance
        """
        if distance_km is None:
            return 0.7  # Neutral if no location

        if distance_km <= 1:
            return 1.0
        elif distance_km <= 10:
            # Linear decay from 1.0 to 0.5 over 9km
            return 1.0 - ((distance_km - 1) / 9) * 0.5
        else:
            # Slower decay from 0.5 to 0.2 over 20km
            return max(0.2, 0.5 - ((distance_km - 10) / 20) * 0.3)

    def _calculate_price_score(
        self,
        price: int,
        max_price: Optional[int],
    ) -> float:
        """
        Calculate price score based on budget fit.

        No budget: 0.7 (neutral)
        Under 70% of budget: 1.0
        70-100% of budget: 0.7-1.0 linear
        Over budget: 0.5

        Returns:
            Score 0.5-1.0 based on price fit
        """
        if max_price is None:
            return 0.7

        ratio = price / max_price

        if ratio <= 0.7:
            return 1.0
        elif ratio <= 1.0:
            # Linear decay from 1.0 to 0.7
            return 1.0 - ((ratio - 0.7) / 0.3) * 0.3
        else:
            return 0.5

    def _calculate_freshness_score(
        self,
        last_active_at: Optional[datetime],
    ) -> float:
        """
        Calculate freshness score based on last activity.

        <= 1 day: 1.0
        <= 7 days: 0.9
        <= 30 days: 0.7
        <= 90 days: 0.5
        > 90 days: 0.3

        Returns:
            Score 0.3-1.0 based on recency
        """
        if last_active_at is None:
            return 0.5  # Unknown activity

        # Convert to date for comparison
        if isinstance(last_active_at, datetime):
            last_active_date = last_active_at.date()
        else:
            last_active_date = last_active_at

        today = datetime.now(timezone.utc).date()
        days_since = (today - last_active_date).days

        if days_since <= 1:
            return 1.0
        elif days_since <= 7:
            return 0.9
        elif days_since <= 30:
            return 0.7
        elif days_since <= 90:
            return 0.5
        else:
            return 0.3

    def _calculate_completeness_score(
        self,
        metrics: Dict[str, Any],
    ) -> float:
        """
        Calculate profile completeness score.

        Components (each 0.2):
        - Has photo
        - Has bio (>= 100 chars)
        - Background check verified
        - Identity verified
        - Response rate > 80%

        Returns:
            Score 0-1.0 based on profile completeness
        """
        score = 0.0

        if metrics.get("has_photo"):
            score += 0.2
        if metrics.get("has_bio"):
            score += 0.2
        if metrics.get("has_background_check"):
            score += 0.2
        if metrics.get("has_identity_verified"):
            score += 0.2
        # response_rate is stored as 0-100 in DB, normalize to 0-1
        response_rate = (metrics.get("response_rate") or 0) / 100
        if response_rate > 0.8:
            score += 0.2

        return score

    def _calculate_audience_boost(
        self,
        service_audience: str,
        query_audience: Optional[str],
    ) -> float:
        """
        Calculate audience match boost.

        +0.1 if service audience matches query audience hint.
        "both" matches any hint.

        Returns:
            0.0 or AUDIENCE_BOOST (0.1)
        """
        if not query_audience:
            return 0.0

        if service_audience == "both":
            return AUDIENCE_BOOST

        if service_audience == query_audience:
            return AUDIENCE_BOOST

        return 0.0

    def _calculate_skill_boost(
        self,
        service_skills: List[str],
        query_skill: Optional[str],
    ) -> float:
        """
        Calculate skill level match boost.

        +0.05 for exact match
        +0.02 for adjacent match (intermediate matches beginner/advanced)

        Returns:
            0.0, SKILL_ADJACENT_BOOST (0.02), or SKILL_BOOST (0.05)
        """
        if not query_skill:
            return 0.0

        if "all" in service_skills:
            return SKILL_BOOST

        if query_skill in service_skills:
            return SKILL_BOOST

        # Check adjacent match for intermediate
        if query_skill == "intermediate":
            if "beginner" in service_skills or "advanced" in service_skills:
                return SKILL_ADJACENT_BOOST

        return 0.0
