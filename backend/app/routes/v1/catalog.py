# backend/app/routes/v1/catalog.py
"""
Catalog browse routes — slug-based public taxonomy navigation.

Phase 4 endpoints under /api/v1/catalog:
    GET /categories                                → All categories (homepage grid)
    GET /categories/{category_slug}                → Category detail with subcategories
    GET /categories/{category_slug}/{sub_slug}     → Subcategory detail with services + filters
    GET /services/{service_id}                     → Single service detail
    GET /subcategories/{subcategory_id}/services   → Services in a subcategory
    GET /subcategories/{subcategory_id}/filters    → Filter definitions for a subcategory
"""

import asyncio
import logging
from typing import List, cast

from fastapi import APIRouter, Depends, Response
from fastapi.params import Path

from ...api.dependencies.services import get_catalog_browse_service
from ...core.exceptions import DomainException
from ...ratelimit.dependency import rate_limit
from ...schemas.service_catalog import ServiceCatalogDetail, ServiceCatalogSummary
from ...schemas.subcategory import CategoryDetail, CategorySummary, SubcategoryDetail
from ...schemas.taxonomy_filter import SubcategoryFilterResponse
from ...services.catalog_browse_service import CatalogBrowseService

logger = logging.getLogger(__name__)

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

router = APIRouter(tags=["catalog-v1"])


@router.get(
    "/categories",
    response_model=List[CategorySummary],
    dependencies=[Depends(rate_limit("read"))],
)
async def list_categories(
    response: Response,
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> List[CategorySummary]:
    """All active categories with subcategory counts. Cached 1hr."""
    try:
        data = await asyncio.to_thread(service.list_categories)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[CategorySummary], data)


@router.get(
    "/categories/{category_slug}",
    response_model=CategoryDetail,
    dependencies=[Depends(rate_limit("read"))],
)
async def get_category(
    response: Response,
    category_slug: str = Path(..., pattern=SLUG_PATTERN, max_length=100),
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> CategoryDetail:
    """Category detail with subcategory listing. Cached 1hr."""
    try:
        data = await asyncio.to_thread(service.get_category, category_slug)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=3600"
    return CategoryDetail(**data)


@router.get(
    "/categories/{category_slug}/{subcategory_slug}",
    response_model=SubcategoryDetail,
    dependencies=[Depends(rate_limit("read"))],
)
async def get_subcategory(
    response: Response,
    category_slug: str = Path(..., pattern=SLUG_PATTERN, max_length=100),
    subcategory_slug: str = Path(..., pattern=SLUG_PATTERN, max_length=100),
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> SubcategoryDetail:
    """Subcategory detail with services and filters. Cached 30min."""
    try:
        data = await asyncio.to_thread(service.get_subcategory, category_slug, subcategory_slug)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=1800"
    return SubcategoryDetail(**data)


@router.get(
    "/services/{service_id}",
    response_model=ServiceCatalogDetail,
    dependencies=[Depends(rate_limit("read"))],
)
async def get_service(
    response: Response,
    service_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> ServiceCatalogDetail:
    """Single service detail. Cached 30min."""
    try:
        data = await asyncio.to_thread(service.get_service, service_id)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=1800"
    return ServiceCatalogDetail(**data)


@router.get(
    "/subcategories/{subcategory_id}/services",
    response_model=List[ServiceCatalogSummary],
    dependencies=[Depends(rate_limit("read"))],
)
async def list_services_for_subcategory(
    response: Response,
    subcategory_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> List[ServiceCatalogSummary]:
    """Services in a subcategory. Cached 30min."""
    try:
        data = await asyncio.to_thread(service.list_services_for_subcategory, subcategory_id)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=1800"
    return cast(List[ServiceCatalogSummary], data)


@router.get(
    "/subcategories/{subcategory_id}/filters",
    response_model=List[SubcategoryFilterResponse],
    dependencies=[Depends(rate_limit("read"))],
)
async def get_subcategory_filters(
    response: Response,
    subcategory_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> List[SubcategoryFilterResponse]:
    """Filter definitions for a subcategory. Cached 1hr."""
    try:
        data = await asyncio.to_thread(service.get_filters_for_subcategory, subcategory_id)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[SubcategoryFilterResponse], data)
