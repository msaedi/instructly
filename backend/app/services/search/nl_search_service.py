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

from dataclasses import dataclass, field
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.schemas.nl_search import (
    NLSearchAvailability,
    NLSearchMatchInfo,
    NLSearchMeta,
    NLSearchResponse,
    NLSearchResult,
    NLSearchScores,
    ParsedQueryInfo,
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
    """

    def __init__(
        self,
        db: "Session",
        cache_service: Optional["CacheService"] = None,
        search_cache: Optional[SearchCacheService] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> None:
        self.db = db
        self._cache_service = cache_service

        # Initialize search cache
        self.search_cache = search_cache or SearchCacheService(cache_service=cache_service)

        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService(
            db, cache_service=cache_service
        )

        # Initialize pipeline components
        self.parser = QueryParser(db)
        self.retriever = PostgresRetriever(db, self.embedding_service)
        self.filter_service = FilterService(db)
        self.ranking_service = RankingService(db)

    async def search(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]] = None,
        limit: int = 20,
        user_id: Optional[str] = None,
    ) -> NLSearchResponse:
        """
        Execute full search pipeline.

        Args:
            query: Natural language search query
            user_location: (lng, lat) tuple or None
            limit: Maximum results to return
            user_id: Optional user ID for timezone-aware parsing

        Returns:
            NLSearchResponse with results and metadata
        """
        metrics = SearchMetrics(total_start=time.time())

        # Stage 0: Check cache
        cached = self._check_cache(query, user_location)
        if cached:
            metrics.cache_hit = True
            cached["meta"]["cache_hit"] = True
            return NLSearchResponse(**cached)

        # Stage 1: Parse query
        parsed_query = await self._parse_query(query, metrics, user_id)

        # Stage 2: Retrieve candidates
        retrieval_result = await self._retrieve_candidates(parsed_query, metrics)

        # Stage 3: Filter candidates
        filter_result = await self._filter_candidates(
            retrieval_result, parsed_query, user_location, metrics
        )

        # Stage 4: Rank results
        ranking_result = self._rank_results(filter_result, parsed_query, user_location, metrics)

        # Build response
        metrics.total_latency_ms = int((time.time() - metrics.total_start) * 1000)

        response = self._build_response(query, parsed_query, ranking_result, limit, metrics)

        # Record Prometheus metrics
        record_search_metrics(
            total_latency_ms=metrics.total_latency_ms,
            stage_latencies={
                "parsing": metrics.parse_latency_ms,
                "retrieval": metrics.retrieve_latency_ms,
                "filtering": metrics.filter_latency_ms,
                "ranking": metrics.rank_latency_ms,
            },
            cache_hit=metrics.cache_hit,
            parsing_mode=parsed_query.parsing_mode,
            result_count=len(response.results),
            degraded=metrics.degraded,
            degradation_reasons=metrics.degradation_reasons,
        )

        # Cache response
        self._cache_response(query, user_location, response)

        return response

    def _check_cache(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
    ) -> Optional[Dict[str, Any]]:
        """Check for cached response."""
        try:
            result: Optional[Dict[str, Any]] = self.search_cache.get_cached_response(
                query, user_location
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
            parsed = await hybrid_parse(query, self.db, user_id)

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
    ) -> None:
        """Cache the response."""
        try:
            self.search_cache.cache_response(
                query,
                response.model_dump(),
                user_location=user_location,
            )
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")
