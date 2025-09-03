# backend/app/routes/search.py
"""
Search API endpoints.

Provides natural language search functionality for finding instructors
and services using the SearchService.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..api.dependencies.auth import require_beta_phase_access
from ..database import get_db
from ..schemas.search_responses import InstructorSearchResponse
from ..services.search_service import SearchService

router = APIRouter()


@router.get(
    "/instructors",
    response_model=InstructorSearchResponse,
    dependencies=[Depends(require_beta_phase_access())],
)
async def search_instructors(
    q: str = Query(..., description="Search query", min_length=1),
    limit: Optional[int] = Query(20, ge=1, le=100, description="Maximum results to return"),
    db: Session = Depends(get_db),
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
        db: Database session

    Returns:
        Search results with instructors, services, and metadata
    """
    # Validate query
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    try:
        # Create search service instance
        search_service = SearchService(db)

        # Perform search
        results = search_service.search(q, limit=limit)

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
