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

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..api.dependencies.auth import get_current_active_user
from ..api.dependencies.services import get_account_lifecycle_service, get_cache_service_dep, get_instructor_service
from ..core.enums import RoleName
from ..core.exceptions import BusinessRuleException, ValidationException
from ..models.user import User
from ..schemas.account_lifecycle import AccountStatusChangeResponse, AccountStatusResponse
from ..schemas.base_responses import PaginatedResponse
from ..schemas.instructor import (
    InstructorFilterParams,
    InstructorProfileCreate,
    InstructorProfileResponse,
    InstructorProfileUpdate,
)
from ..services.account_lifecycle_service import AccountLifecycleService
from ..services.cache_service import CacheService
from ..services.instructor_service import InstructorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.get("/", response_model=PaginatedResponse[InstructorProfileResponse])
async def get_all_instructors(
    service_catalog_id: str = Query(..., description="Service catalog ID (required)"),
    min_price: float = Query(None, ge=0, le=1000, description="Minimum hourly rate"),
    max_price: float = Query(None, ge=0, le=1000, description="Maximum hourly rate"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """
    Get instructors offering a specific service.

    Service-first model: service_catalog_id is required.
    Additional filters:
    - min_price/max_price: Price range filtering for the specified service

    Returns a standardized paginated response with 'items' field.
    """
    # Calculate skip from page and per_page
    skip = (page - 1) * per_page

    # Validate filter parameters using the schema
    try:
        filters = InstructorFilterParams(
            service_catalog_id=service_catalog_id, min_price=min_price, max_price=max_price
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Get filtered instructors for the specified service
    result = instructor_service.get_instructors_filtered(
        search=None,
        service_catalog_id=filters.service_catalog_id,
        min_price=filters.min_price,
        max_price=filters.max_price,
        skip=skip,
        limit=per_page,
    )

    # Extract data from the filtered result
    # The service returns a dict with 'instructors' and 'metadata'
    instructors = result.get("instructors", [])
    total = result.get("metadata", {}).get("total_found", len(instructors))

    # Apply privacy protection to each instructor profile
    privacy_protected_instructors = [
        InstructorProfileResponse.from_orm(instructor)
        if hasattr(instructor, "id")
        else instructor  # If already dict/processed, pass through
        for instructor in instructors
    ]

    # Return standardized paginated response with privacy protection
    return PaginatedResponse(
        items=privacy_protected_instructors,
        total=total,
        page=page,
        per_page=per_page,
        has_next=page * per_page < total,
        has_prev=page > 1,
    )


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
    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access profiles",
        )

    try:
        profile_data = instructor_service.get_instructor_profile(current_user.id)
        # Apply privacy protection (though instructors viewing own profile would see full name anyway)
        if hasattr(profile_data, "id"):  # It's an ORM object
            return InstructorProfileResponse.from_orm(profile_data)
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
    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
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
    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
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
    instructor_id: str, instructor_service: InstructorService = Depends(get_instructor_service)
):
    """Get a specific instructor's profile by user ID with privacy protection."""
    try:
        profile_data = instructor_service.get_instructor_profile(instructor_id)
        # Apply privacy protection using schema-owned construction
        if hasattr(profile_data, "id"):  # It's an ORM object
            return InstructorProfileResponse.from_orm(profile_data)
        return profile_data  # Already processed/dict
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")
        raise


# Account Lifecycle Endpoints


@router.post("/{instructor_id}/suspend", response_model=AccountStatusChangeResponse)
async def suspend_instructor_account(
    instructor_id: str,
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
):
    """
    Suspend an instructor account.

    Requirements:
    - Must be the instructor themselves (cannot suspend other instructors)
    - Cannot have any future bookings
    - Suspended instructors can still login but cannot receive new bookings
    """
    # Check authorization - instructors can only modify their own account
    if current_user.id != instructor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own account status")

    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only instructors can suspend their accounts")

    try:
        result = account_service.suspend_instructor_account(current_user)
        return AccountStatusChangeResponse(**result)
    except BusinessRuleException as e:
        # Extract future bookings info if available
        has_bookings, future_bookings = account_service.has_future_bookings(current_user)
        if has_bookings:
            detail = str(e)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{instructor_id}/deactivate", response_model=AccountStatusChangeResponse)
async def deactivate_instructor_account(
    instructor_id: str,
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
):
    """
    Permanently deactivate an instructor account.

    Requirements:
    - Must be the instructor themselves (cannot deactivate other instructors)
    - Cannot have any future bookings
    - Deactivated instructors cannot login or be reactivated through the API
    """
    # Check authorization - instructors can only modify their own account
    if current_user.id != instructor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own account status")

    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only instructors can deactivate their accounts"
        )

    try:
        result = account_service.deactivate_instructor_account(current_user)
        return AccountStatusChangeResponse(**result)
    except BusinessRuleException as e:
        # Extract future bookings info if available
        has_bookings, future_bookings = account_service.has_future_bookings(current_user)
        if has_bookings:
            detail = str(e)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{instructor_id}/reactivate", response_model=AccountStatusChangeResponse)
async def reactivate_instructor_account(
    instructor_id: str,
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
):
    """
    Reactivate a suspended instructor account.

    Requirements:
    - Must be the instructor themselves (cannot reactivate other instructors)
    - Account must be suspended (not deactivated)
    - Once reactivated, instructor can receive bookings again
    """
    # Check authorization - instructors can only modify their own account
    if current_user.id != instructor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own account status")

    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only instructors can reactivate their accounts"
        )

    try:
        result = account_service.reactivate_instructor_account(current_user)
        return AccountStatusChangeResponse(**result)
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{instructor_id}/can-change-status", response_model=AccountStatusResponse)
async def check_account_status(
    instructor_id: str,
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
):
    """
    Check the current account status and available status change options.

    Returns:
    - Current account status
    - Whether the instructor can login
    - Whether the instructor can receive bookings
    - Available status change options based on current state and future bookings
    """
    # Check authorization - instructors can only check their own status
    if current_user.id != instructor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only check your own account status")

    try:
        result = account_service.get_account_status(current_user)
        return AccountStatusResponse(**result)
    except Exception as e:
        logger.error(f"Error checking account status: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to check account status")
