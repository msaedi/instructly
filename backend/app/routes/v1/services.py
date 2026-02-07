# backend/app/routes/v1/services.py
"""
Service catalog routes - API v1

Versioned service endpoints under /api/v1/services.
All business logic delegated to InstructorService.

Endpoints:
    GET /categories                          → Get all service categories (public)
    GET /categories/browse                   → Categories with subcategory briefs (public)
    GET /categories/{id}/tree                → Full 3-level tree for a category (public)
    GET /categories/{id}/subcategories       → Subcategories for a category (public)
    GET /subcategories/{id}                  → Subcategory with services (public)
    GET /subcategories/{id}/filters          → Filters for a subcategory (public)
    GET /catalog                             → Get catalog services (public)
    GET /catalog/top-per-category            → Top services per category (public)
    GET /catalog/all-with-instructors        → All services with instructor counts (public)
    GET /catalog/kids-available              → Services with kids-capable instructors (public)
    GET /catalog/by-age-group/{age_group}    → Services by age group (public)
    GET /catalog/{id}/filter-context         → Filter context for a service (public)
    GET /search                              → Search for instructors by service (public)
    POST /instructor/add                     → Add service to instructor profile (instructor)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

from ...api.dependencies.auth import get_current_active_user
from ...api.dependencies.services import get_instructor_service
from ...core.exceptions import DomainException
from ...models.user import User
from ...schemas.service_catalog import (
    CatalogServiceMinimalResponse,
    CatalogServiceResponse,
    CategoryResponse,
    InstructorServiceCapabilitiesUpdate,
    InstructorServiceCreate,
    InstructorServiceResponse,
)
from ...schemas.service_catalog_responses import (
    AllServicesMetadata,
    AllServicesWithInstructorsResponse,
    CategoryServiceDetail,
    CategoryWithServices,
    ServiceSearchMetadata,
    ServiceSearchResponse,
    TopCategoryItem,
    TopCategoryServiceItem,
    TopServicesMetadata,
    TopServicesPerCategoryResponse,
)
from ...schemas.subcategory import (
    CategoryTreeResponse,
    CategoryWithSubcategories,
    SubcategoryBrief,
    SubcategoryWithServices,
)
from ...schemas.taxonomy_filter import InstructorFilterContext, SubcategoryFilterResponse
from ...services.instructor_service import InstructorService
from ...utils.strict import model_filter

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["services-v1"])


@router.get("/categories", response_model=List[CategoryResponse])
async def get_service_categories(
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[CategoryResponse]:
    """Get all service categories (cached for 1 hour)."""
    categories = await asyncio.to_thread(instructor_service.get_service_categories)
    # Set Cache-Control header (1 hour to match backend cache TTL)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[CategoryResponse], categories)


@router.get("/catalog", response_model=List[CatalogServiceResponse])
async def get_catalog_services(
    response: Response,
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[CatalogServiceResponse]:
    """
    Get available services from the catalog.

    Optionally filter by category ID.
    """
    try:
        services = await asyncio.to_thread(
            instructor_service.get_available_catalog_services, category_id=category_id
        )
        response.headers["Cache-Control"] = "public, max-age=1800"
        return cast(List[CatalogServiceResponse], services)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category '{category_id}' not found",
            )
        raise


@router.post("/instructor/add", response_model=InstructorServiceResponse)
async def add_service_to_profile(
    service_data: InstructorServiceCreate = Body(...),
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorServiceResponse:
    """
    Add a service from the catalog to instructor's profile.

    Requires INSTRUCTOR role.
    """

    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only instructors can add services"
        )

    try:
        created = await asyncio.to_thread(
            instructor_service.create_instructor_service_from_catalog,
            instructor_id=current_user.id,
            catalog_service_id=service_data.catalog_service_id,
            hourly_rate=service_data.hourly_rate,
            custom_description=service_data.custom_description,
            duration_options=service_data.duration_options,
        )
        return InstructorServiceResponse(**created)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        elif "already offer" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise


@router.patch("/{service_id}/capabilities", response_model=InstructorServiceResponse)
async def update_service_capabilities(
    service_id: str,
    capabilities: InstructorServiceCapabilitiesUpdate = Body(...),
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorServiceResponse:
    """Update location capabilities for an instructor service."""
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only instructors can update services"
        )

    updates = capabilities.model_dump(exclude_unset=True)
    try:
        updated = await asyncio.to_thread(
            instructor_service.update_service_capabilities,
            service_id=service_id,
            instructor_id=current_user.id,
            updates=updates,
        )
    except DomainException as exc:
        raise exc.to_http_exception() from exc

    return InstructorServiceResponse(**updated)


@router.get("/search", response_model=ServiceSearchResponse)
async def search_services(
    q: str = Query(..., min_length=2, description="Search query"),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> ServiceSearchResponse:
    """
    Search for instructors by service.

    This is an alias for the instructor search endpoint that focuses on service matching.
    Searches across service names, categories, and search terms.
    """
    # Use the existing instructor search but with service-focused messaging
    result: Dict[str, Any] = await asyncio.to_thread(
        instructor_service.get_instructors_filtered, search=q, skip=0, limit=50
    )

    metadata_raw = cast(Dict[str, Any], result.get("metadata", {}))
    metadata = ServiceSearchMetadata(**model_filter(ServiceSearchMetadata, metadata_raw))

    response_payload = {
        "instructors": result.get("instructors", []),
        "metadata": metadata,
        "search_type": "service",
        "query": q,
    }

    return ServiceSearchResponse(**model_filter(ServiceSearchResponse, response_payload))


@router.get("/catalog/top-per-category", response_model=TopServicesPerCategoryResponse)
async def get_top_services_per_category(
    limit: int = Query(7, ge=1, le=20, description="Number of top services per category"),
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> TopServicesPerCategoryResponse:
    """
    Get top N services per category for homepage capsules.

    Optimized endpoint that returns only the most popular services per category,
    perfect for homepage display. Cached for 1 hour since popularity changes daily
    but we want fast response times.

    Args:
        limit: Number of top services per category (default: 7)

    Returns:
        Dictionary with categories and their top services
    """
    data: Dict[str, Any] = await asyncio.to_thread(
        instructor_service.get_top_services_per_category, limit=limit
    )

    categories_clean: List[TopCategoryItem] = []
    for category in cast(List[Dict[str, Any]], data.get("categories", [])):
        services_raw = cast(List[Dict[str, Any]], category.get("services", []))
        services_clean: List[TopCategoryServiceItem] = []
        for service_raw in services_raw:
            service_payload = {
                "id": str(service_raw.get("id", "")),
                "name": service_raw.get("name"),
                "slug": service_raw.get("slug"),
                "demand_score": service_raw.get("demand_score"),
                "active_instructors": service_raw.get("active_instructors"),
                "is_trending": service_raw.get("is_trending"),
                "display_order": service_raw.get("display_order"),
            }
            services_clean.append(
                TopCategoryServiceItem(**model_filter(TopCategoryServiceItem, service_payload))
            )

        category_payload = {
            "id": str(category.get("id", "")),
            "name": category.get("name"),
            "icon_name": category.get("icon_name"),
            "services": services_clean,
        }
        categories_clean.append(TopCategoryItem(**model_filter(TopCategoryItem, category_payload)))

    metadata = TopServicesMetadata(
        **model_filter(TopServicesMetadata, cast(Dict[str, Any], data.get("metadata", {})))
    )

    response_payload = {
        "categories": categories_clean,
        "metadata": metadata,
    }

    return TopServicesPerCategoryResponse(
        **model_filter(TopServicesPerCategoryResponse, response_payload)
    )


@router.get(
    "/catalog/all-with-instructors",
    response_model=AllServicesWithInstructorsResponse,
)
async def get_all_services_with_instructors(
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> AllServicesWithInstructorsResponse:
    """
    Get all catalog services organized by category with active instructor counts.

    This endpoint is optimized for the All Services page, providing all services
    with instructor availability information in a single request. Results are
    cached for 5 minutes to balance performance with data freshness.

    Returns:
        Dictionary with categories and their services, including active instructor counts
    """
    payload: Dict[str, Any] = await asyncio.to_thread(
        instructor_service.get_all_services_with_instructors
    )

    categories_clean: List[CategoryWithServices] = []
    for category in cast(List[Dict[str, Any]], payload.get("categories", [])):
        services_raw = cast(List[Dict[str, Any]], category.get("services", []))
        services_clean: List[CategoryServiceDetail] = []
        for service_raw in services_raw:
            service_payload = {
                "id": str(service_raw.get("id", "")),
                "subcategory_id": str(service_raw.get("subcategory_id", "")),
                "name": service_raw.get("name"),
                "slug": service_raw.get("slug"),
                "description": service_raw.get("description"),
                "search_terms": service_raw.get("search_terms"),
                "eligible_age_groups": service_raw.get("eligible_age_groups"),
                "display_order": service_raw.get("display_order"),
                "online_capable": service_raw.get("online_capable"),
                "requires_certification": service_raw.get("requires_certification"),
                "is_active": service_raw.get("is_active"),
                "active_instructors": service_raw.get("active_instructors"),
                "instructor_count": service_raw.get("instructor_count"),
                "demand_score": service_raw.get("demand_score"),
                "is_trending": service_raw.get("is_trending"),
                "actual_min_price": service_raw.get("actual_min_price"),
                "actual_max_price": service_raw.get("actual_max_price"),
            }
            services_clean.append(
                CategoryServiceDetail(**model_filter(CategoryServiceDetail, service_payload))
            )

        category_payload = {
            "id": str(category.get("id", "")),
            "name": category.get("name"),
            "subtitle": category.get("subtitle"),
            "description": category.get("description"),
            "icon_name": category.get("icon_name"),
            "services": services_clean,
        }

        categories_clean.append(
            CategoryWithServices(**model_filter(CategoryWithServices, category_payload))
        )

    metadata = AllServicesMetadata(
        **model_filter(AllServicesMetadata, cast(Dict[str, Any], payload.get("metadata", {})))
    )

    response_payload = {
        "categories": categories_clean,
        "metadata": metadata,
    }

    return AllServicesWithInstructorsResponse(
        **model_filter(AllServicesWithInstructorsResponse, response_payload)
    )


# ── Taxonomy navigation endpoints ──────────────────────────────


@router.get("/categories/browse", response_model=List[CategoryWithSubcategories])
async def get_categories_with_subcategories(
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[CategoryWithSubcategories]:
    """Get all categories with subcategory briefs (for browse page). Cached 1hr."""
    data = await asyncio.to_thread(instructor_service.get_categories_with_subcategories)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[CategoryWithSubcategories], data)


@router.get("/categories/{category_id}/tree", response_model=CategoryTreeResponse)
async def get_category_tree(
    category_id: str,
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> CategoryTreeResponse:
    """Get full 3-level tree for a category. Cached 1hr."""
    try:
        data = await asyncio.to_thread(instructor_service.get_category_tree, category_id)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=3600"
    return CategoryTreeResponse(**model_filter(CategoryTreeResponse, data))


@router.get("/categories/{category_id}/subcategories", response_model=List[SubcategoryBrief])
async def get_subcategories_for_category(
    category_id: str,
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[SubcategoryBrief]:
    """Get subcategories for a category (brief list)."""
    try:
        tree = await asyncio.to_thread(instructor_service.get_category_tree, category_id)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(
        List[SubcategoryBrief],
        tree.get("subcategories", []),
    )


@router.get("/subcategories/{subcategory_id}", response_model=SubcategoryWithServices)
async def get_subcategory_with_services(
    subcategory_id: str,
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> SubcategoryWithServices:
    """Get a subcategory with its services."""
    try:
        data = await asyncio.to_thread(
            instructor_service.get_subcategory_with_services, subcategory_id
        )
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=1800"
    return SubcategoryWithServices(**model_filter(SubcategoryWithServices, data))


@router.get(
    "/subcategories/{subcategory_id}/filters",
    response_model=List[SubcategoryFilterResponse],
)
async def get_subcategory_filters(
    subcategory_id: str,
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[SubcategoryFilterResponse]:
    """Get filter definitions for a subcategory."""
    data = await asyncio.to_thread(instructor_service.get_subcategory_filters, subcategory_id)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[SubcategoryFilterResponse], data)


@router.get("/catalog/by-age-group/{age_group}", response_model=List[CatalogServiceResponse])
async def get_services_by_age_group(
    age_group: str,
    response: Response,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[CatalogServiceResponse]:
    """Get catalog services eligible for an age group."""
    data = await asyncio.to_thread(instructor_service.get_services_by_age_group, age_group)
    response.headers["Cache-Control"] = "public, max-age=1800"
    return cast(List[CatalogServiceResponse], data)


@router.get(
    "/catalog/{service_id}/filter-context",
    response_model=InstructorFilterContext,
)
async def get_service_filter_context(
    service_id: str,
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> InstructorFilterContext:
    """Get filter context for instructor onboarding (available filters + eligible age groups)."""
    try:
        data = await asyncio.to_thread(instructor_service.get_service_filter_context, service_id)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    return InstructorFilterContext(**model_filter(InstructorFilterContext, data))


@router.get("/catalog/kids-available", response_model=List[CatalogServiceMinimalResponse])
async def get_kids_available_services(
    instructor_service: InstructorService = Depends(get_instructor_service),
) -> List[CatalogServiceMinimalResponse]:
    """
    Return catalog services that have at least one active instructor who teaches kids.

    Minimal payload: id, name, slug. Cached for 5 minutes.
    """
    services = await asyncio.to_thread(instructor_service.get_kids_available_services)
    return cast(List[CatalogServiceMinimalResponse], services)
