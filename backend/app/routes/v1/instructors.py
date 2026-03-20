# backend/app/routes/v1/instructors.py
"""
Instructor routes - API v1

Versioned instructor endpoints under /api/v1/instructors.
All business logic delegated to InstructorService.

Endpoints:
    GET / - List all instructor profiles (filtered by service)
    POST /me - Create instructor profile
    GET /me - Get current instructor's profile
    GET /me/commission-status - Get current instructor's commission tier status
    PUT /me - Update instructor profile
    POST /me/go-live - Mark profile as live
    DELETE /me - Delete profile and revert to student role
    GET /{instructor_id} - Get specific instructor's profile
    GET /{instructor_id}/coverage - Get instructor service area coverage
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies.auth import (
    get_current_active_user,
    get_current_active_user_optional,
    require_beta_access,
)
from ...api.dependencies.services import (
    get_favorites_service,
    get_instructor_service,
    get_pricing_service,
)
from ...core.exceptions import (
    BusinessRuleException,
    DomainException,
    NotFoundException,
    ServiceException,
    raise_503_if_pool_exhaustion,
)
from ...core.ulid_helper import is_valid_ulid
from ...database import get_db
from ...models.user import User
from ...ratelimit.dependency import rate_limit
from ...repositories.filter_repository import FilterRepository
from ...schemas.address_responses import CoverageFeatureCollectionResponse
from ...schemas.base_responses import PaginatedResponse
from ...schemas.instructor import (
    CalendarSettingsAcknowledgeResponse,
    CalendarSettingsResponse,
    CommissionStatusResponse,
    GenerateBioResponse,
    InstructorFilterParams,
    InstructorProfileCreate,
    InstructorProfilePublic,
    InstructorProfileResponse,
    InstructorProfileUpdate,
    InstructorServiceAreaCheckResponse,
    ServiceAreaCheckCoordinates,
    UpdateCalendarSettings,
)
from ...services.address_service import AddressService
from ...services.bio_generation_service import BioGenerationService
from ...services.favorites_service import FavoritesService
from ...services.instructor_service import InstructorService
from ...services.pricing_service import PricingService
from .taxonomy_filter_query import parse_taxonomy_filter_query_params

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["instructors-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def get_address_service(db: Session = Depends(get_db)) -> AddressService:
    return AddressService(db)


@router.get(
    "",
    response_model=PaginatedResponse[InstructorProfilePublic],
    dependencies=[Depends(rate_limit("read"))],
    responses={
        400: {"description": "Invalid filter parameters (e.g., max_price < min_price)"},
    },
)
async def list_instructors(
    service_catalog_id: str = Query(..., description="Service catalog ID (required)"),
    min_price: float = Query(None, ge=0, le=1000, description="Minimum hourly rate"),
    max_price: float = Query(None, ge=0, le=1000, description="Maximum hourly rate"),
    age_group: str = Query(None, description="Filter by age group: 'kids' or 'adults'"),
    skill_level: Optional[str] = Query(
        None,
        description="Comma-separated skill levels (beginner,intermediate,advanced)",
    ),
    subcategory_id: Optional[str] = Query(
        None,
        pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$",
        description="Optional subcategory ULID context",
    ),
    content_filters: Optional[str] = Query(
        None,
        max_length=2000,
        description=(
            "Pipe-delimited taxonomy content filters in the format "
            "'key:val1,val2|key2:val3'. "
            "Max 10 keys and 20 values per key."
        ),
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> PaginatedResponse[InstructorProfilePublic]:
    """
    Get instructors offering a specific service.

    Service-first model: service_catalog_id is required.
    Additional filters:
    - min_price/max_price: Price range filtering for the specified service

    Returns a standardized paginated response with 'items' field.
    """
    skip = (page - 1) * per_page

    try:
        taxonomy_filter_selections, _ = parse_taxonomy_filter_query_params(
            skill_level=skill_level,
            content_filters=content_filters,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # Validate filter parameters
    try:
        filters = InstructorFilterParams(
            service_catalog_id=service_catalog_id,
            min_price=min_price,
            max_price=max_price,
            age_group=age_group,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Get filtered instructors
    result = await asyncio.to_thread(
        instructor_service.get_instructors_filtered,
        search=None,
        service_catalog_id=filters.service_catalog_id,
        min_price=filters.min_price,
        max_price=filters.max_price,
        age_group=filters.age_group,
        taxonomy_filter_selections=taxonomy_filter_selections or None,
        subcategory_id=subcategory_id,
        skip=skip,
        limit=per_page,
    )

    instructors = result.get("instructors", [])
    total = result.get("metadata", {}).get("total_found", len(instructors))

    # Apply privacy protection
    privacy_protected_instructors = [
        InstructorProfilePublic.model_validate(instructor)
        if hasattr(instructor, "id")
        else instructor
        for instructor in instructors
    ]

    return PaginatedResponse(
        items=privacy_protected_instructors,
        total=total,
        page=page,
        per_page=per_page,
        has_next=page * per_page < total,
        has_prev=page > 1,
    )


@router.post(
    "/me",
    response_model=InstructorProfileResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        400: {"description": "Profile already exists or validation error"},
    },
)
async def create_profile(
    profile: InstructorProfileCreate = Body(...),
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorProfileResponse:
    """Create a new instructor profile."""
    try:
        profile_data = await asyncio.to_thread(
            instructor_service.create_instructor_profile,
            current_user,
            profile,
        )
        if hasattr(profile_data, "id"):
            return InstructorProfileResponse.from_orm(profile_data)
        return InstructorProfileResponse(**profile_data)
    except BusinessRuleException as exc:
        if exc.code == "instructor_profile_exists":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
        raise exc.to_http_exception()


@router.get(
    "/me",
    response_model=InstructorProfileResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor"},
        404: {"description": "Profile not found"},
    },
)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorProfileResponse:
    """Get current instructor's profile."""
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access profiles",
        )

    try:
        profile_data = await asyncio.to_thread(
            instructor_service.get_instructor_profile, current_user.id
        )
        if hasattr(profile_data, "id"):
            return InstructorProfileResponse.from_orm(profile_data)
        return InstructorProfileResponse(**profile_data)
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except DomainException as e:
        raise e.to_http_exception()


