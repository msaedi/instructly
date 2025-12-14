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
from app.schemas.nl_search import (
    InstructorSummary,
    NLSearchMeta,
    NLSearchResponse,
    NLSearchResultItem,
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
    from app.services.search.location_resolver import ResolvedLocation

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
        self.search_cache = search_cache or SearchCacheService(
            cache_service=cache_service, region_code=region_code
        )

        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService(
            db, cache_service=cache_service
        )

        # Initialize pipeline components
        self.parser = QueryParser(db, region_code=region_code)
        self.retriever = PostgresRetriever(db, self.embedding_service)
        self.filter_service = FilterService(db, region_code=region_code)
        self.ranking_service = RankingService(db)

        # Direct repository access for bulk data hydration (instructor/service info)
        from app.repositories.retriever_repository import RetrieverRepository

        self.retriever_repository = RetrieverRepository(db)

    async def search(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]] = None,
        limit: int = 20,
        user_id: Optional[str] = None,
    ) -> NLSearchResponse:
        """
        Execute full NL search pipeline and return instructor-level results.

        Pipeline:
        1. Cache check
        2. Parse query (regex → LLM as needed)
        3. Retrieve candidates (hybrid vector + trigram; text-only fallback)
        4. Filter candidates (price, location, availability; soft fallback)
        5. Rank candidates (6-signal scoring + audience/skill boosts)
        6. Hydrate top instructors with embedded data (eliminate N+1)

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

        # Stage 2: Retrieve candidates (vector+text hybrid; degraded fallback)
        retrieval_result = await self._retrieve_candidates(parsed_query, metrics)

        # Stage 3: Apply constraint filters (price, location, availability)
        filter_result = await self._filter_candidates(
            retrieval_result,
            parsed_query,
            user_location,
            metrics,
        )

        # Stage 4: Rank candidates (multi-signal scoring)
        rank_start = time.time()
        try:
            ranking_result = await asyncio.to_thread(
                self.ranking_service.rank_candidates,
                filter_result.candidates,
                parsed_query,
                user_location,
            )
        except Exception as e:
            logger.error(f"Ranking failed: {e}")
            ranking_result = RankingResult(results=[], total_results=0)
            metrics.degraded = True
            metrics.degradation_reasons.append("ranking_error")
        metrics.rank_latency_ms = int((time.time() - rank_start) * 1000)

        # Stage 5: Build instructor-level results with embedded data
        try:
            results = await self._hydrate_instructor_results(
                ranking_result.results,
                limit=limit,
                location_resolution=filter_result.location_resolution if filter_result else None,
            )
        except Exception as e:
            logger.error(f"Hydration failed: {e}")
            results = []
            metrics.degraded = True
            metrics.degradation_reasons.append("hydration_error")

        # Build response
        metrics.total_latency_ms = int((time.time() - metrics.total_start) * 1000)

        response = self._build_instructor_response(
            query, parsed_query, results, limit, metrics, filter_result=filter_result
        )

        # Record Prometheus metrics
        record_search_metrics(
            total_latency_ms=metrics.total_latency_ms,
            stage_latencies={
                "parsing": metrics.parse_latency_ms,
                "embedding": metrics.embed_latency_ms,
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

        # Cache response (skip degraded responses to avoid "sticky" outages)
        if not metrics.degraded:
            self._cache_response(query, user_location, response, limit)

        return response

    async def _hydrate_instructor_results(
        self,
        ranked: List[RankedResult],
        limit: int,
        *,
        location_resolution: Optional["ResolvedLocation"] = None,
    ) -> List[NLSearchResultItem]:
        """
        Convert ranked service-level candidates into instructor-level results.

        Uses batch DB queries to avoid N+1:
        - instructor summaries (users + instructor_profiles)
        - ratings aggregates (reviews)
        - coverage areas (instructor_service_areas + region_boundaries)
        - service catalog mapping for selected instructor_services
        """
        if not ranked:
            return []

        # Determine instructor order by first occurrence (ranked list is already sorted by score).
        ordered_instructor_ids: List[str] = []
        seen_instructors: set[str] = set()
        for r in ranked:
            if r.instructor_id in seen_instructors:
                continue
            seen_instructors.add(r.instructor_id)
            ordered_instructor_ids.append(r.instructor_id)
            if len(ordered_instructor_ids) >= limit:
                break

        selected_instructors = set(ordered_instructor_ids)

        # Group services per instructor (keep all ranked services for match_count)
        by_instructor: Dict[str, List[RankedResult]] = {iid: [] for iid in ordered_instructor_ids}
        for r in ranked:
            if r.instructor_id in selected_instructors:
                by_instructor[r.instructor_id].append(r)

        # Pick best_match + other_matches by relevance_score (semantic match) per instructor.
        chosen_by_instructor: Dict[str, List[RankedResult]] = {}
        for instructor_id in ordered_instructor_ids:
            services = sorted(
                by_instructor[instructor_id], key=lambda x: x.relevance_score, reverse=True
            )
            chosen = services[:4]  # best + up to 3 others
            if not chosen:
                continue
            chosen_by_instructor[instructor_id] = chosen

        instructor_cards_task = asyncio.to_thread(
            self.retriever_repository.get_instructor_cards, ordered_instructor_ids
        )

        # Optional distance map (meters) for admin debugging when we have a location reference.
        distance_region_id: Optional[str] = None
        if location_resolution and location_resolution.region_id:
            distance_region_id = str(location_resolution.region_id)
        elif (
            location_resolution
            and location_resolution.requires_clarification
            and location_resolution.candidates
        ):
            # Best-effort: pick the shortest-named candidate as a stable reference for display.
            try:
                chosen_candidate = min(
                    location_resolution.candidates,
                    key=lambda c: len(str(c.get("region_name") or "")),
                )
                distance_region_id = str(chosen_candidate.get("region_id") or "") or None
            except Exception:
                distance_region_id = None

        distance_task = None
        if distance_region_id:
            distance_task = asyncio.to_thread(
                self.filter_service.repository.get_instructor_min_distance_to_region,
                ordered_instructor_ids,
                distance_region_id,
            )

        if distance_task is not None:
            instructor_rows, distance_meters = await asyncio.gather(
                instructor_cards_task, distance_task
            )
        else:
            instructor_rows = await instructor_cards_task
            distance_meters = {}
        instructor_by_id: Dict[str, Dict[str, Any]] = {
            row["instructor_id"]: row for row in instructor_rows
        }

        results: List[NLSearchResultItem] = []
        for instructor_id in ordered_instructor_ids:
            chosen_for_instructor = chosen_by_instructor.get(instructor_id)
            profile = instructor_by_id.get(instructor_id)
            if not chosen_for_instructor or not profile:
                continue

            best_ranked = chosen_for_instructor[0]

            instructor = InstructorSummary(
                id=instructor_id,
                first_name=profile["first_name"],
                last_initial=profile.get("last_initial") or "",
                profile_picture_url=self._build_photo_url(profile.get("profile_picture_key")),
                bio_snippet=profile.get("bio_snippet"),
                verified=bool(profile.get("verified", False)),
                years_experience=profile.get("years_experience"),
            )

            rating_summary = RatingSummary(
                average=round(float(profile["avg_rating"]), 2)
                if profile.get("avg_rating")
                else None,
                count=int(profile.get("review_count", 0) or 0),
            )

            best_match = ServiceMatch(
                service_id=best_ranked.service_id,
                service_catalog_id=best_ranked.service_catalog_id,
                name=best_ranked.name,
                description=best_ranked.description,
                price_per_hour=int(best_ranked.price_per_hour),
                relevance_score=round(float(best_ranked.relevance_score), 3),
            )

            other_matches: List[ServiceMatch] = []
            for other_ranked in chosen_for_instructor[1:]:
                other_matches.append(
                    ServiceMatch(
                        service_id=other_ranked.service_id,
                        service_catalog_id=other_ranked.service_catalog_id,
                        name=other_ranked.name,
                        description=other_ranked.description,
                        price_per_hour=int(other_ranked.price_per_hour),
                        relevance_score=round(float(other_ranked.relevance_score), 3),
                    )
                )

            results.append(
                NLSearchResultItem(
                    instructor_id=instructor_id,
                    instructor=instructor,
                    rating=rating_summary,
                    coverage_areas=profile.get("coverage_areas", []) or [],
                    best_match=best_match,
                    other_matches=other_matches,
                    total_matching_services=len(by_instructor.get(instructor_id, [])) or 1,
                    relevance_score=best_match.relevance_score,
                    distance_km=round(float(distance_meters[instructor_id]) / 1000.0, 1)
                    if distance_meters.get(instructor_id) is not None
                    else None,
                    distance_mi=round(float(distance_meters[instructor_id]) / 1609.34, 1)
                    if distance_meters.get(instructor_id) is not None
                    else None,
                )
            )

        return results

    def _check_cache(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        """Check for cached response."""
        try:
            result: Optional[Dict[str, Any]] = self.search_cache.get_cached_response(
                query,
                user_location,
                limit=limit,
                region_code=self._region_code,
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
            cached_parsed = self.search_cache.get_cached_parsed_query(
                query, region_code=self._region_code
            )
            if cached_parsed:
                metrics.parse_latency_ms = int((time.time() - start) * 1000)
                return cached_parsed

            # Parse with hybrid approach
            parsed = await hybrid_parse(query, self.db, user_id, region_code=self._region_code)

            # Cache the parsed query
            self.search_cache.cache_parsed_query(query, parsed, region_code=self._region_code)

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

        total_ms = int((time.time() - start) * 1000)
        metrics.embed_latency_ms = int(getattr(result, "embed_latency_ms", 0) or 0)
        metrics.retrieve_latency_ms = int(getattr(result, "db_latency_ms", 0) or 0) or max(
            0, total_ms - metrics.embed_latency_ms
        )
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
                        service_catalog_id=c.service_catalog_id,
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
                        service_catalog_id=c.service_catalog_id,
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
                region_code=self._region_code,
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
            match_count = len(services)

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
                    total_matching_services=match_count,
                    relevance_score=best_match.relevance_score,
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
        *,
        filter_result: Optional[FilterResult] = None,
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
        location_resolution = filter_result.location_resolution if filter_result else None
        location_not_found = bool(getattr(location_resolution, "not_found", False))

        location_resolved = self._format_location_resolved(location_resolution)

        soft_filter_message: Optional[str] = None
        if filter_result and filter_result.soft_filtering_used:
            soft_filter_message = self._generate_soft_filter_message(
                parsed_query,
                filter_result.filter_stats,
                location_resolution,
                location_resolved,
            )

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
            filters_applied=filter_result.filters_applied if filter_result else [],
            soft_filtering_used=filter_result.soft_filtering_used if filter_result else False,
            filter_stats=filter_result.filter_stats if filter_result else None,
            soft_filter_message=soft_filter_message,
            location_resolved=location_resolved,
            location_not_found=location_not_found,
        )

        return NLSearchResponse(results=results[:limit], meta=meta)

    def _format_location_resolved(
        self, location_resolution: Optional["ResolvedLocation"]
    ) -> Optional[str]:
        """Format a human-friendly resolved location string for UI/debug."""
        if not location_resolution:
            return None

        if location_resolution.resolved:
            return location_resolution.region_name or location_resolution.borough

        if not (location_resolution.requires_clarification and location_resolution.candidates):
            return None

        candidate_names: List[str] = []
        for candidate in location_resolution.candidates:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("region_name")
            if name is None:
                continue
            text = str(name).strip()
            if text:
                candidate_names.append(text)

        if not candidate_names:
            return None

        # De-dupe while preserving order for stable display.
        seen: set[str] = set()
        unique_names: List[str] = []
        for name in candidate_names:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_names.append(name)

        def _split(name: str) -> tuple[str, str]:
            if "-" in name:
                base, suffix = name.split("-", 1)
                return base.strip(), suffix.strip()
            if " (" in name and name.endswith(")"):
                base, rest = name.split(" (", 1)
                return base.strip(), rest[:-1].strip()
            return "", ""

        split_parts = [_split(name) for name in unique_names]
        prefixes = {p for p, s in split_parts if p and s}
        if prefixes and len(prefixes) == 1 and all(s for _, s in split_parts):
            prefix = next(iter(prefixes))
            suffixes = sorted({s for _, s in split_parts}, key=lambda s: s.lower())
            return f"{prefix} ({', '.join(suffixes)})"

        return ", ".join(unique_names[:5])

    def _generate_soft_filter_message(
        self,
        parsed: ParsedQuery,
        filter_stats: Dict[str, int],
        location_resolution: Optional["ResolvedLocation"],
        location_resolved: Optional[str],
    ) -> Optional[str]:
        """Generate a user-facing message when soft filtering/relaxation is used."""
        messages: List[str] = []

        # Location constraint
        if parsed.location_text:
            if location_resolution and location_resolution.not_found:
                messages.append(f"Couldn't find location '{parsed.location_text}'")
            elif filter_stats.get("after_location") == 0:
                messages.append(
                    f"No instructors found in {location_resolved or parsed.location_text}"
                )

        # Availability constraint
        if (parsed.date or parsed.time_after) and filter_stats.get("after_availability") == 0:
            if parsed.date:
                messages.append(f"No availability on {parsed.date.strftime('%A, %b %d')}")
            else:
                messages.append("No availability matching your time constraints")

        # Price constraint
        if parsed.max_price is not None and filter_stats.get("after_price") == 0:
            messages.append(f"No instructors under ${parsed.max_price}")

        if not messages:
            return None

        location_related = any(
            m.startswith("No instructors found in") or m.startswith("Couldn't find location")
            for m in messages
        )
        suffix = (
            "Showing results from nearby areas."
            if location_related
            else "Showing available instructors."
        )
        return f"{'. '.join(messages)}. {suffix}"

    def _build_photo_url(self, key: Optional[str]) -> Optional[str]:
        """Build Cloudflare R2 URL for profile photo."""
        if not key:
            return None
        # Use R2 assets domain from settings
        assets_domain = getattr(settings, "r2_public_url", "https://assets.instainstru.com")
        return f"{assets_domain}/{key}"
