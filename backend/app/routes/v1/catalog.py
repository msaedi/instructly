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

from ...api.dependencies.services import get_catalog_browse_service
from ...core.exceptions import DomainException
from ...schemas.service_catalog import ServiceCatalogDetail, ServiceCatalogSummary
from ...schemas.subcategory import CategoryDetail, CategorySummary, SubcategoryDetail
from ...schemas.taxonomy_filter import SubcategoryFilterResponse
from ...services.catalog_browse_service import CatalogBrowseService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["catalog-v1"])


@router.get("/categories", response_model=List[CategorySummary])
async def list_categories(
    response: Response,
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> List[CategorySummary]:
    """All active categories with subcategory counts. Cached 1hr."""
    data = await asyncio.to_thread(service.list_categories)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[CategorySummary], data)


@router.get("/categories/{category_slug}", response_model=CategoryDetail)
async def get_category(
    category_slug: str,
    response: Response,
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
)
async def get_subcategory(
    category_slug: str,
    subcategory_slug: str,
    response: Response,
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> SubcategoryDetail:
    """Subcategory detail with services and filters. Cached 30min."""
    try:
        data = await asyncio.to_thread(service.get_subcategory, category_slug, subcategory_slug)
    except DomainException as exc:
        raise exc.to_http_exception() from exc
    response.headers["Cache-Control"] = "public, max-age=1800"
    return SubcategoryDetail(**data)


@router.get("/services/{service_id}", response_model=ServiceCatalogDetail)
async def get_service(
    service_id: str,
    response: Response,
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
)
async def list_services_for_subcategory(
    subcategory_id: str,
    response: Response,
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> List[ServiceCatalogSummary]:
    """Services in a subcategory. Cached 30min."""
    data = await asyncio.to_thread(service.list_services_for_subcategory, subcategory_id)
    response.headers["Cache-Control"] = "public, max-age=1800"
    return cast(List[ServiceCatalogSummary], data)


@router.get(
    "/subcategories/{subcategory_id}/filters",
    response_model=List[SubcategoryFilterResponse],
)
async def get_subcategory_filters(
    subcategory_id: str,
    response: Response,
    service: CatalogBrowseService = Depends(get_catalog_browse_service),
) -> List[SubcategoryFilterResponse]:
    """Filter definitions for a subcategory. Cached 1hr."""
    data = await asyncio.to_thread(service.get_filters_for_subcategory, subcategory_id)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return cast(List[SubcategoryFilterResponse], data)
