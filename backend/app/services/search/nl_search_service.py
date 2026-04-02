# backend/app/services/search/nl_search_service.py
"""Main NL search service facade."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from app.core.exceptions import raise_503_if_pool_exhaustion
from app.schemas.nl_search import NLSearchResponse
from app.services.search.embedding_service import EmbeddingService
from app.services.search.filter_service import FilterService
from app.services.search.location_embedding_service import LocationEmbeddingService
from app.services.search.location_llm_service import LocationLLMService
from app.services.search.nl_pipeline import (
    hydration,
    location,
    postflight,
    preflight,
    response,
    runtime,
)
from app.services.search.nl_pipeline.models import PipelineTimer, SearchMetrics
from app.services.search.ranking_service import RankingService
from app.services.search.retriever import PostgresRetriever
from app.services.search.search_cache import SearchCacheService

if TYPE_CHECKING:
    from app.services.cache_service import CacheService


class NLSearchService:
    """Public NL search service entrypoint."""

    def __init__(
        self,
        cache_service: Optional["CacheService"] = None,
        search_cache: Optional[SearchCacheService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        retriever: Optional[PostgresRetriever] = None,
        filter_service: Optional[FilterService] = None,
        ranking_service: Optional[RankingService] = None,
        region_code: str = "nyc",
    ) -> None:
        self._cache_service = cache_service
        self._region_code = region_code
        self.search_cache = search_cache or SearchCacheService(
            cache_service=cache_service,
            region_code=region_code,
        )
        self.embedding_service = embedding_service or EmbeddingService(cache_service=cache_service)
        self.retriever = retriever or PostgresRetriever(self.embedding_service)
        self.filter_service = filter_service or FilterService(region_code=region_code)
        self.ranking_service = ranking_service or RankingService()
        self.location_embedding_service = LocationEmbeddingService(repository=None)
        self.location_llm_service = LocationLLMService()

    async def search(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]] = None,
        limit: int = 20,
        user_id: Optional[str] = None,
        requester_timezone: Optional[str] = None,
        budget_ms: Optional[int] = None,
        *,
        explicit_skill_levels: Optional[List[str]] = None,
        subcategory_id: Optional[str] = None,
        taxonomy_filter_selections: Optional[Dict[str, List[str]]] = None,
        include_diagnostics: bool = False,
        force_skip_tier5: bool = False,
        force_skip_tier4: bool = False,
        force_skip_vector: bool = False,
        force_skip_embedding: bool = False,
        force_high_load: bool = False,
    ) -> NLSearchResponse:
        perf_start = time.perf_counter()
        metrics = SearchMetrics(total_start=time.time())
        timer = PipelineTimer() if include_diagnostics else None
        candidates_flow = response.build_candidates_flow(include_diagnostics)
        effective_filters, effective_skill_levels, cache_filters = preflight.prepare_search_filters(
            explicit_skill_levels=explicit_skill_levels,
            taxonomy_filter_selections=taxonomy_filter_selections,
            subcategory_id=subcategory_id,
        )
        cached, cache_check_ms = await response.get_cached_search_response(
            self,
            query=query,
            user_location=user_location,
            limit=limit,
            timer=timer,
            cache_filters=cache_filters,
        )
        if cached:
            return response.build_cached_response(
                self,
                cached=cached,
                perf_start=perf_start,
                cache_check_ms=cache_check_ms,
                timer=timer,
                candidates_flow=candidates_flow,
                include_diagnostics=include_diagnostics,
            )

        inflight_incremented = False
        try:
            (
                budget,
                parsed_query_cached,
                parsed_query_future,
                notify_parsed,
                embedding_task,
            ) = await preflight.prepare_uncached_pipeline_for_service(
                self,
                query=query,
                budget_ms=budget_ms,
                force_high_load=force_high_load,
                force_skip_vector_search=force_skip_vector or force_skip_embedding,
            )
            inflight_incremented = True
            (
                pre_data,
                parsed_query,
                embedding_task,
                tier5_task,
                tier5_started_at,
            ) = await preflight.run_preflight_and_parse_for_service(
                self,
                query=query,
                user_id=user_id,
                user_location=user_location,
                parsed_query_cached=parsed_query_cached,
                parsed_query_future=parsed_query_future,
                notify_parsed=notify_parsed,
                embedding_task=embedding_task,
                budget=budget,
                effective_skill_levels=effective_skill_levels,
                metrics=metrics,
                timer=timer,
                candidates_flow=candidates_flow,
                force_skip_tier5=force_skip_tier5,
            )
            query_embedding, embedding_reason = await preflight.resolve_query_embedding_for_service(
                self,
                parsed_query=parsed_query,
                pre_data=pre_data,
                embedding_task=embedding_task,
                budget=budget,
                metrics=metrics,
                timer=timer,
                force_skip_vector=force_skip_vector,
                force_skip_embedding=force_skip_embedding,
            )
            (
                location_resolution,
                location_llm_cache,
                unresolved_info,
            ) = await location.resolve_location_stage_for_service(
                self,
                parsed_query=parsed_query,
                pre_data=pre_data,
                user_location=user_location,
                budget=budget,
                timer=timer,
                force_skip_tier5=force_skip_tier5,
                force_skip_tier4=force_skip_tier4,
                force_skip_embedding=force_skip_embedding,
                tier5_task=tier5_task,
                tier5_started_at=tier5_started_at,
            )
            post_data, retrieval_result = await postflight.run_postflight_stage_for_service(
                self,
                pre_data=pre_data,
                parsed_query=parsed_query,
                query_embedding=query_embedding,
                location_resolution=location_resolution,
                location_llm_cache=location_llm_cache,
                unresolved_info=unresolved_info,
                user_location=user_location,
                limit=limit,
                requester_timezone=requester_timezone,
                taxonomy_filter_selections=effective_filters,
                subcategory_id=subcategory_id,
                embedding_reason=embedding_reason,
                budget=budget,
                metrics=metrics,
                timer=timer,
                candidates_flow=candidates_flow,
            )
            results, hydrate_ms = await hydration.hydrate_results_for_service(
                self,
                post_data=post_data,
                limit=limit,
                metrics=metrics,
                timer=timer,
                candidates_flow=candidates_flow,
            )
            metrics.total_latency_ms = int((time.time() - metrics.total_start) * 1000)
            response_build_start = time.perf_counter()
            response_obj = response.build_instructor_response(
                query=query,
                parsed_query=parsed_query,
                results=results,
                limit=limit,
                metrics=metrics,
                filter_result=post_data.filter_result,
                inferred_filters=post_data.inferred_filters,
                effective_subcategory_id=post_data.effective_subcategory_id,
                effective_subcategory_name=post_data.effective_subcategory_name,
                available_content_filters=post_data.available_content_filters,
                budget=budget,
            )
            response_build_ms = int((time.perf_counter() - response_build_start) * 1000)
            if timer:
                timer.record_stage(
                    "build_response",
                    response_build_ms,
                    "success",
                    {"result_count": len(response_obj.results)},
                )
            cache_write_ms = await response.record_metrics_and_cache(
                self,
                query=query,
                user_location=user_location,
                limit=limit,
                parsed_query=parsed_query,
                response_obj=response_obj,
                metrics=metrics,
                cache_check_ms=cache_check_ms,
                hydrate_ms=hydrate_ms,
                response_build_ms=response_build_ms,
                cache_filters=cache_filters,
            )
            response.attach_diagnostics_and_perf_log(
                self,
                response_obj=response_obj,
                timer=timer,
                budget=budget,
                parsed_query=parsed_query,
                pre_data=pre_data,
                post_data=post_data,
                location_resolution=location_resolution,
                query_embedding=query_embedding,
                candidates_flow=candidates_flow,
                metrics=metrics,
                retrieval_result=retrieval_result,
                cache_check_ms=cache_check_ms,
                hydrate_ms=hydrate_ms,
                response_build_ms=response_build_ms,
                cache_write_ms=cache_write_ms,
                limit=limit,
                include_diagnostics=include_diagnostics,
            )
            return response_obj
        except Exception as exc:
            raise_503_if_pool_exhaustion(exc)
            raise
        finally:
            if inflight_incremented:
                await runtime._decrement_search_inflight()
