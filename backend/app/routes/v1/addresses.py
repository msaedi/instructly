# backend/app/routes/v1/addresses.py
"""
Addresses routes - API v1

Versioned address endpoints under /api/v1/addresses.
All business logic delegated to AddressService.

Endpoints:
    GET /zip/is-nyc                      → Check if ZIP is in NYC
    GET /me                              → List user addresses
    POST /me                             → Create address
    PATCH /me/{address_id}               → Update address
    DELETE /me/{address_id}              → Delete address
    GET /service-areas/me                → List instructor service areas
    PUT /service-areas/me                → Replace instructor service areas
    GET /places/autocomplete             → Autocomplete address search
    GET /places/details                  → Get place details
    GET /coverage/bulk                   → Get bulk coverage GeoJSON
    GET /regions/neighborhoods           → List neighborhoods
"""

import logging
from typing import Any, Dict, Mapping, Sequence, cast

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Response, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...api.dependencies.services import get_cache_service_dep
from ...core.exceptions import DomainException
from ...database import get_db as get_session
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.user import User
from ...schemas.address import (
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
from ...schemas.address_responses import (
    CoverageFeatureCollectionResponse,
    DeleteResponse,
    NeighborhoodItem,
    NeighborhoodsListResponse,
    NYCZipCheckResponse,
)
from ...services.address_service import AddressService
from ...services.cache_service import CacheService
from ...services.geocoding.base import AutocompleteResult, GeocodedAddress
from ...utils.strict import model_filter

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["addresses-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


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


@router.get("/zip/is-nyc", response_model=NYCZipCheckResponse)
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
        response_payload: Dict[str, object] = {"is_nyc": False, "borough": None}
        return NYCZipCheckResponse(**model_filter(NYCZipCheckResponse, response_payload))

    borough = _nyc_zip_to_borough(zip5)
    response_payload = cast(Dict[str, object], {"is_nyc": bool(borough), "borough": borough})
    return NYCZipCheckResponse(**model_filter(NYCZipCheckResponse, response_payload))


@router.get("/me", response_model=AddressListResponse)
def list_my_addresses(
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> AddressListResponse:
    """List all addresses for the current user."""
    addresses_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_addresses(current_user.id),
    )
    items = [AddressResponse(**address) for address in addresses_raw]
    return AddressListResponse(items=items, total=len(items))


async def _invalidate_user_address_cache(cache_service: CacheService, user_id: str) -> None:
    """Background task to invalidate user address cache."""
    try:
        await cache_service.delete(f"user_default_address:{user_id}")
    except Exception:
        logger.debug(
            "Failed to invalidate user address cache for user_id=%s",
            user_id,
            exc_info=True,
        )


@router.post("/me", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_my_address(
    data: AddressCreate = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
    background_tasks: BackgroundTasks = None,
) -> AddressResponse:
    """Create a new address for the current user."""
    created = cast(Mapping[str, Any], service.create_address(current_user.id, data.model_dump()))
    # Invalidate user address cache (new address might become default)
    if background_tasks:
        background_tasks.add_task(_invalidate_user_address_cache, cache_service, current_user.id)
    return AddressResponse(**created)


@router.patch("/me/{address_id}", response_model=AddressResponse)
def update_my_address(
    address_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    data: AddressUpdate = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
    background_tasks: BackgroundTasks = None,
) -> AddressResponse:
    """Update an existing address for the current user."""
    updated = cast(
        Mapping[str, Any] | None,
        service.update_address(current_user.id, address_id, data.model_dump(exclude_unset=True)),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    # Invalidate user address cache (coords or default status may have changed)
    if background_tasks:
        background_tasks.add_task(_invalidate_user_address_cache, cache_service, current_user.id)
    return AddressResponse(**updated)


@router.delete("/me/{address_id}", response_model=DeleteResponse)
def delete_my_address(
    address_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
    background_tasks: BackgroundTasks = None,
) -> DeleteResponse:
    """Delete an address for the current user."""
    ok = service.delete_address(current_user.id, address_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    # Invalidate user address cache (default address may have changed)
    if background_tasks:
        background_tasks.add_task(_invalidate_user_address_cache, cache_service, current_user.id)
    response_payload = {"success": True, "message": "Address deleted"}
    return DeleteResponse(**model_filter(DeleteResponse, response_payload))


# Instructor service areas
@router.get("/service-areas/me", response_model=ServiceAreasResponse)
def list_my_service_areas(
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> ServiceAreasResponse:
    """List service areas for the current instructor."""
    service_areas_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_service_areas(current_user.id),
    )
    items = [ServiceAreaItem(**area) for area in service_areas_raw]
    return ServiceAreasResponse(items=items, total=len(items))


# NYC bias: Center on Midtown Manhattan with tighter radius to prioritize NY over NJ
# Note: Jersey City is only ~3km from Manhattan, so a large radius includes NJ
NYC_AUTOCOMPLETE_BIAS = {
    "lat": 40.7580,  # Midtown Manhattan (slightly north of original)
    "lng": -73.9855,  # Shifted east to be more centered on NYC boroughs
    "radius_m": 30000,  # 30km - covers all 5 boroughs but tighter bias
}


@router.get("/places/autocomplete", response_model=AutocompleteResponse)
def places_autocomplete(
    q: str, provider: str | None = None, scope: str | None = None
) -> AutocompleteResponse:
    """Provider-agnostic autocomplete passthrough.

    Uses the configured provider to retrieve suggestions.
    """
    import anyio

    from ...core.config import settings
    from ...services.geocoding.factory import create_geocoding_provider

    requested_provider = (provider or settings.geocoding_provider or "google").lower()

    scope_normalized = (scope or "").strip().lower()
    country_filter: str | None
    location_bias: dict[str, float] | None = None

    if scope_normalized == "global":
        country_filter = None
    elif scope_normalized == "us":
        country_filter = "US"
    else:
        country_filter = "US"
        location_bias = NYC_AUTOCOMPLETE_BIAS

    geocoder = create_geocoding_provider(requested_provider)

    async def _run_autocomplete() -> list[AutocompleteResult]:
        result = await geocoder.autocomplete(
            q,
            country=country_filter,
            location_bias=location_bias,
        )
        return list(result)

    results: list[AutocompleteResult] = anyio.run(_run_autocomplete)

    items: list[dict[str, Any]] = [
        {
            "text": r.text,
            "place_id": r.place_id,
            "description": r.description,
            "types": r.types,
            "provider": requested_provider,
        }
        for r in results
    ]
    return AutocompleteResponse(items=items, total=len(items))


@router.get("/places/details", response_model=PlaceDetails)
def place_details(place_id: str, provider: str | None = None) -> PlaceDetails:
    """Return normalized place details for a selected suggestion.

    Frontend uses this to auto-fill form fields without exposing provider payloads.
    """
    import anyio

    from ...core.config import settings
    from ...services.geocoding.factory import create_geocoding_provider

    original_place_id = place_id
    requested_provider = provider.lower() if provider else None
    normalized_place_id = place_id

    if requested_provider is None and ":" in place_id:
        prefix, remainder = place_id.split(":", 1)
        if prefix in {"google", "mapbox", "mock"} and remainder:
            requested_provider = prefix
            normalized_place_id = remainder

    if requested_provider is None:
        requested_provider = (settings.geocoding_provider or "google").lower()

    provider_used = requested_provider
    geocoder = create_geocoding_provider(requested_provider)
    result: GeocodedAddress | None = anyio.run(geocoder.get_place_details, normalized_place_id)

    if provider and not result:
        logger.warning(
            "Place details provider mismatch",
            extra={
                "provider": requested_provider,
                "requested_place_id": original_place_id,
            },
        )
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail={
                "code": "invalid_place_id_for_provider",
                "provider": requested_provider,
                "place_id": original_place_id,
            },
        )

    if not result and requested_provider == "google":
        fallback_provider = None
        try:
            fallback_provider = create_geocoding_provider("mapbox")
        except Exception:
            fallback_provider = None

        if fallback_provider is not None:
            logger.warning(
                "Falling back to Mapbox place details",
                extra={
                    "fallback_from": "google",
                    "fallback_to": "mapbox",
                    "original_place_id": normalized_place_id,
                },
            )
            fallback_result = anyio.run(fallback_provider.get_place_details, normalized_place_id)
            if fallback_result:
                result = fallback_result
                provider_used = "mapbox"

    if not result:
        raise HTTPException(status_code=404, detail="Place not found")

    provider_id = result.provider_id
    if provider_used and provider_id and not provider_id.startswith(f"{provider_used}:"):
        provider_id = f"{provider_used}:{provider_id}" if provider_id else provider_id

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
        provider_id=provider_id,
    )


@router.put("/service-areas/me", response_model=ServiceAreasResponse)
def replace_my_service_areas(
    payload: ServiceAreasUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> ServiceAreasResponse:
    """Replace all service areas for the current instructor."""
    try:
        service.replace_service_areas(current_user.id, payload.neighborhood_ids)
    except DomainException as exc:
        raise exc.to_http_exception()
    service_areas_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_service_areas(current_user.id),
    )
    items = [ServiceAreaItem(**area) for area in service_areas_raw]
    return ServiceAreasResponse(items=items, total=len(items))


# Public helper for map: bulk coverage for instructor ids
@router.get("/coverage/bulk", response_model=CoverageFeatureCollectionResponse)
@rate_limit("10/minute", key_type=RateLimitKeyType.IP)
def get_bulk_coverage_geojson(
    ids: str,
    response: Response,
    service: AddressService = Depends(get_address_service),
) -> CoverageFeatureCollectionResponse:
    """Return GeoJSON FeatureCollection of neighborhoods served by the given instructors.

    'ids' is a comma-separated list of instructor user IDs.
    """
    instructor_ids = [s.strip() for s in (ids or "").split(",") if s.strip()]
    # Basic validation and limit
    if not instructor_ids:
        response.headers["Cache-Control"] = "public, max-age=600"
        return CoverageFeatureCollectionResponse(type="FeatureCollection", features=[])
    if len(instructor_ids) > 100:
        instructor_ids = instructor_ids[:100]
    geo = cast(Mapping[str, Any], service.get_coverage_geojson_for_instructors(instructor_ids))
    response.headers["Cache-Control"] = "public, max-age=600"
    return CoverageFeatureCollectionResponse(
        type=geo.get("type", "FeatureCollection"), features=geo.get("features", [])
    )


@router.get("/regions/neighborhoods", response_model=NeighborhoodsListResponse)
def list_neighborhoods(
    region_type: str = "nyc",
    borough: str | None = None,
    page: int = 1,
    per_page: int = 100,
    service: AddressService = Depends(get_address_service),
) -> NeighborhoodsListResponse:
    """List neighborhoods for a region type."""
    per_page = max(1, min(per_page, 500))
    page = max(1, page)
    offset = (page - 1) * per_page
    items_raw = cast(
        Sequence[Mapping[str, Any]],
        service.list_neighborhoods(
            region_type=region_type, borough=borough, limit=per_page, offset=offset
        ),
    )
    items = [
        NeighborhoodItem(**model_filter(NeighborhoodItem, dict(record))) for record in items_raw
    ]
    response_payload = {
        "items": items,
        "total": len(items),
        "page": page,
        "per_page": per_page,
    }
    return NeighborhoodsListResponse(**model_filter(NeighborhoodsListResponse, response_payload))
