# backend/app/services/search/nl_search_service.py
"""
Main NL search service that orchestrates the full search pipeline.

Pipeline stages:
1. Cache check - return cached response if available
2. Query parsing - regex fast-path or LLM for complex queries
3. Query embedding - generate vector embedding
4. Candidate retrieval - hybrid vector + text search
5. Constraint filtering - price, location, availability
6. Multi-signal ranking - quality, distance, freshness, etc.
7. Response caching - store for future requests
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.repositories.retriever_repository import RetrieverRepository
from app.schemas.nl_search import (
    InstructorSummary,
    NLSearchAvailability,
    NLSearchMatchInfo,
    NLSearchMeta,
    NLSearchResponse,
    NLSearchResult,
    NLSearchResultItem,
    NLSearchScores,
    ParsedQueryInfo,
    RatingSummary,
    ServiceMatch,
)
from app.services.search.embedding_service import EmbeddingService
from app.services.search.filter_service import FilteredCandidate, FilterResult, FilterService
from app.services.search.llm_parser import hybrid_parse
from app.services.search.metrics import record_search_metrics
from app.services.search.query_parser import ParsedQuery, QueryParser
from app.services.search.ranking_service import RankedResult, RankingResult, RankingService
from app.services.search.retriever import PostgresRetriever, RetrievalResult
from app.services.search.search_cache import SearchCacheService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


@dataclass
class SearchMetrics:
    """Metrics collected during search execution."""

    total_start: float = 0
    parse_latency_ms: int = 0
    embed_latency_ms: int = 0
    retrieve_latency_ms: int = 0
    filter_latency_ms: int = 0
    rank_latency_ms: int = 0
    total_latency_ms: int = 0
    cache_hit: bool = False
    degraded: bool = False
    degradation_reasons: List[str] = field(default_factory=list)


class NLSearchService:
    """
    Orchestrates the full NL search pipeline.

    Pipeline stages:
    1. Cache check
    2. Query parsing (regex → LLM fallback)
    3. Query embedding
    4. Candidate retrieval (vector + text)
    5. Constraint filtering
    6. Multi-signal ranking
    7. Response caching

    All stages support graceful degradation.
    Supports multi-region architecture via region_code parameter.
    """

    def __init__(
        self,
        db: "Session",
        cache_service: Optional["CacheService"] = None,
        search_cache: Optional[SearchCacheService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        region_code: str = "nyc",
    ) -> None:
        self.db = db
        self._cache_service = cache_service
        self._region_code = region_code

        # Initialize search cache
        self.search_cache = search_cache or SearchCacheService(cache_service=cache_service)

        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService(
            db, cache_service=cache_service
        )

        # Initialize pipeline components
        self.parser = QueryParser(db, region_code=region_code)
        self.retriever = PostgresRetriever(db, self.embedding_service)
        self.filter_service = FilterService(db)
        self.ranking_service = RankingService(db)

        # Direct repository access for instructor-level search
        self.retriever_repository = RetrieverRepository(db)

    async def search(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]] = None,
        limit: int = 20,
        user_id: Optional[str] = None,
    ) -> NLSearchResponse:
        """
        Execute instructor-level search pipeline.

        Returns instructor-grouped results with all embedded data to eliminate
        N+1 queries from the frontend. Each result includes:
        - Instructor profile info
        - Aggregated ratings
        - Coverage areas
        - Best matching service + other matches

        Args:
            query: Natural language search query
            user_location: (lng, lat) tuple or None
            limit: Maximum instructors to return
            user_id: Optional user ID for timezone-aware parsing

        Returns:
            NLSearchResponse with instructor-level results and metadata
        """
        metrics = SearchMetrics(total_start=time.time())

        # Stage 0: Check cache
        cached = self._check_cache(query, user_location, limit)
        if cached:
            metrics.cache_hit = True
            cached["meta"]["cache_hit"] = True
            return NLSearchResponse(**cached)

        # Stage 1: Parse query
        parsed_query = await self._parse_query(query, metrics, user_id)

        # Stage 2: Get embedding for the service query
        embed_start = time.time()
        try:
            embedding = await self.embedding_service.embed_query(
                parsed_query.service_query or query
            )
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            embedding = None
            metrics.degraded = True
            metrics.degradation_reasons.append("embedding_error")
        metrics.embed_latency_ms = int((time.time() - embed_start) * 1000)

        # Stage 3: Instructor-level search with all embedded data
        # Use asyncio.to_thread to avoid blocking the event loop with sync DB call
        retrieve_start = time.time()
        if embedding:
            try:
                raw_results = await asyncio.to_thread(
                    self.retriever_repository.search_with_instructor_data,
                    embedding,
                    limit,
                )
            except Exception as e:
                logger.error(f"Instructor search failed: {e}")
                raw_results = []
                metrics.degraded = True
                metrics.degradation_reasons.append("retrieval_error")
        else:
            raw_results = []
        metrics.retrieve_latency_ms = int((time.time() - retrieve_start) * 1000)

        # Stage 4: Transform to response schema
        results = self._transform_instructor_results(raw_results, parsed_query)

        # Build response
        metrics.total_latency_ms = int((time.time() - metrics.total_start) * 1000)

        response = self._build_instructor_response(query, parsed_query, results, limit, metrics)

        # Record Prometheus metrics
        record_search_metrics(
            total_latency_ms=metrics.total_latency_ms,
            stage_latencies={
                "parsing": metrics.parse_latency_ms,
                "embedding": metrics.embed_latency_ms,
                "retrieval": metrics.retrieve_latency_ms,
                "filtering": 0,  # No separate filtering step
                "ranking": 0,  # Ranking done in SQL
            },
            cache_hit=metrics.cache_hit,
            parsing_mode=parsed_query.parsing_mode,
            result_count=len(response.results),
            degraded=metrics.degraded,
            degradation_reasons=metrics.degradation_reasons,
        )

        # Cache response
        self._cache_response(query, user_location, response, limit)

        return response

    def _check_cache(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        """Check for cached response."""
        try:
            result: Optional[Dict[str, Any]] = self.search_cache.get_cached_response(
                query, user_location, limit=limit
            )
            return result
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            return None

    async def _parse_query(
        self,
        query: str,
        metrics: SearchMetrics,
        user_id: Optional[str] = None,
    ) -> ParsedQuery:
        """Parse the search query."""
        start = time.time()

        try:
            # Try cache first
            cached_parsed = self.search_cache.get_cached_parsed_query(query)
            if cached_parsed:
                metrics.parse_latency_ms = int((time.time() - start) * 1000)
                return cached_parsed

            # Parse with hybrid approach
            parsed = await hybrid_parse(query, self.db, user_id, region_code=self._region_code)

            # Cache the parsed query
            self.search_cache.cache_parsed_query(query, parsed)

        except Exception as e:
            logger.error(f"Parsing failed, using basic extraction: {e}")
            parsed = self.parser.parse(query)
            metrics.degraded = True
            metrics.degradation_reasons.append("parsing_error")

        metrics.parse_latency_ms = int((time.time() - start) * 1000)
        return parsed

    async def _retrieve_candidates(
        self,
        parsed_query: ParsedQuery,
        metrics: SearchMetrics,
    ) -> RetrievalResult:
        """Retrieve candidate services."""
        start = time.time()

        try:
            result = await self.retriever.search(parsed_query)

            if result.degraded:
                metrics.degraded = True
                if result.degradation_reason:
                    metrics.degradation_reasons.append(result.degradation_reason)

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            result = RetrievalResult(
                candidates=[],
                total_candidates=0,
                vector_search_used=False,
                degraded=True,
                degradation_reason="retrieval_error",
            )
            metrics.degraded = True
            metrics.degradation_reasons.append("retrieval_error")

        metrics.retrieve_latency_ms = int((time.time() - start) * 1000)
        return result

    async def _filter_candidates(
        self,
        retrieval_result: RetrievalResult,
        parsed_query: ParsedQuery,
        user_location: Optional[Tuple[float, float]],
        metrics: SearchMetrics,
    ) -> FilterResult:
        """Apply constraint filters."""
        start = time.time()

        try:
            result = await self.filter_service.filter_candidates(
                retrieval_result.candidates,
                parsed_query,
                user_location=user_location,
            )
        except Exception as e:
            logger.error(f"Filtering failed: {e}")
            # Pass through unfiltered on failure
            result = FilterResult(
                candidates=[
                    FilteredCandidate(
                        service_id=c.service_id,
                        instructor_id=c.instructor_id,
                        hybrid_score=c.hybrid_score,
                        name=c.name,
                        description=c.description,
                        price_per_hour=c.price_per_hour,
                    )
                    for c in retrieval_result.candidates
                ],
                total_before_filter=len(retrieval_result.candidates),
                total_after_filter=len(retrieval_result.candidates),
                filters_applied=[],
                soft_filtering_used=False,
            )
            metrics.degraded = True
            metrics.degradation_reasons.append("filtering_error")

        metrics.filter_latency_ms = int((time.time() - start) * 1000)
        return result

    def _rank_results(
        self,
        filter_result: FilterResult,
        parsed_query: ParsedQuery,
        user_location: Optional[Tuple[float, float]],
        metrics: SearchMetrics,
    ) -> RankingResult:
        """Rank filtered candidates."""
        start = time.time()

        try:
            result = self.ranking_service.rank_candidates(
                filter_result.candidates,
                parsed_query,
                user_location=user_location,
            )
        except Exception as e:
            logger.error(f"Ranking failed: {e}")
            # Return unranked results on failure
            result = RankingResult(
                results=[
                    RankedResult(
                        service_id=c.service_id,
                        instructor_id=c.instructor_id,
                        name=c.name,
                        description=c.description,
                        price_per_hour=c.price_per_hour,
                        final_score=c.hybrid_score,
                        rank=i + 1,
                        relevance_score=c.hybrid_score,
                        quality_score=0.5,
                        distance_score=0.5,
                        price_score=0.5,
                        freshness_score=0.5,
                        completeness_score=0.5,
                        available_dates=list(c.available_dates),
                        earliest_available=c.earliest_available,
                    )
                    for i, c in enumerate(filter_result.candidates)
                ],
                total_results=len(filter_result.candidates),
            )
            metrics.degraded = True
            metrics.degradation_reasons.append("ranking_error")

        metrics.rank_latency_ms = int((time.time() - start) * 1000)
        return result

    def _build_response(
        self,
        query: str,
        parsed_query: ParsedQuery,
        ranking_result: RankingResult,
        limit: int,
        metrics: SearchMetrics,
    ) -> NLSearchResponse:
        """Build the final response."""
        # Convert ranked results to response format
        results: List[NLSearchResult] = []
        for r in ranking_result.results[:limit]:
            results.append(
                NLSearchResult(
                    service_id=r.service_id,
                    instructor_id=r.instructor_id,
                    name=r.name,
                    description=r.description,
                    price_per_hour=r.price_per_hour,
                    rank=r.rank,
                    score=round(r.final_score, 3),
                    scores=NLSearchScores(
                        relevance=round(r.relevance_score, 3),
                        quality=round(r.quality_score, 3),
                        distance=round(r.distance_score, 3),
                        price=round(r.price_score, 3),
                        freshness=round(r.freshness_score, 3),
                        completeness=round(r.completeness_score, 3),
                    ),
                    availability=NLSearchAvailability(
                        dates=[d.isoformat() for d in r.available_dates],
                        earliest=r.earliest_available.isoformat() if r.earliest_available else None,
                    ),
                    match_info=NLSearchMatchInfo(
                        audience_boost=r.audience_boost,
                        skill_boost=r.skill_boost,
                        soft_filtered=r.soft_filtered,
                        soft_filter_reasons=list(r.soft_filter_reasons),
                    ),
                )
            )

        # Build parsed query info
        parsed_info = ParsedQueryInfo(
            service_query=parsed_query.service_query,
            location=parsed_query.location_text,
            max_price=parsed_query.max_price,
            date=parsed_query.date.isoformat() if parsed_query.date else None,
            time_after=parsed_query.time_after,
            audience_hint=parsed_query.audience_hint,
            skill_level=parsed_query.skill_level,
            urgency=parsed_query.urgency,
        )

        # Build metadata
        meta = NLSearchMeta(
            query=query,
            corrected_query=parsed_query.corrected_query,
            parsed=parsed_info,
            total_results=len(results),
            limit=limit,
            latency_ms=metrics.total_latency_ms,
            cache_hit=metrics.cache_hit,
            degraded=metrics.degraded,
            degradation_reasons=metrics.degradation_reasons,
            parsing_mode=parsed_query.parsing_mode,
        )

        return NLSearchResponse(results=results, meta=meta)

    def _cache_response(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
        response: NLSearchResponse,
        limit: int,
    ) -> None:
        """Cache the response."""
        try:
            self.search_cache.cache_response(
                query,
                response.model_dump(),
                user_location=user_location,
                limit=limit,
            )
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")

    def _transform_instructor_results(
        self,
        raw_results: List[Dict[str, Any]],
        parsed_query: ParsedQuery,
    ) -> List[NLSearchResultItem]:
        """
        Transform raw DB results into instructor-level result items.

        Args:
            raw_results: Results from search_with_instructor_data
            parsed_query: Parsed query for price filtering

        Returns:
            List of NLSearchResultItem objects
        """
        results: List[NLSearchResultItem] = []

        for row in raw_results:
            # Parse matching services from JSON
            services = row["matching_services"]
            if not services:
                continue

            # Apply price filter if specified
            if parsed_query.max_price:
                services = [s for s in services if s["price_per_hour"] <= parsed_query.max_price]
                if not services:
                    continue

            # Build best match
            best = services[0]
            best_match = ServiceMatch(
                service_id=best["service_id"],
                service_catalog_id=best["service_catalog_id"],
                name=best["name"],
                description=best.get("description"),
                price_per_hour=int(best["price_per_hour"]),
                relevance_score=round(float(best["relevance_score"]), 3),
            )

            # Build other matches (max 3)
            other_matches = [
                ServiceMatch(
                    service_id=s["service_id"],
                    service_catalog_id=s["service_catalog_id"],
                    name=s["name"],
                    description=s.get("description"),
                    price_per_hour=int(s["price_per_hour"]),
                    relevance_score=round(float(s["relevance_score"]), 3),
                )
                for s in services[1:4]
            ]

            # Build instructor summary
            instructor = InstructorSummary(
                id=row["instructor_id"],
                first_name=row["first_name"],
                last_initial=row["last_initial"] or "",
                profile_picture_url=self._build_photo_url(row.get("profile_picture_key")),
                bio_snippet=row.get("bio_snippet"),
                verified=bool(row.get("verified", False)),
                years_experience=row.get("years_experience"),
            )

            # Build rating summary
            rating = RatingSummary(
                average=round(row["avg_rating"], 2) if row.get("avg_rating") else None,
                count=row.get("review_count", 0),
            )

            results.append(
                NLSearchResultItem(
                    instructor_id=row["instructor_id"],
                    instructor=instructor,
                    rating=rating,
                    coverage_areas=row.get("coverage_areas", []),
                    best_match=best_match,
                    other_matches=other_matches,
                    total_matching_services=row.get("match_count", 1),
                    relevance_score=round(row["best_score"], 3),
                )
            )

        return results

    def _build_instructor_response(
        self,
        query: str,
        parsed_query: ParsedQuery,
        results: List[NLSearchResultItem],
        limit: int,
        metrics: SearchMetrics,
    ) -> NLSearchResponse:
        """
        Build the final instructor-level response.

        Args:
            query: Original search query
            parsed_query: Parsed query details
            results: Transformed instructor results
            limit: Requested limit
            metrics: Search metrics

        Returns:
            Complete NLSearchResponse
        """
        # Build parsed query info
        parsed_info = ParsedQueryInfo(
            service_query=parsed_query.service_query,
            location=parsed_query.location_text,
            max_price=parsed_query.max_price,
            date=parsed_query.date.isoformat() if parsed_query.date else None,
            time_after=parsed_query.time_after,
            audience_hint=parsed_query.audience_hint,
            skill_level=parsed_query.skill_level,
            urgency=parsed_query.urgency,
        )

        # Build metadata
        meta = NLSearchMeta(
            query=query,
            corrected_query=parsed_query.corrected_query,
            parsed=parsed_info,
            total_results=len(results),
            limit=limit,
            latency_ms=metrics.total_latency_ms,
            cache_hit=metrics.cache_hit,
            degraded=metrics.degraded,
            degradation_reasons=metrics.degradation_reasons,
            parsing_mode=parsed_query.parsing_mode,
        )

        return NLSearchResponse(results=results[:limit], meta=meta)

    def _build_photo_url(self, key: Optional[str]) -> Optional[str]:
        """Build Cloudflare R2 URL for profile photo."""
        if not key:
            return None
        # Use R2 assets domain from settings
        assets_domain = getattr(settings, "r2_public_url", "https://assets.instainstru.com")
        return f"{assets_domain}/{key}"
