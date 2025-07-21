# backend/app/routes/services.py
"""
Service catalog routes for InstaInstru platform.

Provides endpoints for:
- Browsing service categories
- Searching catalog services
- Adding services from catalog to instructor profile
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..api.dependencies.auth import get_current_active_user
from ..api.dependencies.services import get_instructor_service
from ..models.user import User, UserRole
from ..schemas.service_catalog import (
    CatalogServiceResponse,
    CategoryResponse,
    InstructorServiceCreate,
    InstructorServiceResponse,
)
from ..services.instructor_service import InstructorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/services", tags=["services"])


@router.get("/categories", response_model=List[CategoryResponse])
async def get_service_categories(
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """Get all service categories."""
    return instructor_service.get_service_categories()


@router.get("/catalog", response_model=List[CatalogServiceResponse])
async def get_catalog_services(
    category: Optional[str] = Query(None, description="Filter by category slug"),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """
    Get available services from the catalog.

    Optionally filter by category slug (e.g., 'music-arts', 'academic').
    """
    try:
        return instructor_service.get_available_catalog_services(category_slug=category)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Category '{category}' not found")
        raise


@router.post("/instructor/add", response_model=InstructorServiceResponse)
async def add_service_to_profile(
    service_data: InstructorServiceCreate,
    current_user: User = Depends(get_current_active_user),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """
    Add a service from the catalog to instructor's profile.

    Requires INSTRUCTOR role.
    """
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only instructors can add services")

    try:
        return instructor_service.create_instructor_service_from_catalog(
            instructor_id=current_user.id,
            catalog_service_id=service_data.catalog_service_id,
            hourly_rate=service_data.hourly_rate,
            custom_description=service_data.custom_description,
            duration_options=service_data.duration_options,
        )
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        elif "already offer" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise


@router.get("/search", response_model=Dict)
async def search_services(
    q: str = Query(..., min_length=2, description="Search query"),
    instructor_service: InstructorService = Depends(get_instructor_service),
):
    """
    Search for instructors by service.

    This is an alias for the instructor search endpoint that focuses on service matching.
    Searches across service names, categories, and search terms.
    """
    # Use the existing instructor search but with service-focused messaging
    result = instructor_service.get_instructors_filtered(search=q, skip=0, limit=50)

    # Add service-specific metadata
    result["search_type"] = "service"
    result["query"] = q

    return result
