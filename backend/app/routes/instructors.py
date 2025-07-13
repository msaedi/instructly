# backend/app/routes/instructors.py
"""
Instructor routes for InstaInstru platform.

VERIFIED CLEAN - No changes needed.
This file properly uses schemas and has no legacy patterns.
No availability slot or booking references.

Key Features:
    - Instructor profile management (CRUD operations)
    - Service offerings with soft delete support
    - Profile listing for student discovery
    - Role-based access control
    - Cache integration for performance
    - Areas of service management
    - Experience and bio information

Router Endpoints:
    GET / - List all instructor profiles with active services
    POST /profile - Create a new instructor profile
    GET /profile - Get current instructor's profile
    PUT /profile - Update instructor profile
    DELETE /profile - Delete profile and revert to student role
    GET /{instructor_id} - Get specific instructor's profile
"""

import logging
from typing import Dict, List, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..api.dependencies.auth import get_current_active_user
from ..api.dependencies.services import get_cache_service_dep, get_instructor_service
from ..models.user import User, UserRole
from ..schemas.instructor import (
    InstructorFilterParams,
    InstructorProfileCreate,
    InstructorProfileResponse,
    InstructorProfileUpdate,
)
from ..services.cache_service import CacheService
from ..services.instructor_service import InstructorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.get("/", response_model=Union[List[InstructorProfileResponse], Dict])
async def get_all_instructors(
    search: str = Query(None, description="Text search across name, bio, and skills"),
    skill: str = Query(None, description="Filter by specific skill/service"),
    min_price: float = Query(None, ge=0, le=1000, description="Minimum hourly rate"),
    max_price: float = Query(None, ge=0, le=1000, description="Maximum hourly rate"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records to return"),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """
    Get instructor profiles with optional filtering.

    Supports filtering by:
    - search: Text search across instructor name, bio, and skills
    - skill: Filter by specific skill/service
    - min_price/max_price: Price range filtering

    Returns filtered results with metadata when filters are applied,
    or a simple list when no filters are used (backward compatibility).
    """
    # Check if any filters are applied
    has_filters = any([search, skill, min_price is not None, max_price is not None])

    if has_filters:
        # Validate filter parameters using the schema
        try:
            filters = InstructorFilterParams(search=search, skill=skill, min_price=min_price, max_price=max_price)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Use the new filtering method
        result = instructor_service.get_instructors_filtered(
            search=filters.search,
            skill=filters.skill,
            min_price=filters.min_price,
            max_price=filters.max_price,
            skip=skip,
            limit=limit,
        )
        return result
    else:
        # No filters - use the original method for backward compatibility
        profiles = instructor_service.get_all_instructors(skip=skip, limit=limit)
        return profiles


@router.post(
    "/profile",
    response_model=InstructorProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_instructor_profile(
    profile: InstructorProfileCreate,
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """Create a new instructor profile."""
    try:
        profile_data = instructor_service.create_instructor_profile(user=current_user, profile_data=profile)
        return profile_data
    except Exception as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise


@router.get("/profile", response_model=InstructorProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """Get current instructor's profile."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access profiles",
        )

    try:
        profile_data = instructor_service.get_instructor_profile(current_user.id)
        return profile_data
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise


@router.put("/profile", response_model=InstructorProfileResponse)
async def update_profile(
    profile_update: InstructorProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
):
    """Update instructor profile with soft delete support."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can update profiles",
        )

    try:
        # Ensure instructor service has cache service
        if not instructor_service.cache_service and cache_service:
            instructor_service.cache_service = cache_service

        profile_data = instructor_service.update_instructor_profile(user_id=current_user.id, update_data=profile_update)
        return profile_data
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instructor_profile(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
):
    """Delete instructor profile and revert to student role."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can delete their profiles",
        )

    try:
        # Ensure instructor service has cache service
        if not instructor_service.cache_service and cache_service:
            instructor_service.cache_service = cache_service

        instructor_service.delete_instructor_profile(current_user.id)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise


@router.get("/{instructor_id}", response_model=InstructorProfileResponse)
async def get_instructor_profile(
    instructor_id: int, instructor_service: InstructorService = Depends(get_instructor_service)
):
    """Get a specific instructor's profile by user ID."""
    try:
        profile_data = instructor_service.get_instructor_profile(instructor_id)
        return profile_data
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")
        raise
