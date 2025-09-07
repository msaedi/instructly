"""
API routes for user favorites functionality.

Provides endpoints for students to favorite/unfavorite instructors
and manage their list of favorite instructors.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..core.enums import PermissionName
from ..database import get_db
from ..dependencies.permissions import require_permission
from ..schemas.favorites import (
    FavoritedInstructor,
    FavoriteResponse,
    FavoritesList,
    FavoriteStatusResponse,
)
from ..schemas.instructor import InstructorProfileResponse
from ..services.favorites_service import FavoritesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


def get_favorites_service(db: Session = Depends(get_db)) -> FavoritesService:
    """Dependency to get favorites service."""
    from ..services.cache_service import CacheService

    cache_service = CacheService(db)
    return FavoritesService(db, cache_service=cache_service)


@router.post("/{instructor_id}", response_model=FavoriteResponse)
async def add_favorite(
    instructor_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    _: None = Depends(
        require_permission(PermissionName.CREATE_BOOKINGS)
    ),  # Students can create bookings
):
    """
    Add an instructor to the current user's favorites.

    Args:
        instructor_id: ID of the instructor to favorite
        current_user: Current authenticated user email
        db: Database session
        favorites_service: Favorites service instance

    Returns:
        FavoriteResponse with success status

    Raises:
        HTTPException: If validation fails or user not found
    """
    try:
        # Get current user ID
        from ..repositories.factory import RepositoryFactory

        user_repo = RepositoryFactory.create_user_repository(db)
        user = user_repo.get_by_email(current_user)

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Add favorite
        result = favorites_service.add_favorite(student_id=user.id, instructor_id=instructor_id)

        return FavoriteResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding favorite: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add favorite"
        )


@router.delete("/{instructor_id}", response_model=FavoriteResponse)
async def remove_favorite(
    instructor_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    _: None = Depends(
        require_permission(PermissionName.CREATE_BOOKINGS)
    ),  # Students can create bookings
):
    """
    Remove an instructor from the current user's favorites.

    Args:
        instructor_id: ID of the instructor to unfavorite
        current_user: Current authenticated user email
        db: Database session
        favorites_service: Favorites service instance

    Returns:
        FavoriteResponse with success status

    Raises:
        HTTPException: If validation fails or user not found
    """
    try:
        # Get current user ID
        from ..repositories.factory import RepositoryFactory

        user_repo = RepositoryFactory.create_user_repository(db)
        user = user_repo.get_by_email(current_user)

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Remove favorite
        result = favorites_service.remove_favorite(student_id=user.id, instructor_id=instructor_id)

        return FavoriteResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing favorite: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove favorite"
        )


@router.get("", response_model=FavoritesList)
async def get_favorites(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    favorites_service: FavoritesService = Depends(get_favorites_service),
):
    """
    Get the current user's list of favorited instructors.

    Args:
        current_user: Current authenticated user email
        db: Database session
        favorites_service: Favorites service instance

    Returns:
        FavoritesList with favorited instructors

    Raises:
        HTTPException: If user not found
    """
    try:
        # Get current user ID
        from ..repositories.factory import RepositoryFactory

        user_repo = RepositoryFactory.create_user_repository(db)
        user = user_repo.get_by_email(current_user)

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Get favorites
        favorites = favorites_service.get_student_favorites(user.id)

        # Transform to response format
        favorited_instructors = []
        for instructor in favorites:
            # Build favorited instructor response
            fav_instructor = FavoritedInstructor(
                id=instructor.id,
                email=instructor.email,
                first_name=instructor.first_name,
                last_name=instructor.last_name,
                is_active=instructor.is_active,
                profile=InstructorProfileResponse.from_orm(instructor.instructor_profile)
                if instructor.instructor_profile
                else None,
            )
            favorited_instructors.append(fav_instructor)

        return FavoritesList(favorites=favorited_instructors, total=len(favorited_instructors))

    except Exception as e:
        logger.error(f"Error getting favorites: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get favorites"
        )


@router.get("/check/{instructor_id}", response_model=FavoriteStatusResponse)
async def check_favorite_status(
    instructor_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    favorites_service: FavoritesService = Depends(get_favorites_service),
):
    """
    Check if the current user has favorited a specific instructor.

    Args:
        instructor_id: ID of the instructor to check
        current_user: Current authenticated user email
        db: Database session
        favorites_service: Favorites service instance

    Returns:
        Dictionary with is_favorited boolean

    Raises:
        HTTPException: If user not found
    """
    try:
        # Get current user ID
        from ..repositories.factory import RepositoryFactory

        user_repo = RepositoryFactory.create_user_repository(db)
        user = user_repo.get_by_email(current_user)

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Check favorite status
        is_favorited = favorites_service.is_favorited(
            student_id=user.id, instructor_id=instructor_id
        )

        return FavoriteStatusResponse(is_favorited=is_favorited)

    except Exception as e:
        logger.error(f"Error checking favorite status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check favorite status",
        )