@router.get(
    "/me/commission-status",
    response_model=CommissionStatusResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor"},
        404: {"description": "Profile not found"},
    },
)
async def get_my_commission_status(
    current_user: User = Depends(get_current_active_user),
    pricing_service: PricingService = Depends(get_pricing_service),
) -> CommissionStatusResponse:
    """Get current instructor's commission tier status."""
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access commission status",
        )

    try:
        return await asyncio.to_thread(
            pricing_service.get_instructor_commission_status,
            instructor_user_id=current_user.id,
        )
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except DomainException as e:
        raise e.to_http_exception()


@router.put(
    "/me",
    response_model=InstructorProfileResponse,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor or insufficient permissions"},
        404: {"description": "Profile not found"},
    },
)
async def update_profile(
    profile_update: InstructorProfileUpdate = Body(...),
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorProfileResponse:
    """Update instructor profile."""
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can update profiles",
        )

    try:
        profile_data = await instructor_service.update_instructor_profile_async(
            current_user.id,
            profile_update,
        )
        if hasattr(profile_data, "id"):
            return InstructorProfileResponse.from_orm(profile_data)
        return InstructorProfileResponse(**profile_data)
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except DomainException as e:
        raise e.to_http_exception()


@router.patch(
    "/me/calendar-settings",
    response_model=CalendarSettingsResponse,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor or insufficient permissions"},
        404: {"description": "Profile not found"},
    },
)
async def update_calendar_settings(
    calendar_settings: UpdateCalendarSettings = Body(...),
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> CalendarSettingsResponse:
    """Update instructor calendar settings used by the availability page."""

    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can update calendar settings",
        )

    try:
        payload = await asyncio.to_thread(
            instructor_service.update_calendar_settings,
            current_user.id,
            calendar_settings,
        )
        return CalendarSettingsResponse(**payload)
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except DomainException as e:
        raise e.to_http_exception()


@router.post(
    "/me/calendar-settings/acknowledge",
    response_model=CalendarSettingsAcknowledgeResponse,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor or insufficient permissions"},
        404: {"description": "Profile not found"},
    },
)
async def acknowledge_calendar_settings(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> CalendarSettingsAcknowledgeResponse:
    """Record dismissal of the first-save calendar settings acknowledgement."""

    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can acknowledge calendar settings",
        )

    try:
        payload = await asyncio.to_thread(
            instructor_service.acknowledge_calendar_settings,
            current_user.id,
        )
        return CalendarSettingsAcknowledgeResponse(**payload)
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except DomainException as e:
        raise e.to_http_exception()


@router.post(
    "/me/go-live",
    response_model=InstructorProfileResponse,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor or insufficient permissions"},
        400: {"description": "Prerequisites not met for going live"},
    },
)
async def go_live(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorProfileResponse:
    """
    Mark instructor profile as live if all prerequisites are met.

    Prerequisites:
    - Stripe Connect onboarding completed
    - Identity verification completed
    - At least one service configured
    - Background check passed
    """
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can perform this action",
        )

    try:
        profile = await asyncio.to_thread(instructor_service.go_live, current_user.id)
    except BusinessRuleException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message, "code": exc.code, "details": exc.details},
        )
    except ServiceException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message, "code": exc.code, "details": exc.details},
        )
    except NotFoundException as exc:
        raise exc.to_http_exception()

    return InstructorProfileResponse.from_orm(profile)


