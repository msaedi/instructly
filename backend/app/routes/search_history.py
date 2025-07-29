# backend/app/routes/search_history.py
"""
Search History API endpoints.

Unified implementation that handles both authenticated and guest users
with a single set of endpoints.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from ..auth import get_current_user_optional as auth_get_current_user_optional
from ..database import get_db
from ..models.user import User
from ..schemas.search_context import SearchUserContext
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


async def get_search_context(
    current_user: Optional[User] = Depends(get_current_user_optional),
    x_guest_session_id: Optional[str] = Header(None),
    x_session_id: Optional[str] = Header(None),
    x_search_origin: Optional[str] = Header(None),
) -> SearchUserContext:
    """
    Get search context including user/guest identity and tracking headers.

    Args:
        current_user: Authenticated user if logged in
        x_guest_session_id: Guest session ID for anonymous users
        x_session_id: Browser session ID for analytics
        x_search_origin: Page where search originated

    Returns:
        SearchUserContext with all tracking information
    """
    if current_user:
        context = SearchUserContext.from_user(current_user.id, session_id=x_session_id)
    elif x_guest_session_id:
        context = SearchUserContext.from_guest(x_guest_session_id, session_id=x_session_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either authentication token or guest session ID",
        )

    # Add search origin if provided
    context.search_origin = x_search_origin
    return context


@router.get("/", response_model=List[SearchHistoryResponse])
async def get_recent_searches(
    limit: int = 3,
    context: SearchUserContext = Depends(get_search_context),
    db: Session = Depends(get_db),
):
    """
    Get recent searches for the current user (authenticated or guest).

    For authenticated users: Pass authorization token
    For guests: Pass X-Guest-Session-ID header

    Args:
        limit: Maximum number of searches to return (default 3)
        context: Search context with user/guest identity
        db: Database session

    Returns:
        List of recent search history entries
    """
    search_service = SearchHistoryService(db)
    searches = search_service.get_recent_searches(context=context, limit=limit)

    return [
        SearchHistoryResponse(
            id=search.id,
            search_query=search.search_query,
            search_type=search.search_type,
            results_count=search.results_count,
            first_searched_at=search.first_searched_at,
            last_searched_at=search.last_searched_at,
            search_count=search.search_count,
            guest_session_id=search.guest_session_id if not context.user_id else None,
        )
        for search in searches
    ]


@router.post("/", response_model=SearchHistoryResponse, status_code=status.HTTP_201_CREATED)
async def record_search(
    search_data: SearchHistoryCreate,
    request: Request,
    context: SearchUserContext = Depends(get_search_context),
    db: Session = Depends(get_db),
):
    """
    Record a search for the current user (authenticated or guest).

    For authenticated users: Pass authorization token
    For guests: Pass X-Guest-Session-ID header
    Optional headers:
    - X-Session-ID: Browser session ID for analytics
    - X-Search-Origin: Page where search originated

    Args:
        search_data: The search details to record
        context: Search context with user/guest identity and tracking info
        db: Database session

    Returns:
        The created or updated search history entry
    """
    search_service = SearchHistoryService(db)

    # Extract analytics data
    # Get client IP (handling proxies)
    client_ip = request.headers.get("X-Forwarded-For")
    if client_ip:
        # Take the first IP if there are multiple
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else None

    # Get user agent
    user_agent = request.headers.get("User-Agent")

    # Extract device context from request body if provided
    device_context = None
    if hasattr(search_data, "device_context"):
        device_context = search_data.device_context

    try:
        # Build search dict with all data including tracking info
        search_dict = {
            "search_query": search_data.search_query,
            "search_type": search_data.search_type,
            "results_count": search_data.results_count,
            "referrer": context.search_origin,
            "context": search_data.search_context if hasattr(search_data, "search_context") else None,
        }

        search = await search_service.record_search(
            context=context,
            search_data=search_dict,
            request_ip=client_ip,
            user_agent=user_agent,
            device_context=device_context,
        )

        return SearchHistoryResponse(
            id=search.id,
            search_query=search.search_query,
            search_type=search.search_type,
            results_count=search.results_count,
            first_searched_at=search.first_searched_at,
            last_searched_at=search.last_searched_at,
            search_count=search.search_count,
            guest_session_id=search.guest_session_id if not context.user_id else None,
            search_event_id=getattr(search, "search_event_id", None),
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


@router.post("/interaction", status_code=status.HTTP_201_CREATED)
async def track_interaction(
    interaction_data: dict,
    request: Request,
    context: SearchUserContext = Depends(get_search_context),
    db: Session = Depends(get_db),
):
    """
    Track user interaction with search results.

    Records clicks, hovers, bookmarks, and other interactions with search results
    to measure search effectiveness and result relevance.

    Args:
        interaction_data: Interaction details including:
            - search_event_id: ID of the search event
            - interaction_type: Type of interaction (click, hover, bookmark)
            - instructor_id: ID of the instructor interacted with
            - result_position: Position in search results
            - time_to_interaction: Time from search to interaction (seconds)
        request: HTTP request for headers
        context: Search user context
        db: Database session

    Returns:
        Interaction tracking confirmation
    """
    search_service = SearchHistoryService(db)

    try:
        # Extract interaction data
        search_event_id = interaction_data.get("search_event_id")
        interaction_type = interaction_data.get("interaction_type")
        instructor_id = interaction_data.get("instructor_id")
        result_position = interaction_data.get("result_position")
        time_to_interaction = interaction_data.get("time_to_interaction")

        logger.info(
            f"Track interaction request",
            {
                "search_event_id": search_event_id,
                "interaction_type": interaction_type,
                "context_user_id": context.user_id,
                "context_guest_session_id": context.guest_session_id,
            },
        )

        # Validate required fields
        if not search_event_id or not interaction_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="search_event_id and interaction_type are required"
            )

        # Get session ID from context
        session_id = getattr(context, "session_id", None)

        # Track the interaction
        interaction = search_service.track_interaction(
            search_event_id=search_event_id,
            interaction_type=interaction_type,
            instructor_id=instructor_id,
            result_position=result_position,
            time_to_interaction=time_to_interaction,
            session_id=session_id,
        )

        logger.info(
            f"Search interaction tracked successfully",
            {
                "interaction_id": interaction.id,
                "user_id": context.user_id,
                "guest_session_id": context.guest_session_id,
                "interaction_type": interaction_type,
            },
        )

        return {"status": "tracked", "interaction_id": interaction.id, "message": "Interaction tracked successfully"}
    except ValueError as e:
        # Handle specific validation errors
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error tracking interaction: {str(e)}", exc_info=True)
        # Return more specific error in development
        import os

        if os.getenv("ENV", "development") == "development":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to track interaction: {str(e)}"
            )
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to track interaction")
