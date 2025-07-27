# backend/app/routes/search.py
"""
Search API endpoints.

Provides natural language search functionality for finding instructors
and services using the SearchService.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user_optional
from ..database import get_db
from ..models.user import User
from ..services.search_history_service import SearchHistoryService
from ..services.search_service import SearchService

router = APIRouter()


@router.get("/instructors")
async def search_instructors(
    q: str = Query(..., description="Search query", min_length=1),
    limit: Optional[int] = Query(20, ge=1, le=100, description="Maximum results to return"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user_optional),
):
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

        # Record search history for authenticated users
        if current_user:
            search_history_service = SearchHistoryService(db)
            # Count actual results returned
            results_count = len(results.get("results", [])) if isinstance(results, dict) else 0

            try:
                # Record the search asynchronously
                await search_history_service.record_search(
                    user_id=current_user.id, query=q, search_type="natural_language", results_count=results_count
                )
            except Exception as history_error:
                # Log error but don't fail the search
                # This ensures search history doesn't break the main search functionality
                import logging

                logger = logging.getLogger(__name__)
                logger.error(f"Failed to record search history: {str(history_error)}")

        return results

    except ValueError as e:
        # Handle invalid search parameters
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle unexpected errors
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
