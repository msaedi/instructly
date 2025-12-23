# backend/app/routes/v1/search.py
"""
Search routes - API v1

Versioned search endpoints under /api/v1/search.
Provides natural language search functionality for finding instructors
and services using NLSearchService.

Endpoints:
    GET /              → NL search with full pipeline (parsing, embedding, retrieval, ranking)
    GET /health        → Health check for search components
    GET /config        → Get/update search configuration (admin only)
    GET /analytics/*   → Search analytics endpoints (admin only)
"""

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ...api.dependencies.auth import (
    get_current_active_user_optional,
    require_beta_phase_access,
)
from ...api.dependencies.services import get_cache_service_dep
from ...database import get_db, get_db_session
from ...dependencies.permissions import require_permission
from ...models import User
from ...ratelimit.dependency import rate_limit
from ...repositories.address_repository import UserAddressRepository
from ...repositories.region_boundary_repository import RegionBoundaryRepository
from ...schemas.nl_search import (
    ModelOption,
    NLSearchResponse,
    PopularQueriesResponse,
    PopularQueryItem,
    SearchClickRequest,
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
from ...services.cache_service import CacheService
from ...services.permission_service import PermissionService
from ...services.search.config import get_search_config
from ...services.search.nl_search_service import NLSearchService, get_search_inflight_count
from ...services.search.patterns import NEAR_ME

logger = logging.getLogger(__name__)

SEARCH_ANALYTICS_TIMEOUT_S = float(os.getenv("SEARCH_ANALYTICS_TIMEOUT_S", "0.5"))

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["search-v1"])


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
    diagnostics: bool = Query(False, description="Include detailed diagnostics (admin only)"),
    force_skip_tier5: bool = Query(False, description="Force skip Tier 5 LLM (admin only)"),
    force_skip_tier4: bool = Query(False, description="Force skip Tier 4 embedding (admin only)"),
    force_skip_vector: bool = Query(False, description="Force skip vector search (admin only)"),
    force_skip_embedding: bool = Query(False, description="Force skip embeddings (admin only)"),
    force_high_load: bool = Query(False, description="Force high-load budget (admin only)"),
    response: Response = None,
    cache_service: CacheService = Depends(get_cache_service_dep),
    current_user: Optional[User] = Depends(get_current_active_user_optional),
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

    # Validate query is not empty after stripping whitespace
    if not q.strip():
        raise HTTPException(
            status_code=400,
            detail="Query cannot be empty or whitespace-only",
        )

    # Validate location (both or neither)
    user_location: Optional[tuple[float, float]] = None
    requires_auth = False
    requires_address = False
    location_message: Optional[str] = None

    if lat is not None and lng is not None:
        user_location = (lng, lat)  # Note: (lng, lat) order for PostGIS
    elif lat is not None or lng is not None:
        raise HTTPException(
            status_code=400,
            detail="Both lat and lng must be provided together",
        )

    # Handle "near me" queries - fetch user's default address if available
    is_near_me_query = NEAR_ME.search(q) is not None
    if is_near_me_query and user_location is None:
        if current_user is None:
            requires_auth = True
            location_message = "Please sign in to search near your location"
        else:
            # Try to get user's default address
            def _get_user_address() -> Optional[tuple[float, float]]:
                with get_db_session() as db:
                    address_repo = UserAddressRepository(db)
                    address = address_repo.get_default_address(current_user.id)
                    if address and address.latitude and address.longitude:
                        # Return as (lng, lat) for PostGIS
                        return (float(address.longitude), float(address.latitude))
                    return None

            user_location = await asyncio.to_thread(_get_user_address)
            if user_location is None:
                requires_address = True
                location_message = "Please add an address to your profile to search near you"

    # Reverse geocode coordinates to neighborhood for "near me" queries
    near_me_resolved_location: Optional[str] = None
    if is_near_me_query and user_location is not None:

        def _reverse_geocode_to_neighborhood() -> Optional[str]:
            with get_db_session() as db:
                region_repo = RegionBoundaryRepository(db)
                # user_location is (lng, lat) - need to extract lat and lng
                lng_val, lat_val = user_location
                region = region_repo.find_region_by_point(lat_val, lng_val, "nyc")
                if region and region.get("region_name"):
                    return str(region["region_name"])
                return None

        near_me_resolved_location = await asyncio.to_thread(_reverse_geocode_to_neighborhood)

    try:
        admin_flags = any(
            [
                diagnostics,
                force_skip_tier5,
                force_skip_tier4,
                force_skip_vector,
                force_skip_embedding,
                force_high_load,
            ]
        )
        if admin_flags:
            if current_user is None:
                raise HTTPException(status_code=403, detail="Admin access required")

            def _check_permission() -> bool:
                with get_db_session() as db:
                    service = PermissionService(db)
                    return service.user_has_permission(current_user.id, "admin:read")

            has_permission = await asyncio.to_thread(_check_permission)
            if not has_permission:
                raise HTTPException(status_code=403, detail="Admin access required")

        service = NLSearchService(cache_service=cache_service, region_code=region)
        result = await service.search(
            query=q,
            user_location=user_location,
            limit=limit,
            include_diagnostics=diagnostics,
            force_skip_tier5=force_skip_tier5,
            force_skip_tier4=force_skip_tier4,
            force_skip_vector=force_skip_vector,
            force_skip_embedding=force_skip_embedding,
            force_high_load=force_high_load,
        )

        # Update metadata for "near me" queries
        if is_near_me_query:
            result.meta.requires_auth = requires_auth
            result.meta.requires_address = requires_address
            if location_message:
                result.meta.location_message = location_message
            # Set resolved location from reverse geocoding
            if near_me_resolved_location:
                result.meta.location_resolved = near_me_resolved_location
                # Also update parsed.location to show "near me" was detected
                if result.meta.parsed:
                    result.meta.parsed.location = "near me"

        # Set Cache-Control header
        if response:
            cache_ttl = 60 if not result.meta.cache_hit else 300
            response.headers["Cache-Control"] = f"public, max-age={cache_ttl}"

        # Log search for analytics (TRULY non-blocking, fire-and-forget)
        # Generate ID upfront so we can return it immediately without waiting for DB
        from app.core.ulid_helper import generate_ulid

        search_query_id = generate_ulid()
        result.meta.search_query_id = search_query_id

        # Build normalized query from parsed info
        parsed = result.meta.parsed
        normalized_query = {
            "service_query": parsed.service_query,
            "location": parsed.location,
            "location_resolved": result.meta.location_resolved,
            "location_not_found": result.meta.location_not_found,
            "max_price": parsed.max_price,
            "date": parsed.date,
            "time_after": parsed.time_after,
            "time_before": parsed.time_before,
            "audience_hint": parsed.audience_hint,
            "skill_level": parsed.skill_level,
            "urgency": parsed.urgency,
        }
        top_result_ids = [r.best_match.service_catalog_id for r in result.results[:10]]

        # Capture values for closure
        _q = q
        _normalized_query = normalized_query
        _parsing_mode = result.meta.parsing_mode
        _result_count = result.meta.total_results
        _top_result_ids = top_result_ids
        _latency_ms = result.meta.latency_ms
        _cache_hit = result.meta.cache_hit
        _degraded = result.meta.degraded
        _search_query_id = search_query_id

        def _log_search_query_background() -> None:
            """Log analytics synchronously using its own session."""
            with get_db_session() as db:
                analytics_repo = SearchAnalyticsRepository(db)
                analytics_repo.nl_log_search_query(
                    original_query=_q,
                    normalized_query=_normalized_query,
                    parsing_mode=_parsing_mode,
                    parsing_latency_ms=0,
                    result_count=_result_count,
                    top_result_ids=_top_result_ids,
                    total_latency_ms=_latency_ms,
                    cache_hit=_cache_hit,
                    degraded=_degraded,
                    query_id=_search_query_id,
                )

        async def _log_search_query_safe() -> None:
            """Skip analytics under load and enforce a short timeout."""
            try:
                inflight = await get_search_inflight_count()
                high_load_threshold = int(get_search_config().high_load_threshold)
                if inflight >= high_load_threshold:
                    logger.debug(
                        "Skipping analytics - high load (inflight=%s threshold=%s)",
                        inflight,
                        high_load_threshold,
                    )
                    return
                await asyncio.wait_for(
                    asyncio.to_thread(_log_search_query_background),
                    timeout=SEARCH_ANALYTICS_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning("Background analytics logging timed out")
            except Exception as exc:
                logger.warning("Background analytics logging failed: %s", exc)

        # Fire-and-forget: create task but don't await it
        asyncio.create_task(_log_search_query_safe())

        return result

    except HTTPException:
        # Preserve intentional status codes (e.g., 503 overload from NLSearchService)
        raise
    except Exception as e:
        logger.error(f"NL search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Search temporarily unavailable",
        )


@router.get("/health", response_model=SearchHealthResponse)
async def search_health(
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> SearchHealthResponse:
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

    search_cache = SearchCacheService(cache_service=cache_service)
    cache_stats = await search_cache.get_cache_stats()

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
    _: User = Depends(require_permission("admin:read")),
) -> SearchMetricsResponse:
    """
    Get aggregate search metrics for the last N days. Requires admin access.

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
    _: User = Depends(require_permission("admin:read")),
) -> PopularQueriesResponse:
    """Get most popular search queries. Requires admin access."""
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
    _: User = Depends(require_permission("admin:read")),
) -> ZeroResultQueriesResponse:
    """Get queries that returned zero results. Requires admin access."""
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    repo = SearchAnalyticsRepository(db)
    rows = repo.nl_get_zero_result_queries(days, limit)
    queries = [ZeroResultQueryItem(**row) for row in rows]
    return ZeroResultQueriesResponse(queries=queries)


@router.post("/click", response_model=SearchClickResponse)
def log_search_click(
    request: Optional[SearchClickRequest] = Body(
        None,
        description=(
            "JSON body payload for click tracking. If omitted, query parameters are accepted for "
            "backward compatibility."
        ),
    ),
    search_query_id: Optional[str] = Query(None, description="Search query ID from NL search"),
    service_id: Optional[str] = Query(
        None, description="Service ID that was clicked (instructor_service_id)"
    ),
    instructor_id: Optional[str] = Query(None, description="Instructor user ID that was clicked"),
    position: Optional[int] = Query(
        None, ge=1, description="Position in search results (1-indexed)"
    ),
    action: str = Query("view", description="Action type: view, book, message, favorite"),
    db: Session = Depends(get_db),
    _current_user: Optional[User] = Depends(get_current_active_user_optional),
) -> SearchClickResponse:
    """
    Log a click on a search result for conversion tracking.

    Call this endpoint when a user interacts with a search result.
    Authentication is optional (best-effort).
    """
    from ...repositories.search_analytics_repository import SearchAnalyticsRepository

    repo = SearchAnalyticsRepository(db)

    if request is None:
        if not search_query_id or not instructor_id or position is None:
            raise HTTPException(
                status_code=422,
                detail="search_query_id, instructor_id, and position are required",
            )
        request = SearchClickRequest(
            search_query_id=search_query_id,
            service_id=service_id,
            instructor_id=instructor_id,
            position=position,
            action=action,
        )

    click_id: Optional[str] = None
    if request.service_id:
        service_catalog_id, instructor_profile_id = repo.nl_resolve_click_targets(
            service_id=request.service_id,
            instructor_id=request.instructor_id,
        )
        if not service_catalog_id:
            raise HTTPException(status_code=400, detail="Invalid service_id")

        if not instructor_profile_id:
            raise HTTPException(status_code=400, detail="Invalid instructor_id")

        click_id = repo.nl_log_search_click(
            search_query_id=request.search_query_id,
            service_id=service_catalog_id,
            instructor_id=instructor_profile_id,
            position=request.position,
            action=request.action,
        )

    # Self-learning: if the location was unresolved for this search, record which region
    # the user clicked into (best-effort; do not fail the endpoint).
    try:
        from app.services.search.location_learning_click_service import LocationLearningClickService

        LocationLearningClickService(db).capture_location_learning_click(
            search_query_id=request.search_query_id,
            instructor_user_id=request.instructor_id,
        )
    except Exception as learn_err:
        logger.debug("Location learning click capture failed: %s", str(learn_err))

    if click_id is None:
        from app.core.ulid_helper import generate_ulid

        click_id = generate_ulid()

    return SearchClickResponse(click_id=click_id)


# ===== Configuration Endpoints =====


@router.get("/config", response_model=SearchConfigResponse)
async def get_config(
    _: User = Depends(require_permission("admin:read")),
) -> SearchConfigResponse:
    """
    Get current NL search configuration. Requires admin access.

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
async def update_config(
    update: SearchConfigUpdate,
    _: User = Depends(require_permission("admin:manage")),
) -> SearchConfigResponse:
    """
    Update NL search configuration at runtime. Requires admin access.

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
async def reset_config(
    _: User = Depends(require_permission("admin:manage")),
) -> SearchConfigResetResponse:
    """
    Reset NL search configuration to environment defaults. Requires admin access.

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
