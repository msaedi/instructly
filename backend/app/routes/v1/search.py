# backend/app/routes/v1/search.py
"""
Search routes - API v1

Versioned search endpoints under /api/v1/search.
Provides natural language search functionality for finding instructors
and services using the SearchService.

Endpoints:
    GET /              → NL search with full pipeline (parsing, embedding, retrieval, ranking)
    GET /instructors   → Legacy search for instructors with natural language queries
    GET /health        → Health check for search components
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ...api.dependencies.auth import require_beta_phase_access
from ...api.dependencies.services import get_cache_service_dep
from ...database import get_db
from ...ratelimit.dependency import rate_limit
from ...schemas.nl_search import (
    ModelOption,
    NLSearchResponse,
    PopularQueriesResponse,
    PopularQueryItem,
    SearchClickResponse,
    SearchConfigResetResponse,
    SearchConfigResponse,
    SearchConfigUpdate,
    SearchHealthCache,
    SearchHealthComponents,
    SearchHealthResponse,
    SearchMetricsResponse,
    ZeroResultQueriesResponse,
    ZeroResultQueryItem,
)
from ...schemas.search_responses import InstructorSearchResponse
from ...services.cache_service import CacheService
from ...services.search.nl_search_service import NLSearchService
from ...services.search_service import SearchService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["search-v1"])


@router.get(
    "/instructors",
    response_model=InstructorSearchResponse,
    dependencies=[Depends(require_beta_phase_access()), Depends(rate_limit("read"))],
)
async def search_instructors(
    q: str = Query(..., description="Search query", min_length=1),
    limit: Optional[int] = Query(20, ge=1, le=100, description="Maximum results to return"),
    response: Response = None,
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> InstructorSearchResponse:
    """
    Search for instructors using natural language queries.

    Supports queries like:
    - "piano lessons under $50"
    - "math tutor near me"
    - "online yoga classes"
    - "SAT prep this weekend"

    Args:
        q: The search query string
        limit: Maximum number of results to return (1-100, default 20)
        response: FastAPI response object for setting headers
        db: Database session
        cache_service: Cache service for result caching

    Returns:
        Search results with instructors, services, and metadata
    """
    # Validate query
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    try:
        # Create search service instance with cache
        search_service = SearchService(db, cache_service=cache_service)

        # Perform search
        limit_value = int(limit if isinstance(limit, int) else 20)
        results = await asyncio.to_thread(search_service.search, q, limit_value)

        # Set Cache-Control header (60 seconds to match backend cache TTL)
        if response:
            response.headers["Cache-Control"] = "public, max-age=60"

        # Search recording is handled by frontend which has full context
        # (session ID, referrer, interaction type, etc.)
        # Backend focuses on returning search results efficiently
        # This ensures consistent behavior for both guests and authenticated users

        return InstructorSearchResponse(**results)

    except ValueError as e:
        # Handle invalid search parameters
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle unexpected errors
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get(
    "",
    response_model=NLSearchResponse,
    dependencies=[Depends(require_beta_phase_access()), Depends(rate_limit("search"))],
)
async def nl_search(
    q: str = Query(..., min_length=1, max_length=500, description="Natural language search query"),
    lat: Optional[float] = Query(None, ge=-90, le=90, description="User latitude"),
    lng: Optional[float] = Query(None, ge=-180, le=180, description="User longitude"),
    region: str = Query("nyc", description="Region code for location/price lookups"),
    limit: int = Query(20, ge=1, le=50, description="Maximum results to return"),
    response: Response = None,
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> NLSearchResponse:
    """
    Natural language search for instructors and services.

    Full pipeline search that combines:
    - Query parsing (regex + LLM)
    - Semantic embedding
    - Hybrid vector + text retrieval
    - Constraint filtering (price, location, availability)
    - Multi-signal ranking

    Supports queries like:
    - "piano lessons in brooklyn"
    - "cheap guitar lessons tomorrow"
    - "math tutoring for kids after 5pm"

    Args:
        q: Natural language search query
        lat: User latitude (optional, must provide with lng)
        lng: User longitude (optional, must provide with lat)
        region: Region code for location and price threshold lookups (default: nyc)
        limit: Maximum results to return (1-50, default 20)
        response: FastAPI response object for headers
        db: Database session
        cache_service: Cache service for result caching

    Returns:
        Search results with ranked instructors and full metadata
    """
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    # Validate location (both or neither)
    user_location: Optional[tuple[float, float]] = None
    if lat is not None and lng is not None:
        user_location = (lng, lat)  # Note: (lng, lat) order for PostGIS
    elif lat is not None or lng is not None:
        raise HTTPException(
            status_code=400,
            detail="Both lat and lng must be provided together",
        )

    try:
        service = NLSearchService(db, cache_service=cache_service, region_code=region)
        result = await service.search(
            query=q,
            user_location=user_location,
            limit=limit,
        )

        # Set Cache-Control header
        if response:
            cache_ttl = 60 if not result.meta.cache_hit else 300
            response.headers["Cache-Control"] = f"public, max-age={cache_ttl}"

        # Log search for analytics (non-blocking, don't fail search on logging error)
        try:
            if not result.meta.cache_hit:
                analytics_repo = SearchAnalyticsRepository(db)
                # Build normalized query from parsed info
                parsed = result.meta.parsed
                normalized_query = {
                    "service_query": parsed.service_query,
                    "location": parsed.location,
                    "max_price": parsed.max_price,
                    "date": parsed.date,
                    "time_after": parsed.time_after,
                    "audience_hint": parsed.audience_hint,
                    "skill_level": parsed.skill_level,
                    "urgency": parsed.urgency,
                }
                top_result_ids = [r.service_id for r in result.results[:10]]

                search_query_id = await asyncio.to_thread(
                    lambda: analytics_repo.nl_log_search_query(
                        original_query=q,
                        normalized_query=normalized_query,
                        parsing_mode=result.meta.parsing_mode,
                        parsing_latency_ms=0,  # Not tracked separately in response
                        result_count=result.meta.total_results,
                        top_result_ids=top_result_ids,
                        total_latency_ms=result.meta.latency_ms,
                        cache_hit=result.meta.cache_hit,
                        degraded=result.meta.degraded,
                    )
                )
                # Update result with search_query_id for click tracking
                result.meta.search_query_id = search_query_id
        except Exception as log_err:
            logger.warning(f"Failed to log search analytics: {log_err}")

        return result

    except Exception as e:
        logger.error(f"NL search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Search temporarily unavailable",
        )


@router.get("/health", response_model=SearchHealthResponse)
async def search_health(db: Session = Depends(get_db)) -> SearchHealthResponse:
    """
    Health check for search service components.

    Returns status of:
    - Cache service availability
    - Parsing circuit breaker state
    - Embedding circuit breaker state

    Returns:
        Health status with component details
    """
    from ...services.search.circuit_breaker import EMBEDDING_CIRCUIT, PARSING_CIRCUIT
    from ...services.search.search_cache import SearchCacheService

    cache = SearchCacheService()
    cache_stats = cache.get_cache_stats()

    return SearchHealthResponse(
        status="healthy",
        components=SearchHealthComponents(
            cache=SearchHealthCache(
                available=cache_stats.get("available", False),
                response_cache_version=cache_stats.get("response_cache_version"),
                ttls=cache_stats.get("ttls"),
                error=cache_stats.get("error"),
            ),
            parsing_circuit=PARSING_CIRCUIT.state.value,
            embedding_circuit=EMBEDDING_CIRCUIT.state.value,
        ),
    )


# ===== Analytics Endpoints =====


@router.get("/analytics/metrics", response_model=SearchMetricsResponse)
async def search_metrics(
    days: int = Query(1, ge=1, le=30, description="Number of days to analyze"),
    db: Session = Depends(get_db),
) -> SearchMetricsResponse:
    """
    Get aggregate search metrics for the last N days.

    Returns metrics including:
    - Total searches
    - Average latency (p50, p95)
    - Average results per search
    - Zero result rate
    - Cache hit rate
    - Degradation rate
    """
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    repo = SearchAnalyticsRepository(db)
    metrics = repo.nl_get_search_metrics(days)
    return SearchMetricsResponse(**metrics)


@router.get("/analytics/popular", response_model=PopularQueriesResponse)
async def popular_queries(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    limit: int = Query(50, ge=1, le=200, description="Maximum queries to return"),
    db: Session = Depends(get_db),
) -> PopularQueriesResponse:
    """Get most popular search queries."""
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    repo = SearchAnalyticsRepository(db)
    rows = repo.nl_get_popular_queries(days, limit)
    queries = [PopularQueryItem(**row) for row in rows]
    return PopularQueriesResponse(queries=queries)


@router.get("/analytics/zero-results", response_model=ZeroResultQueriesResponse)
async def zero_result_queries(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    limit: int = Query(100, ge=1, le=500, description="Maximum queries to return"),
    db: Session = Depends(get_db),
) -> ZeroResultQueriesResponse:
    """Get queries that returned zero results."""
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    repo = SearchAnalyticsRepository(db)
    rows = repo.nl_get_zero_result_queries(days, limit)
    queries = [ZeroResultQueryItem(**row) for row in rows]
    return ZeroResultQueriesResponse(queries=queries)


@router.post("/click", response_model=SearchClickResponse)
async def log_search_click(
    search_query_id: str = Query(..., description="Search query ID from NL search"),
    service_id: str = Query(..., description="Service ID that was clicked"),
    instructor_id: str = Query(..., description="Instructor ID that was clicked"),
    position: int = Query(..., ge=1, description="Position in search results (1-indexed)"),
    action: str = Query("view", description="Action type: view, book, message, favorite"),
    db: Session = Depends(get_db),
) -> SearchClickResponse:
    """
    Log a click on a search result for conversion tracking.

    Call this endpoint when a user interacts with a search result.
    """
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    repo = SearchAnalyticsRepository(db)
    click_id = repo.nl_log_search_click(
        search_query_id=search_query_id,
        service_id=service_id,
        instructor_id=instructor_id,
        position=position,
        action=action,
    )
    return SearchClickResponse(click_id=click_id)


# ===== Configuration Endpoints =====


@router.get("/config", response_model=SearchConfigResponse)
async def get_config() -> SearchConfigResponse:
    """
    Get current NL search configuration.

    Returns the currently active models and timeouts along with
    available options for the admin UI.
    """
    from ...services.search.config import (
        AVAILABLE_EMBEDDING_MODELS,
        AVAILABLE_PARSING_MODELS,
        get_search_config,
    )

    config = get_search_config()
    return SearchConfigResponse(
        parsing_model=config.parsing_model,
        parsing_timeout_ms=config.parsing_timeout_ms,
        embedding_model=config.embedding_model,
        embedding_timeout_ms=config.embedding_timeout_ms,
        available_parsing_models=[ModelOption(**m) for m in AVAILABLE_PARSING_MODELS],
        available_embedding_models=[ModelOption(**m) for m in AVAILABLE_EMBEDDING_MODELS],
    )


@router.put("/config", response_model=SearchConfigResponse)
async def update_config(update: SearchConfigUpdate) -> SearchConfigResponse:
    """
    Update NL search configuration at runtime.

    Changes are temporary (not persisted to environment).
    Useful for testing different models without redeployment.
    Server restart will revert to environment defaults.

    Note: Embedding model cannot be changed at runtime as it requires
    re-generating all embeddings in the database.
    """
    from ...services.search.config import (
        AVAILABLE_EMBEDDING_MODELS,
        AVAILABLE_PARSING_MODELS,
        update_search_config,
    )

    # Prevent embedding model changes at runtime
    # Changing requires re-running embedding generation for all services
    if update.embedding_model is not None:
        raise HTTPException(
            status_code=400,
            detail="Embedding model cannot be changed at runtime. "
            "Change OPENAI_EMBEDDING_MODEL in .env and re-run "
            "python scripts/generate_openai_embeddings.py",
        )

    config = update_search_config(
        parsing_model=update.parsing_model,
        parsing_timeout_ms=update.parsing_timeout_ms,
        embedding_timeout_ms=update.embedding_timeout_ms,
    )
    return SearchConfigResponse(
        parsing_model=config.parsing_model,
        parsing_timeout_ms=config.parsing_timeout_ms,
        embedding_model=config.embedding_model,
        embedding_timeout_ms=config.embedding_timeout_ms,
        available_parsing_models=[ModelOption(**m) for m in AVAILABLE_PARSING_MODELS],
        available_embedding_models=[ModelOption(**m) for m in AVAILABLE_EMBEDDING_MODELS],
    )


@router.post("/config/reset", response_model=SearchConfigResetResponse)
async def reset_config() -> SearchConfigResetResponse:
    """
    Reset NL search configuration to environment defaults.

    Use this to revert any runtime changes made via PUT /config.
    """
    from ...services.search.config import (
        AVAILABLE_EMBEDDING_MODELS,
        AVAILABLE_PARSING_MODELS,
        reset_search_config,
    )

    config = reset_search_config()
    return SearchConfigResetResponse(
        status="reset",
        config=SearchConfigResponse(
            parsing_model=config.parsing_model,
            parsing_timeout_ms=config.parsing_timeout_ms,
            embedding_model=config.embedding_model,
            embedding_timeout_ms=config.embedding_timeout_ms,
            available_parsing_models=[ModelOption(**m) for m in AVAILABLE_PARSING_MODELS],
            available_embedding_models=[ModelOption(**m) for m in AVAILABLE_EMBEDDING_MODELS],
        ),
    )
