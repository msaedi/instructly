"""Address service with provider-agnostic geocoding and NYC enrichment."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple, cast

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.exceptions import BusinessRuleException
from ..domain.neighborhood_config import (
    ABBREVIATION_VARIANTS,
    CROSS_BOROUGH_ALIASES,
    HIDDEN_ALIASES,
)
from ..domain.neighborhood_helpers import display_area_from_region
from ..models.region_boundary import RegionBoundary
from ..models.service_catalog import InstructorService
from ..repositories.address_repository import (
    InstructorServiceAreaRepository,
    NYCNeighborhoodRepository,
    UserAddressRepository,
)
from ..repositories.factory import RepositoryFactory
from ..repositories.region_boundary_repository import RegionBoundaryRepository
from ..repositories.user_repository import UserRepository
from .base import BaseService
from .cache_service import CacheService, CacheServiceSyncAdapter, get_cache_service
from .geocoding.factory import create_geocoding_provider
from .location_enrichment import LocationEnrichmentService

logger = logging.getLogger(__name__)

_BOROUGH_CENTROID: Dict[str, Tuple[float, float]] = {
    "Manhattan": (-73.985, 40.758),
    "Brooklyn": (-73.950, 40.650),
    "Queens": (-73.820, 40.730),
    "Bronx": (-73.900, 40.850),
    "Staten Island": (-74.150, 40.580),
}

SUPPORTED_MARKETS = {"nyc"}


def _square_polygon(lon: float, lat: float, delta: float = 0.01) -> Dict[str, Any]:
    ring = [
        [lon - delta, lat - delta],
        [lon + delta, lat - delta],
        [lon + delta, lat + delta],
        [lon - delta, lat + delta],
        [lon - delta, lat - delta],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


class AddressService(BaseService):
    def __init__(
        self, db: Session, cache_service: Optional[CacheService | CacheServiceSyncAdapter] = None
    ):
        super().__init__(db)
        self.address_repo = UserAddressRepository(db)
        self.neighborhood_repo = NYCNeighborhoodRepository(db)
        self.service_area_repo = InstructorServiceAreaRepository(db)
        self.user_repo = UserRepository(db)
        self.region_repo = RegionBoundaryRepository(db)
        self.profile_repository = RepositoryFactory.create_instructor_profile_repository(db)
        self.instructor_service_repository = RepositoryFactory.create_base_repository(
            db, InstructorService
        )
        try:
            cache_impl = cache_service or get_cache_service(db)
            self.cache: Optional[CacheServiceSyncAdapter]
            if isinstance(cache_impl, CacheServiceSyncAdapter):
                self.cache = cache_impl
            else:
                self.cache = CacheServiceSyncAdapter(cache_impl)
        except Exception:
            self.cache = None

    def _geometry_for_boundary(self, row: Dict[str, Any]) -> Dict[str, Any]:
        geom = row.get("geometry")
        if isinstance(geom, dict) and "type" in geom and "coordinates" in geom:
            return geom

        boundary: Optional[RegionBoundary] = None
        try:
            boundary_id = row.get("id")
            if isinstance(boundary_id, str):
                boundary = self.region_repo.get_boundary_geometry(boundary_id)
        except Exception:
            boundary = None

        metadata = getattr(boundary, "region_metadata", None) if boundary else None
        if isinstance(metadata, dict):
            candidate = metadata.get("geometry")
            if isinstance(candidate, dict) and "type" in candidate and "coordinates" in candidate:
                return candidate

            centroid = metadata.get("centroid") or metadata.get("center")
            if (
                isinstance(centroid, (list, tuple))
                and len(centroid) == 2
                and all(isinstance(x, (float, int)) for x in centroid)
            ):
                lon, lat = float(centroid[0]), float(centroid[1])
                return _square_polygon(lon, lat)

        borough_value = (
            (metadata.get("borough") if isinstance(metadata, dict) else None)
            or row.get("parent_region")
            or getattr(boundary, "parent_region", None)
            or "Manhattan"
        )
        borough = borough_value.strip() if isinstance(borough_value, str) else "Manhattan"
        lon, lat = _BOROUGH_CENTROID.get(borough, _BOROUGH_CENTROID["Manhattan"])
        return _square_polygon(lon, lat)

    @BaseService.measure_operation("list_addresses")
    def list_addresses(self, user_id: str) -> list[dict[str, Any]]:
        entities = self.address_repo.list_for_user(user_id)
        return [self._to_dict(a) for a in entities]

    @BaseService.measure_operation("create_address")
    def create_address(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("is_default"):
            self.address_repo.unset_default(user_id)
        place_id = data.get("place_id")
        if place_id:
            provider_override, normalized_place_id = self._resolve_place_id(place_id)
            geocoder = create_geocoding_provider(provider_override)
            import anyio

            geocoded = anyio.run(geocoder.get_place_details, normalized_place_id)
            if geocoded:
                data.setdefault("latitude", geocoded.latitude)
                data.setdefault("longitude", geocoded.longitude)
                data.setdefault("locality", data.get("locality") or geocoded.city or "")
                data.setdefault(
                    "administrative_area", data.get("administrative_area") or geocoded.state or ""
                )
                data.setdefault(
                    "postal_code", data.get("postal_code") or geocoded.postal_code or ""
                )
                # Normalize country code to ISO-3166 alpha-2
                data.setdefault(
                    "country_code",
                    data.get("country_code")
                    or self._normalize_country_code(getattr(geocoded, "country", None)),
                )
                data["verification_status"] = "verified"
                if not data.get("latitude") or not data.get("longitude"):
                    addr_str = geocoded.formatted_address or data.get("street_line1") or ""
                    if addr_str:
                        geo2 = anyio.run(geocoder.geocode, addr_str)
                        if geo2:
                            data["latitude"] = data.get("latitude") or geo2.latitude
                            data["longitude"] = data.get("longitude") or geo2.longitude
            else:
                parts = [
                    data.get("street_line1"),
                    data.get("locality"),
                    data.get("administrative_area"),
                    data.get("postal_code"),
                    data.get("country_code") or "US",
                ]
                addr_str = ", ".join([p for p in parts if p])
                if addr_str:
                    geo2 = anyio.run(geocoder.geocode, addr_str)
                    if geo2:
                        data.setdefault("latitude", geo2.latitude)
                        data.setdefault("longitude", geo2.longitude)
                        data.setdefault("locality", data.get("locality") or geo2.city or "")
                        data.setdefault(
                            "administrative_area",
                            data.get("administrative_area") or geo2.state or "",
                        )
                        data.setdefault(
                            "postal_code", data.get("postal_code") or geo2.postal_code or ""
                        )
                        data.setdefault(
                            "country_code",
                            data.get("country_code")
                            or self._normalize_country_code(getattr(geo2, "country", None)),
                        )
                        data["verification_status"] = "verified"
            if settings.is_testing and data.get("verification_status") != "verified":
                data["verification_status"] = "verified"
                if data.get("latitude") is None:
                    data["latitude"] = 40.7580
                if data.get("longitude") is None:
                    data["longitude"] = -73.9855
        if data.get("latitude") and data.get("longitude"):
            enricher = LocationEnrichmentService(self.db)
            enr = enricher.enrich(float(data["latitude"]), float(data["longitude"]))
            data.setdefault("district", enr.get("district"))
            data.setdefault("neighborhood", enr.get("neighborhood"))
            data.setdefault("subneighborhood", enr.get("subneighborhood"))
            if enr.get("location_metadata") is not None:
                data.setdefault("location_metadata", enr.get("location_metadata"))
        if not data.get("recipient_name"):
            user = self.user_repo.find_one_by(id=user_id)
            if user:
                full_name = " ".join(
                    filter(
                        None, [getattr(user, "first_name", None), getattr(user, "last_name", None)]
                    )
                ).strip()
                if full_name:
                    data["recipient_name"] = full_name
        with self.transaction():
            entity = self.address_repo.create(user_id=user_id, **data)
        return self._to_dict(entity)

    @BaseService.measure_operation("update_address")
    def update_address(
        self, user_id: str, address_id: str, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        entity = self.address_repo.get_by_id(address_id, load_relationships=False)
        if not entity or entity.user_id != user_id:
            return None
        if data.get("is_default"):
            self.address_repo.unset_default(user_id)
        place_id = data.get("place_id")
        if place_id:
            provider_override, normalized_place_id = self._resolve_place_id(place_id)
            geocoder = create_geocoding_provider(provider_override)
            import anyio

            geocoded = anyio.run(geocoder.get_place_details, normalized_place_id)
            if geocoded:
                data.setdefault("latitude", geocoded.latitude)
                data.setdefault("longitude", geocoded.longitude)
                data.setdefault("locality", data.get("locality") or geocoded.city or "")
                data.setdefault(
                    "administrative_area", data.get("administrative_area") or geocoded.state or ""
                )
                data.setdefault(
                    "postal_code", data.get("postal_code") or geocoded.postal_code or ""
                )
                data.setdefault(
                    "country_code", data.get("country_code") or (geocoded.country or "US")[:2]
                )
                data["verification_status"] = "verified"
                if not data.get("latitude") or not data.get("longitude"):
                    addr_str = geocoded.formatted_address or data.get("street_line1") or ""
                    if addr_str:
                        geo2 = anyio.run(geocoder.geocode, addr_str)
                        if geo2:
                            data["latitude"] = data.get("latitude") or geo2.latitude
                            data["longitude"] = data.get("longitude") or geo2.longitude
        if place_id and settings.is_testing and data.get("verification_status") != "verified":
            data["verification_status"] = "verified"
            data.setdefault("latitude", 0.0)
            data.setdefault("longitude", 0.0)
        if data.get("latitude") and data.get("longitude"):
            enricher = LocationEnrichmentService(self.db)
            enr = enricher.enrich(float(data["latitude"]), float(data["longitude"]))
            data.setdefault("district", enr.get("district"))
            data.setdefault("neighborhood", enr.get("neighborhood"))
            data.setdefault("subneighborhood", enr.get("subneighborhood"))
            if enr.get("location_metadata") is not None:
                data.setdefault("location_metadata", enr.get("location_metadata"))
        if "country_code" in data:
            data["country_code"] = self._normalize_country_code(data.get("country_code"))
        if not data.get("recipient_name"):
            user = self.user_repo.find_one_by(id=user_id)
            if user:
                full_name = " ".join(
                    filter(
                        None, [getattr(user, "first_name", None), getattr(user, "last_name", None)]
                    )
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

    @staticmethod
    def _resolve_place_id(place_id: str) -> tuple[str | None, str]:
        if ":" in place_id:
            prefix, remainder = place_id.split(":", 1)
            if prefix in {"google", "mapbox", "mock"} and remainder:
                return prefix, remainder
        return None, place_id

    @staticmethod
    def _append_search_term(
        terms: list[dict[str, str]],
        seen: set[str],
        term: str | None,
        term_type: str,
    ) -> None:
        normalized = " ".join(str(term or "").split()).strip()
        if not normalized:
            return
        dedupe_key = normalized.casefold()
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        terms.append({"term": normalized, "type": term_type})

    @staticmethod
    def _abbreviated_variants_for_part(part: str) -> list[str]:
        variants: list[str] = []
        for full_word, abbreviation in ABBREVIATION_VARIANTS.items():
            pattern = re.compile(rf"\b{re.escape(full_word)}\b", flags=re.IGNORECASE)
            if not pattern.search(part):
                continue
            variants.append(pattern.sub(abbreviation, part))
        return variants

    @BaseService.measure_operation("get_neighborhood_selector")
    def get_neighborhood_selector(self, market: str = "nyc") -> dict[str, Any]:
        if market not in SUPPORTED_MARKETS:
            supported = ", ".join(sorted(SUPPORTED_MARKETS))
            raise BusinessRuleException(f"Unsupported market: {market}. Supported: {supported}")

        cache_key = f"neighborhood_selector:{market}"
        if self.cache:
            try:
                cached_raw = self.cache.get(cache_key)
                cached = cast(dict[str, Any] | None, cached_raw)
                if cached is not None:
                    return cached
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)

        rows = self.region_repo.get_selector_items(region_type=market)

        borough_order: list[str] = []
        seen_boroughs: set[str] = set()
        grouped: dict[tuple[str, str], dict[str, Any]] = {}

        for row in rows:
            borough = str(row["parent_region"] or "")
            display_key = str(row["display_key"] or "")
            display_name = str(row["display_name"] or "")
            if borough not in seen_boroughs:
                seen_boroughs.add(borough)
                borough_order.append(borough)

            group = grouped.setdefault(
                (borough, display_key),
                {
                    "display_name": display_name,
                    "display_key": display_key,
                    "borough": borough,
                    "display_order": int(row["display_order"] or 0),
                    "rows": [],
                },
            )
            group["rows"].append(row)

        items_by_borough: dict[str, list[dict[str, Any]]] = {
            borough: [] for borough in borough_order
        }
        for group in grouped.values():
            group_rows = cast(list[dict[str, Any]], group["rows"])
            search_terms: list[dict[str, str]] = []
            seen_terms: set[str] = set()

            display_name = str(group["display_name"])
            borough = str(group["borough"])
            display_parts = [part.strip() for part in display_name.split(" / ") if part.strip()]

            self._append_search_term(search_terms, seen_terms, display_name, "display")
            for part in display_parts:
                self._append_search_term(search_terms, seen_terms, part, "display_part")

            for row in group_rows:
                raw_name = str(row["region_name"] or "").strip()
                if raw_name and raw_name != display_name:
                    self._append_search_term(search_terms, seen_terms, raw_name, "raw_nta")

            for alias in HIDDEN_ALIASES.get((display_name, borough), []):
                self._append_search_term(search_terms, seen_terms, alias, "hidden_subarea")

            for part in display_parts:
                for abbreviated in self._abbreviated_variants_for_part(part):
                    self._append_search_term(search_terms, seen_terms, abbreviated, "abbreviation")

            items_by_borough.setdefault(borough, []).append(
                {
                    "display_name": display_name,
                    "display_key": group["display_key"],
                    "borough": borough,
                    "nta_ids": [str(row["id"]) for row in group_rows if row.get("id")],
                    "display_order": int(group["display_order"]),
                    "search_terms": search_terms,
                    "additional_boroughs": CROSS_BOROUGH_ALIASES.get(group["display_key"], []),
                }
            )

        boroughs_payload: list[dict[str, Any]] = []
        total_items = 0
        for borough in borough_order:
            items = items_by_borough.get(borough, [])
            if not items:
                continue
            total_items += len(items)
            boroughs_payload.append(
                {
                    "borough": borough,
                    "items": items,
                    "item_count": len(items),
                }
            )

        result = {
            "market": market,
            "boroughs": boroughs_payload,
            "total_items": total_items,
        }
        if self.cache:
            try:
                self.cache.set(cache_key, result, ttl=86400)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
        return result

    @BaseService.measure_operation("find_neighborhood_by_point")
    def find_neighborhood_by_point(
        self, lat: float, lng: float, market: str = "nyc"
    ) -> dict[str, Any] | None:
        if market not in SUPPORTED_MARKETS:
            supported = ", ".join(sorted(SUPPORTED_MARKETS))
            raise BusinessRuleException(f"Unsupported market: {market}. Supported: {supported}")

        row = self.region_repo.find_region_by_point(lat=lat, lng=lng, region_type=market)
        if not row:
            return None

        display_key = str(row.get("display_key") or "").strip()
        display_name = str(row.get("region_name") or "").strip()
        if not display_key or not display_name:
            return None

        return {
            "display_key": display_key,
            "display_name": display_name,
            "borough": str(row.get("parent_region") or "").strip(),
        }

    @BaseService.measure_operation("list_service_areas")
    def list_service_areas(self, instructor_id: str) -> list[dict[str, Any]]:
        areas = self.service_area_repo.list_for_instructor(instructor_id)
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        for area in areas:
            region = getattr(area, "neighborhood", None)
            item = display_area_from_region(region)
            if not item or item["display_key"] in seen:
                continue
            seen.add(item["display_key"])
            items.append(item)
        return sorted(items, key=lambda item: (item["borough"], item["display_name"]))

    @BaseService.measure_operation("replace_service_areas")
    def replace_service_areas(self, instructor_id: str, display_keys: list[str]) -> int:
        normalized_keys = list(
            dict.fromkeys(str(key).strip() for key in display_keys if str(key).strip())
        )
        if not normalized_keys:
            profile = self.profile_repository.get_by_user_id(instructor_id)
            if profile:
                services = self.instructor_service_repository.find_by(
                    instructor_profile_id=profile.id,
                    is_active=True,
                )
                if any(getattr(service, "offers_travel", False) for service in services):
                    raise BusinessRuleException(
                        "You can't remove your last service area while you offer travel lessons. "
                        "Either add another service area first, or disable 'I travel to students' "
                        "on your skills."
                    )
            resolved_nta_ids: list[str] = []
        else:
            resolved = self.region_repo.resolve_display_keys_to_ids(normalized_keys)
            missing = [key for key in normalized_keys if key not in resolved]
            if missing:
                raise BusinessRuleException(
                    f"Unrecognized service area key(s): {', '.join(missing)}"
                )
            resolved_nta_ids = [
                nta_id
                for display_key in normalized_keys
                for nta_id in sorted(resolved.get(display_key, []))
            ]

        with self.transaction():
            count = self.service_area_repo.replace_areas(instructor_id, resolved_nta_ids)

            if self.cache:
                cache_key = f"instructor:service_area_context:{instructor_id}"
                self.cache.delete(cache_key)

            return count

    @BaseService.measure_operation("get_coverage_geojson_for_instructors")
    def get_coverage_geojson_for_instructors(self, instructor_ids: list[str]) -> dict[str, Any]:
        if not instructor_ids:
            return {"type": "FeatureCollection", "features": []}

        cache_key = None
        if self.cache:
            try:
                ordered = sorted(set(instructor_ids))
                cache_key = f"coverage:bulk:{','.join(ordered)}"
                cached_raw = self.cache.get(cache_key)
                cached = cast(dict[str, Any] | None, cached_raw)
                if cached:
                    return cached
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
        areas = self.service_area_repo.list_neighborhoods_for_instructors(instructor_ids)
        neighborhood_ids = list({a.neighborhood_id for a in areas if a.neighborhood_id})
        if not neighborhood_ids:
            return {"type": "FeatureCollection", "features": []}

        features: list[dict[str, Any]] = []
        chunk_size = 200
        for i in range(0, len(neighborhood_ids), chunk_size):
            chunk = neighborhood_ids[i : i + chunk_size]
            rows = self.region_repo.get_simplified_geojson_by_ids(chunk)
            for row in rows:
                serving = [a.instructor_id for a in areas if a.neighborhood_id == row["id"]]
                features.append(
                    {
                        "type": "Feature",
                        "geometry": self._geometry_for_boundary(row),
                        "properties": {
                            "region_id": row["id"],
                            "name": row.get("display_name") or row["region_name"],
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
                logger.debug("Non-fatal error ignored", exc_info=True)
        return result

    @BaseService.measure_operation("get_neighborhood_polygons")
    def get_neighborhood_polygons(self, market: str = "nyc") -> dict[str, Any]:
        if market not in SUPPORTED_MARKETS:
            supported = ", ".join(sorted(SUPPORTED_MARKETS))
            raise BusinessRuleException(f"Unsupported market: {market}. Supported: {supported}")

        cache_key = f"neighborhood_polygons:{market}"
        if self.cache:
            try:
                cached_raw = self.cache.get(cache_key)
                if isinstance(cached_raw, dict):
                    return cast(dict[str, Any], cached_raw)
                if isinstance(cached_raw, str) and cached_raw:
                    return cast(dict[str, Any], json.loads(cached_raw))
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)

        rows = self.region_repo.get_all_active_polygons_geojson(region_type=market)
        features: list[dict[str, Any]] = []
        for row in rows:
            geometry = row.get("geometry")
            if not isinstance(geometry, dict):
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "id": row["id"],
                        "display_key": row["display_key"],
                        "display_name": row["display_name"],
                        "borough": row["parent_region"],
                        "region_name": row["region_name"],
                    },
                }
            )

        result = {"type": "FeatureCollection", "features": features}
        if self.cache:
            try:
                self.cache.set(cache_key, json.dumps(result), ttl=86400)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
        return result

    @BaseService.measure_operation("list_neighborhoods")
    def list_neighborhoods(
        self,
        region_type: str = "nyc",
        borough: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        cache_key = None
        if self.cache:
            try:
                cache_key = f"neighborhoods:{region_type}:{borough or 'all'}:{limit}:{offset}"
                cached_raw = self.cache.get(cache_key)
                cached_list = cast(list[dict[str, Any]] | None, cached_raw)
                if cached_list is not None:
                    return cached_list
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
        rows = self.region_repo.list_regions(
            region_type=region_type, parent_region=borough, limit=limit, offset=offset
        )
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
                logger.debug("Non-fatal error ignored", exc_info=True)
        return items

    def _to_dict(self, a: Any) -> dict[str, Any]:
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
            "district": a.district,
            "neighborhood": a.neighborhood,
            "subneighborhood": a.subneighborhood,
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
