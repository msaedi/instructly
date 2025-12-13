# backend/app/routes/v1/search.py
"""
Search routes - API v1

Versioned search endpoints under /api/v1/search.
Provides natural language search functionality for finding instructors
and services using the SearchService.

Endpoints:
    GET /instructors    → Search instructors with natural language queries
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ...api.dependencies.auth import require_beta_phase_access
from ...api.dependencies.services import get_cache_service_dep
from ...database import get_db
from ...ratelimit.dependency import rate_limit
from ...schemas.search_responses import InstructorSearchResponse
from ...services.cache_service import CacheService
from ...services.search_service import SearchService

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