@router.post(
    "/me/generate-bio",
    response_model=GenerateBioResponse,
    dependencies=[Depends(rate_limit("bio_generate"))],
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Instructor profile not found"},
        503: {"description": "Bio generation service unavailable"},
    },
)
async def generate_bio(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> GenerateBioResponse:
    """Generate a personalized bio for the current instructor using AI."""
    try:
        service = BioGenerationService(db)
        bio = await service.generate_bio(current_user.id)
        return GenerateBioResponse(bio=bio)
    except NotFoundException as exc:
        raise exc.to_http_exception()
    except ServiceException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        )


# openapi-exempt: 204 No Content - no response body
@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_beta_access("instructor")), Depends(rate_limit("write"))],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not an instructor or insufficient permissions"},
        404: {"description": "Profile not found"},
    },
)
async def delete_profile(
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> None:
    """Delete instructor profile and revert to student role."""
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can delete their profiles",
        )

    try:
        # Run sync service call off the event loop so cache invalidation (sync adapter) executes.
        await asyncio.to_thread(instructor_service.delete_instructor_profile, current_user.id)
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    except DomainException as e:
        raise e.to_http_exception()

    return None


@router.get(
    "/{instructor_id}",
    response_model=InstructorProfilePublic,
    dependencies=[Depends(rate_limit("read"))],
    responses={
        404: {"description": "Instructor profile not found"},
    },
)
async def get_instructor(
    instructor_id: str = Path(
        ...,
        description="Instructor user ULID (or instructor profile ULID)",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    response: Response = None,
    instructor_service: InstructorService = Depends(get_instructor_service),
    favorites_service: FavoritesService = Depends(get_favorites_service),
    current_user: User = Depends(get_current_active_user_optional),
) -> InstructorProfilePublic:
    """Get a specific instructor's profile by ID with privacy protection and favorite status."""
    try:
        profile_data = await asyncio.to_thread(
            instructor_service.get_public_instructor_profile, instructor_id
        )
        if profile_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Instructor profile not found",
            )

        instructor_user_id = str(profile_data.get("user_id") or instructor_id)
        result = InstructorProfilePublic(**profile_data)

        # Add favorite status
        if current_user:
            result.is_favorited = await asyncio.to_thread(
                favorites_service.is_favorited,
                student_id=current_user.id,
                instructor_id=instructor_user_id,
            )
        else:
            result.is_favorited = None

        stats = await asyncio.to_thread(
            favorites_service.get_instructor_favorite_stats, instructor_user_id
        )
        result.favorited_count = stats["favorite_count"]

        # Set Cache-Control header (5 minutes to match backend cache TTL)
        if response:
            response.headers["Cache-Control"] = (
                "private, max-age=300" if current_user else "public, max-age=300"
            )

        return result
    except HTTPException:
        raise
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found"
        )
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        raise_503_if_pool_exhaustion(e)
        raise


@router.get(
    "/{instructor_id}/coverage",
    response_model=CoverageFeatureCollectionResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses={
        400: {"description": "Invalid instructor ID"},
    },
)
async def get_coverage(
    instructor_id: str = Path(
        ...,
        description="Instructor user ULID (or instructor profile ULID)",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    address_service: AddressService = Depends(get_address_service),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> CoverageFeatureCollectionResponse:
    """Get instructor service area coverage as GeoJSON."""
    if not is_valid_ulid(instructor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid instructor ID")

    try:
        instructor_user = await asyncio.to_thread(
            instructor_service.get_instructor_user, instructor_id
        )
    except NotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")
    except DomainException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(
            "coverage_check_failed",
            extra={"instructor_id": instructor_id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error"
        )

    geo = await asyncio.to_thread(
        address_service.get_coverage_geojson_for_instructors, [instructor_user.id]
    )
    return CoverageFeatureCollectionResponse(
        type=geo.get("type", "FeatureCollection"), features=geo.get("features", [])
    )


@router.get(
    "/{instructor_id}/check-service-area",
    response_model=InstructorServiceAreaCheckResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses={
        400: {"description": "Invalid instructor ID"},
        404: {"description": "Instructor not found"},
    },
)
def check_service_area(
    instructor_id: str = Path(
        ...,
        description="Instructor user ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude"),
    db: Session = Depends(get_db),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorServiceAreaCheckResponse:
    """Check whether coordinates fall within an instructor's service area."""
    if not is_valid_ulid(instructor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid instructor ID")

    try:
        instructor_service.get_instructor_user(instructor_id)
    except NotFoundException as exc:
        raise exc.to_http_exception()

    filter_repo = FilterRepository(db)
    is_covered = filter_repo.is_location_in_service_area(
        instructor_id=instructor_id,
        lat=lat,
        lng=lng,
    )

    return InstructorServiceAreaCheckResponse(
        instructor_id=instructor_id,
        is_covered=is_covered,
        coordinates=ServiceAreaCheckCoordinates(lat=lat, lng=lng),
    )
