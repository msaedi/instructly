"""Routes for user addresses and instructor service areas."""

import logging
from typing import Any, Mapping, Sequence, cast

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..database import get_db as get_session
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
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
from ..services.geocoding.base import AutocompleteResult, GeocodedAddress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/addresses", tags=["addresses"])


def get_address_service(db: Session = Depends(get_session)) -> AddressService:
    return AddressService(db)


# --- Utility: NYC ZIP validation (approximate, robust without external calls) ---
def _nyc_zip_to_borough(zip5: str) -> str | None:
    """Return NYC borough name if ZIP is a known NYC ZIP, else None.

    Uses commonly recognized USPS ZIP ranges:
    - Manhattan: 10001–10292, 10499
    - Bronx: 10451–10475
    - Brooklyn: 11201–11256
    - Queens: 11004–11005, 11101–11109, 11351–11385, 11411–11499, 11691–11697
    - Staten Island: 10301–10314
    """
    try:
        z = int(zip5)
    except Exception:
        return None

    # Manhattan
    if (10001 <= z <= 10292) or z == 10499:
        return "Manhattan"
    # Staten Island
    if 10301 <= z <= 10314:
        return "Staten Island"
    # Bronx
    if 10451 <= z <= 10475:
        return "Bronx"
    # Brooklyn
    if 11201 <= z <= 11256:
        return "Brooklyn"
    # Queens
    if z in (11004, 11005):
        return "Queens"
    if 11101 <= z <= 11109:
        return "Queens"
    if 11351 <= z <= 11385:
        return "Queens"
    if 11411 <= z <= 11499:
        return "Queens"
    if 11691 <= z <= 11697:
        return "Queens"
    return None


class NYCZipCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    is_nyc: bool
    borough: str | None = None


@router.get("/zip/is-nyc", response_model=NYCZipCheckResponse)  # type: ignore[misc]
def is_nyc_zip(zip: str) -> NYCZipCheckResponse:
    """Lightweight NYC ZIP check.

    Args:
        zip: Five-digit ZIP code.

    Returns:
        { "is_nyc": bool, "borough": Optional[str] }

    Notes:
        - This endpoint is deterministic and does not require geocoding APIs.
        - It is sufficient for onboarding gating; deeper enrichment occurs when
          we create an address with lat/lng.
    """
    zip5 = (zip or "").strip()
    if len(zip5) != 5 or not zip5.isdigit():
        return NYCZipCheckResponse(is_nyc=False, borough=None)

    borough = _nyc_zip_to_borough(zip5)
    return NYCZipCheckResponse(is_nyc=bool(borough), borough=borough)


@router.get("/me", response_model=AddressListResponse)  # type: ignore[misc]
def list_my_addresses(
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> AddressListResponse:
    addresses_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_addresses(current_user.id),
    )
    items = [AddressResponse(**address) for address in addresses_raw]
    return AddressListResponse(items=items, total=len(items))


@router.post("/me", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)  # type: ignore[misc]
def create_my_address(
    data: AddressCreate = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> AddressResponse:
    created = cast(Mapping[str, Any], service.create_address(current_user.id, data.model_dump()))
    return AddressResponse(**created)


@router.patch("/me/{address_id}", response_model=AddressResponse)  # type: ignore[misc]
def update_my_address(
    address_id: str,
    data: AddressUpdate = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> AddressResponse:
    updated = cast(
        Mapping[str, Any] | None,
        service.update_address(current_user.id, address_id, data.model_dump(exclude_unset=True)),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return AddressResponse(**updated)


class DeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    success: bool
    message: str


@router.delete("/me/{address_id}", response_model=DeleteResponse)  # type: ignore[misc]
def delete_my_address(
    address_id: str,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> DeleteResponse:
    ok = service.delete_address(current_user.id, address_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return DeleteResponse(success=True, message="Address deleted")


# Instructor service areas
@router.get("/service-areas/me", response_model=ServiceAreasResponse)  # type: ignore[misc]
def list_my_service_areas(
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> ServiceAreasResponse:
    service_areas_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_service_areas(current_user.id),
    )
    items = [ServiceAreaItem(**area) for area in service_areas_raw]
    return ServiceAreasResponse(items=items, total=len(items))


@router.get("/places/autocomplete", response_model=AutocompleteResponse)  # type: ignore[misc]
def places_autocomplete(q: str) -> AutocompleteResponse:
    """Provider-agnostic autocomplete passthrough.

    Uses the configured provider to retrieve suggestions.
    """
    import anyio

    from ..services.geocoding.factory import create_geocoding_provider

    provider = create_geocoding_provider()
    results: list[AutocompleteResult] = anyio.run(provider.autocomplete, q)
    items: list[dict[str, Any]] = [
        {
            "text": r.text,
            "place_id": r.place_id,
            "description": r.description,
            "types": r.types,
        }
        for r in results
    ]
    return AutocompleteResponse(items=items, total=len(items))


@router.get("/places/details", response_model=PlaceDetails)  # type: ignore[misc]
def place_details(place_id: str) -> PlaceDetails:
    """Return normalized place details for a selected suggestion.

    Frontend uses this to auto-fill form fields without exposing provider payloads.
    """
    import anyio

    from ..services.geocoding.factory import create_geocoding_provider

    provider = create_geocoding_provider()
    result: GeocodedAddress | None = anyio.run(provider.get_place_details, place_id)
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


@router.put("/service-areas/me", response_model=ServiceAreasResponse)  # type: ignore[misc]
def replace_my_service_areas(
    payload: ServiceAreasUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> ServiceAreasResponse:
    service.replace_service_areas(current_user.id, payload.neighborhood_ids)
    service_areas_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_service_areas(current_user.id),
    )
    items = [ServiceAreaItem(**area) for area in service_areas_raw]
    return ServiceAreasResponse(items=items, total=len(items))


# Public helper for map: bulk coverage for instructor ids
@router.get("/coverage/bulk", response_model=CoverageFeatureCollectionResponse)  # type: ignore[misc]
@rate_limit("10/minute", key_type=RateLimitKeyType.IP)
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
    geo = cast(Mapping[str, Any], service.get_coverage_geojson_for_instructors(instructor_ids))
    return CoverageFeatureCollectionResponse(
        type=geo.get("type", "FeatureCollection"), features=geo.get("features", [])
    )


class NeighborhoodItem(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    id: str
    name: str
    borough: str | None = None
    code: str | None = None


class NeighborhoodsListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    items: list[NeighborhoodItem]
    total: int
    page: int | None = None
    per_page: int | None = None


@router.get("/regions/neighborhoods", response_model=NeighborhoodsListResponse)  # type: ignore[misc]
def list_neighborhoods(
    region_type: str = "nyc",
    borough: str | None = None,
    page: int = 1,
    per_page: int = 100,
    service: AddressService = Depends(get_address_service),
) -> NeighborhoodsListResponse:
    per_page = max(1, min(per_page, 500))
    page = max(1, page)
    offset = (page - 1) * per_page
    items_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_neighborhoods(
            region_type=region_type, borough=borough, limit=per_page, offset=offset
        ),
    )
    items = [NeighborhoodItem(**record) for record in items_raw]
    return NeighborhoodsListResponse(items=items, total=len(items), page=page, per_page=per_page)
