"""Core preflight helpers for parse, filters, and the first DB burst."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import TYPE_CHECKING, AbstractSet, Callable, Dict, List, Literal, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.search import retriever as retriever_module
from app.services.search.config import SearchConfig
from app.services.search.nl_pipeline.models import (
    ParseAndTextSearchResult,
    PreLocationTiersResult,
    PreOpenAIData,
)
from app.services.search.nl_pipeline.protocols import AsyncioLike, DBSessionFactory, LoggerLike

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import (
        CachedAliasInfo,
        RegionLookup,
        SearchBatchRepository,
    )
    from app.services.search.embedding_service import EmbeddingService
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.query_parser import ParsedQuery, QueryParser


def coerce_skill_level_override(
    value: str,
) -> Literal["beginner", "intermediate", "advanced"] | None:
    """Return a typed skill-level literal for validated override values."""
    if value == "beginner":
        return "beginner"
    if value == "intermediate":
        return "intermediate"
    if value == "advanced":
        return "advanced"
    return None


def normalize_filter_values(values: Optional[List[str]]) -> List[str]:
    """Normalize multi-select filter values for stable filtering/cache keys."""
    if not values:
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def normalize_taxonomy_filter_selections(
    selections: Optional[Dict[str, List[str]]],
) -> Dict[str, List[str]]:
    """Normalize taxonomy filters to deterministic key/value payloads."""
    normalized: Dict[str, List[str]] = {}
    for raw_key, raw_values in (selections or {}).items():
        key = str(raw_key).strip().lower()
        if not key:
            continue
        values = normalize_filter_values(raw_values)
        if values:
            normalized[key] = values
    return normalized


def build_cache_filters(
    taxonomy_filters: Dict[str, List[str]],
    *,
    subcategory_id: Optional[str],
) -> Optional[Dict[str, object]]:
    """Build cache-key filter payload to avoid filtered/unfiltered collisions."""
    payload: Dict[str, object] = {}
    if subcategory_id:
        payload["subcategory_id"] = str(subcategory_id).strip()
    if taxonomy_filters:
        payload["taxonomy"] = {
            key: list(values)
            for key, values in sorted(taxonomy_filters.items(), key=lambda item: item[0])
        }
    return payload or None


def compute_text_match_flags(
    service_query: str,
    text_results: Dict[str, Tuple[float, Dict[str, object]]],
    *,
    trigram_generic_tokens: Optional[AbstractSet[str]] = None,
    require_text_match_score_threshold: Optional[float] = None,
    skip_vector_min_results: Optional[int] = None,
    skip_vector_score_threshold: Optional[float] = None,
) -> tuple[float, bool, bool]:
    trigram_generic_tokens = trigram_generic_tokens or retriever_module.TRIGRAM_GENERIC_TOKENS
    require_text_match_score_threshold = (
        require_text_match_score_threshold
        if require_text_match_score_threshold is not None
        else retriever_module.TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD
    )
    skip_vector_min_results = (
        skip_vector_min_results
        if skip_vector_min_results is not None
        else retriever_module.TEXT_SKIP_VECTOR_MIN_RESULTS
    )
    skip_vector_score_threshold = (
        skip_vector_score_threshold
        if skip_vector_score_threshold is not None
        else retriever_module.TEXT_SKIP_VECTOR_SCORE_THRESHOLD
    )
    best_text_score = max((score for score, _ in text_results.values()), default=0.0)
    raw_tokens = [token for token in str(service_query or "").strip().split() if token]
    non_generic_tokens = [
        token for token in raw_tokens if token.lower() not in trigram_generic_tokens
    ]
    require_text_match = (
        bool(text_results)
        and (0 < len(non_generic_tokens) <= 2)
        and best_text_score >= require_text_match_score_threshold
    )
    skip_vector = (
        len(text_results) >= skip_vector_min_results
        and best_text_score >= skip_vector_score_threshold
    )
    return best_text_score, require_text_match, skip_vector


async def embed_query_with_timeout(
    query: str,
    *,
    asyncio_module: AsyncioLike,
    embedding_service: EmbeddingService,
    get_config: Callable[[], SearchConfig],
    embedding_soft_timeout_ms: int,
) -> tuple[Optional[List[float]], int, Optional[str]]:
    embed_start = time.perf_counter()
    degradation_reason: Optional[str] = None
    embedding: Optional[List[float]] = None
    try:
        config_timeout_ms = max(0, int(get_config().embedding_timeout_ms))
        soft_timeout_ms = max(0, int(embedding_soft_timeout_ms))
        timeout_ms = (
            min(config_timeout_ms, soft_timeout_ms) if soft_timeout_ms else config_timeout_ms
        )
        timeout_s = (timeout_ms / 1000.0) if timeout_ms else None
        if timeout_s:
            embedding = await asyncio_module.wait_for(
                embedding_service.embed_query(query),
                timeout=timeout_s,
            )
        else:
            embedding = await embedding_service.embed_query(query)
    except asyncio.TimeoutError:
        degradation_reason = "embedding_timeout"
        embedding = None
    if embedding is None and degradation_reason is None:
        degradation_reason = "embedding_service_unavailable"
    embed_latency_ms = int((time.perf_counter() - embed_start) * 1000)
    return embedding, embed_latency_ms, degradation_reason


def execute_parse_and_text_search(
    *,
    batch: SearchBatchRepository,
    db: Session,
    query: str,
    parsed_query: Optional[ParsedQuery],
    user_id: Optional[str],
    region_code: str,
    query_parser_cls: type[QueryParser],
    notify_parsed: Optional[Callable[[ParsedQuery], None]],
    trigram_generic_tokens: AbstractSet[str],
    require_text_match_score_threshold: float,
    skip_vector_min_results: int,
    skip_vector_score_threshold: float,
    text_top_k: int,
    max_candidates: int,
    logger: LoggerLike,
) -> ParseAndTextSearchResult:
    parse_latency_ms = 0
    if parsed_query is None:
        parse_start = time.perf_counter()
        parser = query_parser_cls(db, user_id=user_id, region_code=region_code)
        parsed_query = parser.parse(query)
        parse_latency_ms = int((time.perf_counter() - parse_start) * 1000)
    if notify_parsed and parsed_query is not None:
        try:
            notify_parsed(parsed_query)
        except Exception as exc:  # pragma: no cover - compatibility logging only
            logger.debug("Failed to notify parsed query: %s", exc)
    has_service_embeddings = batch.has_service_embeddings()
    text_results: Optional[Dict[str, Tuple[float, Dict[str, object]]]] = None
    text_latency_ms = 0
    best_text_score = 0.0
    require_text_match = False
    skip_vector = False
    if not parsed_query.needs_llm:
        text_query = retriever_module.normalize_query_for_trigram(parsed_query.service_query)
        text_start = time.perf_counter()
        text_results = batch.text_search(
            text_query, text_query, limit=min(text_top_k, max_candidates)
        )
        text_latency_ms = int((time.perf_counter() - text_start) * 1000)
        best_text_score, require_text_match, skip_vector = compute_text_match_flags(
            parsed_query.service_query,
            text_results,
            trigram_generic_tokens=trigram_generic_tokens,
            require_text_match_score_threshold=require_text_match_score_threshold,
            skip_vector_min_results=skip_vector_min_results,
            skip_vector_score_threshold=skip_vector_score_threshold,
        )
    return ParseAndTextSearchResult(
        parsed_query=parsed_query,
        parse_latency_ms=parse_latency_ms,
        has_service_embeddings=has_service_embeddings,
        text_results=text_results,
        text_latency_ms=text_latency_ms,
        best_text_score=best_text_score,
        require_text_match=require_text_match,
        skip_vector=skip_vector,
    )


def resolve_pre_location_tiers(
    *,
    batch: SearchBatchRepository,
    db: Session,
    parsed_query: ParsedQuery,
    user_location: Optional[Tuple[float, float]],
    region_code: str,
    location_resolver_cls: type[LocationResolver],
    normalize_location_text: Callable[[str], str],
    resolve_cached_alias: Callable[[CachedAliasInfo, RegionLookup], Optional[ResolvedLocation]],
    location_llm_top_k: int,
) -> PreLocationTiersResult:
    region_lookup: Optional[RegionLookup] = None
    location_resolution: Optional[ResolvedLocation] = None
    location_normalized: Optional[str] = None
    cached_alias_normalized: Optional[str] = None
    fuzzy_score: Optional[float] = None
    location_llm_candidates: List[str] = []
    should_load_regions = bool(parsed_query.needs_llm or parsed_query.location_text)
    if should_load_regions:
        region_lookup = batch.load_region_lookup()
    if not (
        region_lookup
        and parsed_query.location_text
        and parsed_query.location_type != "near_me"
        and user_location is None
        and not parsed_query.needs_llm
    ):
        return PreLocationTiersResult(
            region_lookup=region_lookup,
            location_resolution=location_resolution,
            location_normalized=location_normalized,
            cached_alias_normalized=cached_alias_normalized,
            fuzzy_score=fuzzy_score,
            location_llm_candidates=location_llm_candidates,
        )
    location_normalized = normalize_location_text(parsed_query.location_text)
    if "region_lookup" in inspect.signature(location_resolver_cls).parameters:
        resolver = location_resolver_cls(db, region_code=region_code, region_lookup=region_lookup)
    else:
        resolver = location_resolver_cls(db, region_code=region_code)
    non_semantic = resolver.resolve_sync(
        parsed_query.location_text,
        original_query=parsed_query.original_query,
        track_unresolved=False,
    )
    if non_semantic.resolved or non_semantic.requires_clarification:
        location_resolution = non_semantic
    else:
        cached_alias = batch.get_cached_llm_alias(location_normalized)
        if cached_alias:
            location_resolution = resolve_cached_alias(cached_alias, region_lookup)
            if location_resolution:
                cached_alias_normalized = location_normalized
    if location_resolution is None and location_normalized:
        fuzzy_score = batch.get_best_fuzzy_score(location_normalized)
    if location_resolution is None and location_normalized:
        location_llm_candidates = batch.get_fuzzy_candidate_names(
            location_normalized,
            limit=location_llm_top_k,
        )
        if (
            fuzzy_score is not None
            and fuzzy_score < resolver.MIN_FUZZY_FOR_EMBEDDING
            and region_lookup.region_names
        ):
            location_llm_candidates = list(region_lookup.region_names)
    return PreLocationTiersResult(
        region_lookup=region_lookup,
        location_resolution=location_resolution,
        location_normalized=location_normalized,
        cached_alias_normalized=cached_alias_normalized,
        fuzzy_score=fuzzy_score,
        location_llm_candidates=location_llm_candidates,
    )


def assemble_pre_openai_data(
    *,
    parsed_query: ParsedQuery,
    parse_latency_ms: int,
    text_results: Optional[Dict[str, Tuple[float, Dict[str, object]]]],
    text_latency_ms: int,
    has_service_embeddings: bool,
    best_text_score: float,
    require_text_match: bool,
    skip_vector: bool,
    region_lookup: Optional[RegionLookup],
    location_resolution: Optional[ResolvedLocation],
    location_normalized: Optional[str],
    cached_alias_normalized: Optional[str],
    fuzzy_score: Optional[float],
    location_llm_candidates: List[str],
) -> PreOpenAIData:
    return PreOpenAIData(
        parsed_query=parsed_query,
        parse_latency_ms=parse_latency_ms,
        text_results=text_results,
        text_latency_ms=text_latency_ms,
        has_service_embeddings=has_service_embeddings,
        best_text_score=best_text_score,
        require_text_match=require_text_match,
        skip_vector=skip_vector,
        region_lookup=region_lookup,
        location_resolution=location_resolution,
        location_normalized=location_normalized,
        cached_alias_normalized=cached_alias_normalized,
        fuzzy_score=fuzzy_score,
        location_llm_candidates=location_llm_candidates,
    )


def run_pre_openai_burst(
    *,
    get_db_session: DBSessionFactory,
    search_batch_repository_cls: type[SearchBatchRepository],
    query: str,
    parsed_query: Optional[ParsedQuery],
    user_id: Optional[str],
    user_location: Optional[Tuple[float, float]],
    notify_parsed: Optional[Callable[[ParsedQuery], None]],
    region_code: str,
    query_parser_cls: type[QueryParser],
    location_resolver_cls: type[LocationResolver],
    normalize_location_text: Callable[[str], str],
    resolve_cached_alias: Callable[[CachedAliasInfo, RegionLookup], Optional[ResolvedLocation]],
    location_llm_top_k: int,
    trigram_generic_tokens: AbstractSet[str],
    require_text_match_score_threshold: float,
    skip_vector_min_results: int,
    skip_vector_score_threshold: float,
    text_top_k: int,
    max_candidates: int,
    logger: LoggerLike,
) -> PreOpenAIData:
    with get_db_session() as db:
        batch = search_batch_repository_cls(db, region_code=region_code)
        parsed_result = execute_parse_and_text_search(
            batch=batch,
            db=db,
            query=query,
            parsed_query=parsed_query,
            user_id=user_id,
            region_code=region_code,
            query_parser_cls=query_parser_cls,
            notify_parsed=notify_parsed,
            trigram_generic_tokens=trigram_generic_tokens,
            require_text_match_score_threshold=require_text_match_score_threshold,
            skip_vector_min_results=skip_vector_min_results,
            skip_vector_score_threshold=skip_vector_score_threshold,
            text_top_k=text_top_k,
            max_candidates=max_candidates,
            logger=logger,
        )
        location_result = resolve_pre_location_tiers(
            batch=batch,
            db=db,
            parsed_query=parsed_result.parsed_query,
            user_location=user_location,
            region_code=region_code,
            location_resolver_cls=location_resolver_cls,
            normalize_location_text=normalize_location_text,
            resolve_cached_alias=resolve_cached_alias,
            location_llm_top_k=location_llm_top_k,
        )
        return assemble_pre_openai_data(
            parsed_query=parsed_result.parsed_query,
            parse_latency_ms=parsed_result.parse_latency_ms,
            has_service_embeddings=parsed_result.has_service_embeddings,
            text_results=parsed_result.text_results,
            text_latency_ms=parsed_result.text_latency_ms,
            best_text_score=parsed_result.best_text_score,
            require_text_match=parsed_result.require_text_match,
            skip_vector=parsed_result.skip_vector,
            region_lookup=location_result.region_lookup,
            location_resolution=location_result.location_resolution,
            location_normalized=location_result.location_normalized,
            cached_alias_normalized=location_result.cached_alias_normalized,
            fuzzy_score=location_result.fuzzy_score,
            location_llm_candidates=location_result.location_llm_candidates,
        )


def prepare_search_filters(
    *,
    explicit_skill_levels: Optional[List[str]],
    taxonomy_filter_selections: Optional[Dict[str, List[str]]],
    subcategory_id: Optional[str],
) -> tuple[Dict[str, List[str]], List[str], Optional[Dict[str, object]]]:
    normalized_explicit_skills = normalize_filter_values(explicit_skill_levels)
    effective_taxonomy_filters = normalize_taxonomy_filter_selections(taxonomy_filter_selections)
    if normalized_explicit_skills:
        effective_taxonomy_filters["skill_level"] = normalized_explicit_skills
    effective_skill_levels = effective_taxonomy_filters.get("skill_level", [])
    cache_filters = build_cache_filters(
        effective_taxonomy_filters,
        subcategory_id=subcategory_id,
    )
    return effective_taxonomy_filters, effective_skill_levels, cache_filters
