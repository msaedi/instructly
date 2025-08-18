"""Address service with provider-agnostic geocoding and NYC enrichment."""

from typing import List, Optional

from sqlalchemy.orm import Session

from ..repositories.address_repository import (
    InstructorServiceAreaRepository,
    NYCNeighborhoodRepository,
    UserAddressRepository,
)
from ..repositories.region_boundary_repository import RegionBoundaryRepository
from ..repositories.user_repository import UserRepository
from .base import BaseService
from .cache_service import CacheService, get_cache_service
from .geocoding.factory import create_geocoding_provider
from .location_enrichment import LocationEnrichmentService


class AddressService(BaseService):
    def __init__(self, db: Session, cache_service: Optional[CacheService] = None):
        super().__init__(db)
        self.address_repo = UserAddressRepository(db)
        self.neighborhood_repo = NYCNeighborhoodRepository(db)
        self.service_area_repo = InstructorServiceAreaRepository(db)
        self.user_repo = UserRepository(db)
        self.region_repo = RegionBoundaryRepository(db)
        try:
            self.cache: Optional[CacheService] = cache_service or get_cache_service(db)
        except Exception:
            self.cache = None

    # User addresses
    @BaseService.measure_operation("list_addresses")
    def list_addresses(self, user_id: str) -> list:
        entities = self.address_repo.list_for_user(user_id)
        return [self._to_dict(a) for a in entities]

    @BaseService.measure_operation("create_address")
    def create_address(self, user_id: str, data: dict) -> dict:
        # If is_default, unset others first
        if data.get("is_default"):
            self.address_repo.unset_default(user_id)
        # Enrich via place_id if present
        place_id = data.get("place_id")
        if place_id:
            geocoder = create_geocoding_provider()
            import anyio

            geocoded = anyio.run(geocoder.get_place_details, place_id)
            if geocoded:
                data.setdefault("latitude", geocoded.latitude)
                data.setdefault("longitude", geocoded.longitude)
                data.setdefault("locality", data.get("locality") or geocoded.city or "")
                data.setdefault("administrative_area", data.get("administrative_area") or geocoded.state or "")
                data.setdefault("postal_code", data.get("postal_code") or geocoded.postal_code or "")
                # Normalize country code to ISO-3166 alpha-2
                data.setdefault(
                    "country_code",
                    data.get("country_code") or self._normalize_country_code(getattr(geocoded, "country", None)),
                )
                data["verification_status"] = "verified"
                # Fallback: if lat/lon missing from place details, try geocode formatted address
                if not data.get("latitude") or not data.get("longitude"):
                    addr_str = geocoded.formatted_address or data.get("street_line1") or ""
                    if addr_str:
                        geo2 = anyio.run(geocoder.geocode, addr_str)
                        if geo2:
                            data["latitude"] = data.get("latitude") or geo2.latitude
                            data["longitude"] = data.get("longitude") or geo2.longitude
        # Optional enrichment if we have coordinates
        if data.get("latitude") and data.get("longitude"):
            enricher = LocationEnrichmentService(self.db)
            enr = enricher.enrich(float(data["latitude"]), float(data["longitude"]))
            data.setdefault("district", enr.get("district"))
            data.setdefault("neighborhood", enr.get("neighborhood"))
            data.setdefault("subneighborhood", enr.get("subneighborhood"))
            if enr.get("location_metadata") is not None:
                data.setdefault("location_metadata", enr.get("location_metadata"))
        # Default recipient_name to user's full name if not provided
        if not data.get("recipient_name"):
            user = self.user_repo.find_one_by(id=user_id)
            if user:
                full_name = " ".join(
                    filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)])
                ).strip()
                if full_name:
                    data["recipient_name"] = full_name
        with self.transaction():
            entity = self.address_repo.create(user_id=user_id, **data)
        return self._to_dict(entity)

    @BaseService.measure_operation("update_address")
    def update_address(self, user_id: str, address_id: str, data: dict) -> Optional[dict]:
        entity = self.address_repo.get_by_id(address_id, load_relationships=False)
        if not entity or entity.user_id != user_id:
            return None
        if data.get("is_default"):
            self.address_repo.unset_default(user_id)
        # Re-enrich if a new place_id is provided and key fields are missing
        place_id = data.get("place_id")
        if place_id:
            geocoder = create_geocoding_provider()
            import anyio

            geocoded = anyio.run(geocoder.get_place_details, place_id)
            if geocoded:
                data.setdefault("latitude", geocoded.latitude)
                data.setdefault("longitude", geocoded.longitude)
                data.setdefault("locality", data.get("locality") or geocoded.city or "")
                data.setdefault("administrative_area", data.get("administrative_area") or geocoded.state or "")
                data.setdefault("postal_code", data.get("postal_code") or geocoded.postal_code or "")
                data.setdefault("country_code", data.get("country_code") or (geocoded.country or "US")[:2])
                data["verification_status"] = "verified"
                if not data.get("latitude") or not data.get("longitude"):
                    addr_str = geocoded.formatted_address or data.get("street_line1") or ""
                    if addr_str:
                        geo2 = anyio.run(geocoder.geocode, addr_str)
                        if geo2:
                            data["latitude"] = data.get("latitude") or geo2.latitude
                            data["longitude"] = data.get("longitude") or geo2.longitude
        # Optional enrichment on update if coordinates present or just resolved
        if data.get("latitude") and data.get("longitude"):
            enricher = LocationEnrichmentService(self.db)
            enr = enricher.enrich(float(data["latitude"]), float(data["longitude"]))
            data.setdefault("district", enr.get("district"))
            data.setdefault("neighborhood", enr.get("neighborhood"))
            data.setdefault("subneighborhood", enr.get("subneighborhood"))
            if enr.get("location_metadata") is not None:
                data.setdefault("location_metadata", enr.get("location_metadata"))
        # Normalize country code if present
        if "country_code" in data:
            data["country_code"] = self._normalize_country_code(data.get("country_code"))
        # Ensure recipient_name persists or is defaulted
        if not data.get("recipient_name"):
            user = self.user_repo.find_one_by(id=user_id)
            if user:
                full_name = " ".join(
                    filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)])
                ).strip()
                if full_name:
                    data["recipient_name"] = full_name
        with self.transaction():
            updated = self.address_repo.update(address_id, **data)
        return self._to_dict(updated) if updated else None

    @BaseService.measure_operation("delete_address")
    def delete_address(self, user_id: str, address_id: str) -> bool:
        entity = self.address_repo.get_by_id(address_id, load_relationships=False)
        if not entity or entity.user_id != user_id:
            return False
        # Soft delete via repository
        with self.transaction():
            self.address_repo.update(address_id, is_active=False)
        return True

    # Instructor service areas
    @BaseService.measure_operation("list_service_areas")
    def list_service_areas(self, instructor_id: str) -> List[dict]:
        areas = self.service_area_repo.list_for_instructor(instructor_id)
        return [
            {
                "neighborhood_id": a.neighborhood_id,
                "ntacode": a.neighborhood.ntacode if a.neighborhood else None,
                "name": a.neighborhood.ntaname if a.neighborhood else None,
                "borough": a.neighborhood.borough if a.neighborhood else None,
            }
            for a in areas
        ]

    @BaseService.measure_operation("replace_service_areas")
    def replace_service_areas(self, instructor_id: str, neighborhood_ids: List[str]) -> int:
        with self.transaction():
            count = self.service_area_repo.replace_areas(instructor_id, neighborhood_ids)
            return count

    # Map support utilities
    @BaseService.measure_operation("get_coverage_geojson_for_instructors")
    def get_coverage_geojson_for_instructors(self, instructor_ids: List[str]) -> dict:
        """Return a GeoJSON FeatureCollection of active coverage polygons for instructors.

        Uses simplified boundaries via ST_AsGeoJSON directly from DB through the RegionBoundaryRepository
        helper methods to preserve repository pattern.
        """
        if not instructor_ids:
            return {"type": "FeatureCollection", "features": []}

        # Cache key
        cache_key = None
        if self.cache:
            try:
                ordered = sorted(set(instructor_ids))
                cache_key = f"coverage:bulk:{','.join(ordered)}"
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            except Exception:
                pass

        # List areas for instructors
        areas = self.service_area_repo.list_neighborhoods_for_instructors(instructor_ids)
        neighborhood_ids = list({a.neighborhood_id for a in areas if a.neighborhood_id})
        if not neighborhood_ids:
            return {"type": "FeatureCollection", "features": []}

        # Fetch minimal boundary JSON via repository helper
        features: list[dict] = []
        chunk_size = 200
        for i in range(0, len(neighborhood_ids), chunk_size):
            chunk = neighborhood_ids[i : i + chunk_size]
            rows = self.region_repo.get_simplified_geojson_by_ids(chunk)
            for row in rows:
                serving = [a.instructor_id for a in areas if a.neighborhood_id == row["id"]]
                features.append(
                    {
                        "type": "Feature",
                        "geometry": row["geometry"],
                        "properties": {
                            "region_id": row["id"],
                            "name": row["region_name"],
                            "borough": row["parent_region"],
                            "region_type": row["region_type"],
                            "instructors": serving,
                        },
                    }
                )

        result = {"type": "FeatureCollection", "features": features}
        if self.cache and cache_key:
            try:
                self.cache.set(cache_key, result, tier="hot")  # ~5 minutes
            except Exception:
                pass
        return result

    @BaseService.measure_operation("list_neighborhoods")
    def list_neighborhoods(
        self, region_type: str = "nyc", borough: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        # Cache key for pagination
        cache_key = None
        if self.cache:
            try:
                cache_key = f"neighborhoods:{region_type}:{borough or 'all'}:{limit}:{offset}"
                cached = self.cache.get(cache_key)
                if cached is not None:
                    return cached
            except Exception:
                pass

        rows = self.region_repo.list_regions(region_type=region_type, parent_region=borough, limit=limit, offset=offset)
        items = [
            {
                "id": r["id"],
                "name": r["region_name"],
                "borough": r["parent_region"],
                "code": r["region_code"],
            }
            for r in rows
        ]
        if self.cache and cache_key:
            try:
                self.cache.set(cache_key, items, tier="warm")  # ~1 hour
            except Exception:
                pass
        return items

    # Helpers
    def _to_dict(self, a) -> dict:
        return {
            "id": a.id,
            "label": a.label,
            "custom_label": a.custom_label,
            "recipient_name": a.recipient_name,
            "street_line1": a.street_line1,
            "street_line2": a.street_line2,
            "locality": a.locality,
            "administrative_area": a.administrative_area,
            "postal_code": a.postal_code,
            "country_code": a.country_code,
            "latitude": float(a.latitude) if a.latitude is not None else None,
            "longitude": float(a.longitude) if a.longitude is not None else None,
            "place_id": a.place_id,
            "verification_status": a.verification_status,
            "is_default": a.is_default,
            "is_active": a.is_active,
            # Generic location hierarchy
            "district": a.district,
            "neighborhood": a.neighborhood,
            "subneighborhood": a.subneighborhood,
            # Flexible metadata for region-specific details
            "location_metadata": a.location_metadata,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        }

    def _normalize_country_code(self, country: Optional[str]) -> str:
        """Best-effort conversion to ISO-3166 alpha-2 code.

        Accepts already-2-letter codes or common full names like 'United States'. Defaults to 'US'.
        """
        try:
            if not country:
                return "US"
            c = str(country).strip()
            if len(c) == 2:
                return c.upper()
            # Common mappings
            mapping = {
                "united states": "US",
                "united states of america": "US",
                "usa": "US",
            }
            m = mapping.get(c.lower())
            if m:
                return m
            return "US"
        except Exception:
            return "US"
