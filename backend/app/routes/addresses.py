"""Routes for user addresses and instructor service areas."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..api.dependencies.services import get_db
from ..database import get_db as get_session
from ..models.user import User
from ..schemas.address import (
    AddressCreate,
    AddressListResponse,
    AddressResponse,
    AddressUpdate,
    AutocompleteResponse,
    PlaceDetails,
    ServiceAreaItem,
    ServiceAreasResponse,
    ServiceAreasUpdateRequest,
)
from ..schemas.address_responses import CoverageFeatureCollectionResponse
from ..services.address_service import AddressService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/addresses", tags=["addresses"])


def get_address_service(db: Session = Depends(get_session)) -> AddressService:
    return AddressService(db)


@router.get("/me", response_model=AddressListResponse)
def list_my_addresses(
    current_user=Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
):
    items = [AddressResponse(**a) for a in service.list_addresses(current_user.id)]
    return AddressListResponse(items=items, total=len(items))


@router.post("/me", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_my_address(
    data: AddressCreate,
    current_user=Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
):
    created = service.create_address(current_user.id, data.model_dump())
    return AddressResponse(**created)


@router.patch("/me/{address_id}", response_model=AddressResponse)
def update_my_address(
    address_id: str,
    data: AddressUpdate,
    current_user=Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
):
    updated = service.update_address(current_user.id, address_id, data.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return AddressResponse(**updated)


class DeleteResponse(BaseModel):
    success: bool
    message: str


@router.delete("/me/{address_id}", response_model=DeleteResponse)
def delete_my_address(
    address_id: str,
    current_user=Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
):
    ok = service.delete_address(current_user.id, address_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return DeleteResponse(success=True, message="Address deleted")


# Instructor service areas
@router.get("/service-areas/me", response_model=ServiceAreasResponse)
def list_my_service_areas(
    current_user=Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
):
    items = [ServiceAreaItem(**a) for a in service.list_service_areas(current_user.id)]
    return ServiceAreasResponse(items=items, total=len(items))


@router.get("/places/autocomplete", response_model=AutocompleteResponse)
def places_autocomplete(q: str):
    """Provider-agnostic autocomplete passthrough.

    Uses the configured provider to retrieve suggestions.
    """
    import anyio

    from ..services.geocoding.factory import create_geocoding_provider

    provider = create_geocoding_provider()
    results = anyio.run(provider.autocomplete, q)
    items = [
        {
            "text": r.text,
            "place_id": r.place_id,
            "description": r.description,
            "types": r.types,
        }
        for r in results
    ]
    return AutocompleteResponse(items=items, total=len(items))


@router.get("/places/details", response_model=PlaceDetails)
def place_details(place_id: str):
    """Return normalized place details for a selected suggestion.

    Frontend uses this to auto-fill form fields without exposing provider payloads.
    """
    import anyio

    from ..services.geocoding.factory import create_geocoding_provider

    provider = create_geocoding_provider()
    result = anyio.run(provider.get_place_details, place_id)
    if not result:
        raise HTTPException(status_code=404, detail="Place not found")
    return PlaceDetails(
        formatted_address=result.formatted_address,
        latitude=result.latitude,
        longitude=result.longitude,
        street_number=result.street_number,
        street_name=result.street_name,
        city=result.city,
        state=result.state,
        postal_code=result.postal_code,
        country=result.country,
        provider_id=result.provider_id,
    )


@router.put("/service-areas/me", response_model=ServiceAreasResponse)
def replace_my_service_areas(
    payload: ServiceAreasUpdateRequest,
    current_user=Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
):
    service.replace_service_areas(current_user.id, payload.neighborhood_ids)
    items = [ServiceAreaItem(**a) for a in service.list_service_areas(current_user.id)]
    return ServiceAreasResponse(items=items, total=len(items))


# Public helper for map: bulk coverage for instructor ids
@router.get("/coverage/bulk", response_model=CoverageFeatureCollectionResponse)
def get_bulk_coverage_geojson(
    ids: str, service: AddressService = Depends(get_address_service)
) -> CoverageFeatureCollectionResponse:
    """Return GeoJSON FeatureCollection of neighborhoods served by the given instructors.

    'ids' is a comma-separated list of instructor user IDs.
    """
    instructor_ids = [s.strip() for s in (ids or "").split(",") if s.strip()]
    # Basic validation and limit
    if not instructor_ids:
        return CoverageFeatureCollectionResponse(type="FeatureCollection", features=[])
    if len(instructor_ids) > 100:
        instructor_ids = instructor_ids[:100]
    geo = service.get_coverage_geojson_for_instructors(instructor_ids)
    return CoverageFeatureCollectionResponse(
        type=geo.get("type", "FeatureCollection"), features=geo.get("features", [])
    )


class NeighborhoodItem(BaseModel):
    id: str
    name: str
    borough: str | None = None
    code: str | None = None


class NeighborhoodsListResponse(BaseModel):
    items: list[NeighborhoodItem]
    total: int
    page: int | None = None
    per_page: int | None = None


@router.get("/regions/neighborhoods", response_model=NeighborhoodsListResponse)
def list_neighborhoods(
    region_type: str = "nyc",
    borough: str | None = None,
    page: int = 1,
    per_page: int = 100,
    service: AddressService = Depends(get_address_service),
):
    per_page = max(1, min(per_page, 500))
    page = max(1, page)
    offset = (page - 1) * per_page
    items_raw = service.list_neighborhoods(region_type=region_type, borough=borough, limit=per_page, offset=offset)
    items = [NeighborhoodItem(**r) for r in items_raw]
    return NeighborhoodsListResponse(items=items, total=len(items), page=page, per_page=per_page)
