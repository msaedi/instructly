# backend/app/routes/search_history.py
"""
Search History API endpoints.

Provides endpoints for managing user search history:
- Recording searches
- Retrieving recent searches
- Deleting specific searches
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..database import get_db
from ..models.user import User
from ..schemas.search_history import SearchHistoryCreate, SearchHistoryResponse
from ..services.search_history_service import SearchHistoryService

router = APIRouter()


@router.get("/", response_model=List[SearchHistoryResponse])
async def get_recent_searches(
    limit: int = 3,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get the user's recent searches.

    Args:
        limit: Maximum number of searches to return (default 3)
        current_user: The authenticated user
        db: Database session

    Returns:
        List of recent search history entries
    """
    search_service = SearchHistoryService(db)
    searches = search_service.get_recent_searches(user_id=current_user.id, limit=limit)

    return [
        SearchHistoryResponse(
            id=search.id,
            search_query=search.search_query,
            search_type=search.search_type,
            results_count=search.results_count,
            created_at=search.created_at,
        )
        for search in searches
    ]


@router.post("/", response_model=SearchHistoryResponse, status_code=status.HTTP_201_CREATED)
async def record_search(
    search_data: SearchHistoryCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Record a new search in the user's history.

    Updates timestamp if the exact query already exists.
    Maintains a rolling window of searches per user.

    Args:
        search_data: The search details to record
        current_user: The authenticated user
        db: Database session

    Returns:
        The created or updated search history entry
    """
    search_service = SearchHistoryService(db)

    try:
        search = await search_service.record_search(
            user_id=current_user.id,
            query=search_data.search_query,
            search_type=search_data.search_type,
            results_count=search_data.results_count,
        )

        return SearchHistoryResponse(
            id=search.id,
            search_query=search.search_query,
            search_type=search.search_type,
            results_count=search.results_count,
            created_at=search.created_at,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to record search: {str(e)}"
        )


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(
    search_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Delete a specific search from the user's history.

    Only the owner of the search can delete it.

    Args:
        search_id: ID of the search to delete
        current_user: The authenticated user
        db: Database session

    Returns:
        204 No Content on success

    Raises:
        404 if search not found or user doesn't own it
    """
    search_service = SearchHistoryService(db)

    deleted = search_service.delete_search(user_id=current_user.id, search_id=search_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search history entry not found")

    return None
