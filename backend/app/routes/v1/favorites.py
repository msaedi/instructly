# backend/app/routes/v1/favorites.py
"""
Favorites routes - API v1

Versioned favorites endpoints under /api/v1/favorites.
All business logic delegated to FavoritesService.

Endpoints:
    GET /                              → List user favorites
    POST /{instructor_id}              → Add instructor to favorites
    DELETE /{instructor_id}            → Remove instructor from favorites
    GET /check/{instructor_id}         → Check if instructor is favorited
"""

import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies import get_current_user
from ...core.enums import PermissionName
from ...core.exceptions import raise_503_if_pool_exhaustion
from ...database import get_db
from ...dependencies.permissions import require_permission
from ...models.user import User
from ...schemas.favorites import (
    FavoritedInstructor,
    FavoriteResponse,
    FavoritesList,
    FavoriteStatusResponse,
)
from ...schemas.instructor import InstructorProfileResponse
from ...services.cache_service import CacheService
from ...services.favorites_service import FavoritesService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["favorites-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def get_favorites_service(db: Session = Depends(get_db)) -> FavoritesService:
    """Dependency to get favorites service."""
    cache_service: CacheService = CacheService(db)
    return FavoritesService(db, cache_service=cache_service)


@router.post("/{instructor_id}", response_model=FavoriteResponse)
async def add_favorite(
    instructor_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    _: None = Depends(
        require_permission(PermissionName.CREATE_BOOKINGS)
    ),  # Students can create bookings
) -> FavoriteResponse:
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
        result = await asyncio.to_thread(
            favorites_service.add_favorite,
            student_id=current_user.id,
            instructor_id=instructor_id,
        )

        return FavoriteResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise_503_if_pool_exhaustion(e)
        logger.error(f"Error adding favorite: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add favorite"
        )


@router.delete("/{instructor_id}", response_model=FavoriteResponse)
async def remove_favorite(
    instructor_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    _: None = Depends(
        require_permission(PermissionName.CREATE_BOOKINGS)
    ),  # Students can create bookings
) -> FavoriteResponse:
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
        result = await asyncio.to_thread(
            favorites_service.remove_favorite,
            student_id=current_user.id,
            instructor_id=instructor_id,
        )

        return FavoriteResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise_503_if_pool_exhaustion(e)
        logger.error(f"Error removing favorite: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove favorite"
        )


@router.get("", response_model=FavoritesList)
async def get_favorites(
    current_user: User = Depends(get_current_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> FavoritesList:
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
        favorites = await asyncio.to_thread(
            favorites_service.get_student_favorites,
            current_user.id,
        )

        # Transform to response format
        favorited_instructors: List[FavoritedInstructor] = []
        for instructor in favorites:
            # Build favorited instructor response
            fav_instructor = FavoritedInstructor(
                id=instructor.id,
                email=instructor.email,
                first_name=instructor.first_name,
                last_name=instructor.last_name,
                is_active=instructor.is_active,
                profile=(
                    InstructorProfileResponse.from_orm(
                        instructor.instructor_profile, include_private_fields=False
                    )
                    if instructor.instructor_profile
                    else None
                ),
            )
            favorited_instructors.append(fav_instructor)

        return FavoritesList(favorites=favorited_instructors, total=len(favorited_instructors))

    except Exception as e:
        raise_503_if_pool_exhaustion(e)
        logger.error(f"Error getting favorites: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get favorites"
        )


@router.get("/check/{instructor_id}", response_model=FavoriteStatusResponse)
async def check_favorite_status(
    instructor_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> FavoriteStatusResponse:
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
        is_favorited = await asyncio.to_thread(
            favorites_service.is_favorited,
            student_id=current_user.id,
            instructor_id=instructor_id,
        )

        return FavoriteStatusResponse(is_favorited=is_favorited)

    except Exception as e:
        raise_503_if_pool_exhaustion(e)
        logger.error(f"Error checking favorite status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check favorite status",
        )
