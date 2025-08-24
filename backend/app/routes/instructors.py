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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user, get_current_active_user_optional
from ..api.dependencies.services import get_cache_service_dep, get_favorites_service, get_instructor_service
from ..core.enums import RoleName
from ..core.ulid_helper import is_valid_ulid
from ..database import get_db
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..models.user import User
from ..schemas.address_responses import CoverageFeatureCollectionResponse
from ..schemas.base_responses import PaginatedResponse
from ..schemas.instructor import (
    InstructorFilterParams,
    InstructorProfileCreate,
    InstructorProfileResponse,
    InstructorProfileUpdate,
)
from ..services.address_service import AddressService
from ..services.cache_service import CacheService
from ..services.favorites_service import FavoritesService
from ..services.instructor_service import InstructorService
from ..services.stripe_service import StripeService

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
        InstructorProfileResponse.model_validate(instructor)
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


def get_address_service(db: Session = Depends(get_db)) -> AddressService:
    return AddressService(db)


@router.post(
    "/me",
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


@router.get("/me", response_model=InstructorProfileResponse)
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


@router.put("/me", response_model=InstructorProfileResponse)
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


@router.post("/me/go-live", response_model=InstructorProfileResponse)
async def go_live(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
    db: Session = Depends(get_db),
):
    """Mark instructor profile as live if all mandatory steps are completed.

    Mandatory steps:
    - Stripe Connect onboarding completed
    - Identity verification completed
    - At least one service configured (skills/pricing)

    Background check is optional and does NOT gate going live.
    """
    if not any(role.name == RoleName.INSTRUCTOR for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can perform this action",
        )

    # Load profile details
    try:
        profile_data = instructor_service.get_instructor_profile(current_user.id, include_inactive_services=False)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise

    # Check Stripe Connect status
    stripe_service = StripeService(db)
    connect = (
        stripe_service.check_account_status(profile_data["id"])
        if profile_data.get("id")
        else {
            "has_account": False,
            "onboarding_completed": False,
        }
    )

    # Determine gating conditions
    skills_ok = bool(profile_data.get("skills_configured")) or (len(profile_data.get("services", [])) > 0)
    identity_ok = bool(profile_data.get("identity_verified_at"))
    connect_ok = bool(connect.get("onboarding_completed"))

    missing: list[str] = []
    if not skills_ok:
        missing.append("skills")
    if not identity_ok:
        missing.append("identity")
    if not connect_ok:
        missing.append("stripe_connect")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Prerequisites not met", "missing": missing},
        )

    # Set live and completion timestamp
    try:
        with instructor_service.transaction():
            # Refresh ORM profile
            profile = instructor_service.profile_repository.find_one_by(user_id=current_user.id)
            if not profile:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
            # Update flags
            if not getattr(profile, "onboarding_completed_at", None):
                instructor_service.profile_repository.update(
                    profile.id,
                    is_live=True,
                    onboarding_completed_at=datetime.now(timezone.utc),
                    skills_configured=True
                    if not getattr(profile, "skills_configured", False)
                    else profile.skills_configured,
                )
            else:
                instructor_service.profile_repository.update(profile.id, is_live=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to go live")

    # Return updated profile
    return instructor_service.get_instructor_profile(current_user.id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
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
    instructor_id: str,
    instructor_service: InstructorService = Depends(get_instructor_service),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    current_user: User = Depends(get_current_active_user_optional),
):
    """Get a specific instructor's profile by user ID with privacy protection and favorite status."""
    try:
        profile_data = instructor_service.get_instructor_profile(instructor_id)

        # Apply privacy protection using schema-owned construction
        if hasattr(profile_data, "id"):  # It's an ORM object
            response = InstructorProfileResponse.from_orm(profile_data)
        else:
            # If it's already a dict, convert to Pydantic model
            response = InstructorProfileResponse(**profile_data)

        # Add favorite status and count
        if current_user:
            # Check if current user has favorited this instructor
            response.is_favorited = favorites_service.is_favorited(
                student_id=current_user.id, instructor_id=instructor_id
            )
        else:
            response.is_favorited = None  # None indicates not authenticated

        # Always show favorite count
        stats = favorites_service.get_instructor_favorite_stats(instructor_id)
        response.favorited_count = stats["favorite_count"]

        return response
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")
        raise


@router.get("/{instructor_id}/coverage", response_model=CoverageFeatureCollectionResponse)
@rate_limit("30/minute", key_type=RateLimitKeyType.IP)
async def get_instructor_coverage(
    instructor_id: str,
    address_service: AddressService = Depends(get_address_service),
):
    if not is_valid_ulid(instructor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid instructor id")
    geo = address_service.get_coverage_geojson_for_instructors([instructor_id])
    return CoverageFeatureCollectionResponse(
        type=geo.get("type", "FeatureCollection"), features=geo.get("features", [])
    )
