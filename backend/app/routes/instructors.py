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
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..api.dependencies.auth import get_current_active_user
from ..api.dependencies.services import get_cache_service_dep, get_instructor_service
from ..models.user import User, UserRole
from ..schemas.instructor import InstructorProfileCreate, InstructorProfileResponse, InstructorProfileUpdate
from ..services.cache_service import CacheService
from ..services.instructor_service import InstructorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.get("/", response_model=List[InstructorProfileResponse])
async def get_all_instructors(
    skip: int = 0, limit: int = 100, instructor_service: InstructorService = Depends(get_instructor_service)
):
    """Get all instructor profiles with active services only."""
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
