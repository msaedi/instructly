# backend/app/routes/search_history.py
"""
Search History API endpoints.

Unified implementation that handles both authenticated and guest users
with a single set of endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional as auth_get_current_user_optional
from ..database import get_db
from ..models.user import User
from ..schemas.search_history import SearchHistoryCreate, SearchHistoryResponse
from ..services.search_history_service import SearchHistoryService

router = APIRouter()


async def get_current_user_optional(
    current_user_email: Optional[str] = Depends(auth_get_current_user_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.

    This allows endpoints to work for both authenticated and guest users.
    """
    if not current_user_email:
        return None

    user = db.query(User).filter(User.email == current_user_email).first()
    return user


@router.get("/", response_model=List[SearchHistoryResponse])
async def get_recent_searches(
    limit: int = 3,
    current_user: Optional[User] = Depends(get_current_user_optional),
    x_guest_session_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Get recent searches for the current user (authenticated or guest).

    For authenticated users: Pass authorization token
    For guests: Pass X-Guest-Session-ID header

    Args:
        limit: Maximum number of searches to return (default 3)
        current_user: The authenticated user (if applicable)
        x_guest_session_id: Guest session ID header (if applicable)
        db: Database session

    Returns:
        List of recent search history entries
    """
    search_service = SearchHistoryService(db)

    if current_user:
        searches = search_service.get_recent_searches(user_id=current_user.id, limit=limit)
    elif x_guest_session_id:
        searches = search_service.get_recent_searches(guest_session_id=x_guest_session_id, limit=limit)
    else:
        # Return empty list if no user context
        return []

    return [
        SearchHistoryResponse(
            id=search.id,
            search_query=search.search_query,
            search_type=search.search_type,
            results_count=search.results_count,
            created_at=search.created_at,
            guest_session_id=search.guest_session_id if not current_user else None,
        )
        for search in searches
    ]


@router.post("/", response_model=SearchHistoryResponse, status_code=status.HTTP_201_CREATED)
async def record_search(
    search_data: SearchHistoryCreate,
    current_user: Optional[User] = Depends(get_current_user_optional),
    x_guest_session_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Record a search for the current user (authenticated or guest).

    For authenticated users: Pass authorization token
    For guests: Pass X-Guest-Session-ID header

    Args:
        search_data: The search details to record
        current_user: The authenticated user (if applicable)
        x_guest_session_id: Guest session ID header (if applicable)
        db: Database session

    Returns:
        The created or updated search history entry
    """
    search_service = SearchHistoryService(db)

    try:
        if current_user:
            search = await search_service.record_search(
                user_id=current_user.id,
                query=search_data.search_query,
                search_type=search_data.search_type,
                results_count=search_data.results_count,
            )
        elif x_guest_session_id:
            search = await search_service.record_search(
                guest_session_id=x_guest_session_id,
                query=search_data.search_query,
                search_type=search_data.search_type,
                results_count=search_data.results_count,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either authentication token or guest session ID",
            )

        return SearchHistoryResponse(
            id=search.id,
            search_query=search.search_query,
            search_type=search.search_type,
            results_count=search.results_count,
            created_at=search.created_at,
            guest_session_id=search.guest_session_id if not current_user else None,
        )
    except ValueError as e:
        # Handle validation errors with 400
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Only use 500 for unexpected errors
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error recording search: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(
    search_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    x_guest_session_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Delete a search for the current user (authenticated or guest).

    For authenticated users: Pass authorization token
    For guests: Pass X-Guest-Session-ID header

    Args:
        search_id: ID of the search to delete
        current_user: The authenticated user (if applicable)
        x_guest_session_id: Guest session ID header (if applicable)
        db: Database session

    Returns:
        204 No Content on success

    Raises:
        404 if search not found or doesn't belong to the user/guest
    """
    search_service = SearchHistoryService(db)

    if current_user:
        deleted = search_service.delete_search(user_id=current_user.id, search_id=search_id)
    elif x_guest_session_id:
        deleted = search_service.delete_search(guest_session_id=x_guest_session_id, search_id=search_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either authentication token or guest session ID",
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Search history entry not found or does not belong to you"
        )

    return None
