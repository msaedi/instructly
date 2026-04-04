"""Parsing-specific service helpers for the preflight pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from app import database as database_module
from app.services.search import llm_parser as llm_parser_module, query_parser as query_parser_module
from app.services.search.nl_pipeline.protocols import SearchServiceLike

if TYPE_CHECKING:
    from app.services.search.nl_pipeline.models import SearchMetrics
    from app.services.search.query_parser import ParsedQuery

logger = logging.getLogger(__name__)


async def _cache_parsed_query_safe(
    service: SearchServiceLike, query: str, parsed_query: ParsedQuery
) -> None:
    try:
        await service.search_cache.cache_parsed_query(
            query,
            parsed_query,
            region_code=service._region_code,
        )
    except Exception as exc:
        logger.warning("Failed to cache parsed query: %s", exc)


async def _run_llm_parse_for_service(
    service: SearchServiceLike,
    *,
    query: str,
    parsed_query: ParsedQuery,
    user_id: Optional[str],
    metrics: SearchMetrics,
) -> ParsedQuery:
    llm_start = time.perf_counter()
    llm_parser = llm_parser_module.LLMParser(user_id=user_id, region_code=service._region_code)
    parsed_query = await llm_parser.parse(query, parsed_query)
    metrics.parse_latency_ms += int((time.perf_counter() - llm_start) * 1000)
    if parsed_query.parsing_mode != "llm":
        metrics.degraded = True
        metrics.degradation_reasons.append("parsing_error")
    await _cache_parsed_query_safe(service, query, parsed_query)
    return parsed_query


async def parse_query(
    service: SearchServiceLike,
    query: str,
    metrics: SearchMetrics,
    user_id: Optional[str] = None,
) -> ParsedQuery:
    start = time.time()
    try:
        cached_parsed = await service.search_cache.get_cached_parsed_query(
            query,
            region_code=service._region_code,
        )
        if cached_parsed:
            metrics.parse_latency_ms = int((time.time() - start) * 1000)
            return cached_parsed
        parsed = await llm_parser_module.hybrid_parse(
            query,
            user_id=user_id,
            region_code=service._region_code,
        )
        await service.search_cache.cache_parsed_query(
            query,
            parsed,
            region_code=service._region_code,
        )
    except Exception as exc:
        logger.error("Parsing failed, using basic extraction: %s", exc)

        def _parse_regex_fallback() -> ParsedQuery:
            with database_module.get_db_session() as db:
                parser = query_parser_module.QueryParser(
                    db,
                    user_id=user_id,
                    region_code=service._region_code,
                )
                return parser.parse(query)

        parsed = await asyncio.to_thread(_parse_regex_fallback)
        metrics.degraded = True
        metrics.degradation_reasons.append("parsing_error")
    metrics.parse_latency_ms = int((time.time() - start) * 1000)
    return parsed
