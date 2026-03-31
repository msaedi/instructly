"""Teaching location management for InstructorService."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence, cast

from ...core.exceptions import BusinessRuleException
from ...models.instructor import InstructorPreferredPlace
from ..base import BaseService
from .mixin_base import (
    InstructorMixinBase,
    PreparedTeachingLocationGeocode,
    get_instructor_service_module,
)

logger = logging.getLogger(__name__)


class InstructorLocationMixin(InstructorMixinBase):
    """Teaching location management and preferred places."""

    @BaseService.measure_operation("get_instructor_teaching_locations")
    def get_instructor_teaching_locations(
        self, instructor_id: str
    ) -> List[InstructorPreferredPlace]:
        """Get teaching locations from instructor_preferred_places."""
        return self.preferred_place_repository.list_for_instructor_and_kind(
            instructor_id, "teaching_location"
        )

    def _load_existing_places(
        self, instructor_id: str, kind: str
    ) -> dict[str, dict[str, Optional[Any]]]:
        """Load existing teaching locations keyed by normalized address."""
        if kind != "teaching_location":
            return {}

        existing_places_by_address: dict[str, dict[str, Optional[Any]]] = {}
        try:
            existing_places = self.preferred_place_repository.list_for_instructor_and_kind(
                instructor_id, kind
            )
            for place in existing_places:
                address_key = str(place.address or "").strip().lower()
                if not address_key:
                    continue
                existing_places_by_address[address_key] = {
                    "place_id": getattr(place, "place_id", None),
                    "lat": getattr(place, "lat", None),
                    "lng": getattr(place, "lng", None),
                    "approx_lat": getattr(place, "approx_lat", None),
                    "approx_lng": getattr(place, "approx_lng", None),
                    "neighborhood": getattr(place, "neighborhood", None),
                }
        except Exception:
            logger.debug("Non-fatal error loading existing teaching locations", exc_info=True)
        return existing_places_by_address

    def _validate_location_removal(
        self,
        instructor_id: str,
        kind: str,
        items: Sequence[Any],
    ) -> None:
        """Guard against removing the last teaching location for active studio services."""
        if kind != "teaching_location" or items:
            return

        profile = self.profile_repository.get_by_user_id(instructor_id)
        if not profile:
            return

        services = self.service_repository.find_by(
            instructor_profile_id=profile.id,
            is_active=True,
        )
        if any(getattr(service, "offers_at_location", False) for service in services):
            raise BusinessRuleException(
                "You can't remove your last teaching location while you offer lessons at your studio. "
                "Either add another location first, or disable 'Students come to me' on your skills."
            )

    def _normalize_place_inputs(self, items: Sequence[Any]) -> list[tuple[str, Optional[str]]]:
        """Normalize and validate preferred place payloads."""
        normalized: list[tuple[str, Optional[str]]] = []
        seen_addresses: set[str] = set()

        for item in items:
            address = item.address.strip()
            key = address.lower()
            if key in seen_addresses:
                raise BusinessRuleException(
                    "Duplicate addresses are not allowed for preferred places"
                )
            seen_addresses.add(key)

            label = getattr(item, "label", None)
            if label is not None:
                label = label.strip()
                if not label:
                    label = None

            normalized.append((address, label))

        if len(normalized) > 2:
            raise BusinessRuleException("At most two preferred places per category are allowed")
        return normalized

    def _build_teaching_location_fields(
        self,
        address: str,
        existing_places_by_address: dict[str, dict[str, Optional[Any]]],
        geocoded_locations: dict[str, PreparedTeachingLocationGeocode] | None,
    ) -> dict[str, Any]:
        """Build persisted fields for a teaching location row."""
        instructor_service_module = get_instructor_service_module()
        address_key = address.strip().lower()
        existing_place = existing_places_by_address.get(address_key, {})
        place_id = cast(Optional[str], existing_place.get("place_id"))
        lat = cast(Optional[float], existing_place.get("lat"))
        lng = cast(Optional[float], existing_place.get("lng"))
        approx_lat = cast(Optional[float], existing_place.get("approx_lat"))
        approx_lng = cast(Optional[float], existing_place.get("approx_lng"))
        neighborhood = cast(Optional[str], existing_place.get("neighborhood"))

        if approx_lat is None or approx_lng is None:
            if lat is None or lng is None:
                prepared_geocode = (geocoded_locations or {}).get(address_key)
                if prepared_geocode:
                    lat = prepared_geocode.lat
                    lng = prepared_geocode.lng
                    place_id = place_id or prepared_geocode.place_id
                    if not neighborhood:
                        neighborhood = prepared_geocode.neighborhood
                        if not neighborhood:
                            if prepared_geocode.city and prepared_geocode.state:
                                neighborhood = f"{prepared_geocode.city}, {prepared_geocode.state}"
                            elif prepared_geocode.city:
                                neighborhood = prepared_geocode.city

            if lat is not None and lng is not None:
                approx_lat, approx_lng = instructor_service_module.jitter_coordinates(
                    float(lat), float(lng)
                )
                try:
                    enrichment = instructor_service_module.LocationEnrichmentService(
                        self.db
                    ).enrich(float(lat), float(lng))
                    enriched_neighborhood = enrichment.get("neighborhood")
                    district = enrichment.get("district")
                    if enriched_neighborhood:
                        neighborhood = (
                            f"{enriched_neighborhood}, {district}"
                            if district and district not in enriched_neighborhood
                            else enriched_neighborhood
                        )
                    elif district and not neighborhood:
                        neighborhood = district
                    elif neighborhood and district and district not in neighborhood:
                        neighborhood = f"{neighborhood}, {district}"
                except Exception:
                    logger.debug(
                        "Non-fatal location enrichment error for teaching location",
                        exc_info=True,
                    )

        return {
            "place_id": place_id,
            "lat": lat,
            "lng": lng,
            "approx_lat": approx_lat,
            "approx_lng": approx_lng,
            "neighborhood": neighborhood,
        }

    def _build_place_rows(
        self,
        kind: str,
        normalized_places: Sequence[tuple[str, Optional[str]]],
        existing_places_by_address: dict[str, dict[str, Optional[Any]]],
        geocoded_locations: dict[str, PreparedTeachingLocationGeocode] | None,
    ) -> list[dict[str, Any]]:
        """Build normalized preferred-place rows ready for persistence."""
        rows: list[dict[str, Any]] = []
        for position, (address, label) in enumerate(normalized_places):
            row = {
                "address": address,
                "label": label,
                "position": position,
            }
            if kind == "teaching_location":
                row.update(
                    self._build_teaching_location_fields(
                        address,
                        existing_places_by_address,
                        geocoded_locations,
                    )
                )
            rows.append(row)
        return rows

    def _replace_preferred_places(
        self,
        instructor_id: str,
        kind: str,
        items: Sequence[Any],
        *,
        geocoded_locations: dict[str, PreparedTeachingLocationGeocode] | None = None,
    ) -> None:
        """Replace preferred place rows for a given instructor/kind atomically."""
        existing_places_by_address = self._load_existing_places(instructor_id, kind)
        self._validate_location_removal(instructor_id, kind, items)
        normalized_places = self._normalize_place_inputs(items)
        rows = self._build_place_rows(
            kind,
            normalized_places,
            existing_places_by_address,
            geocoded_locations,
        )

        self.preferred_place_repository.delete_for_kind(instructor_id, kind)
        self.preferred_place_repository.flush()
        self.db.expire_all()

        for row in rows:
            self.preferred_place_repository.create_for_kind(
                instructor_id=instructor_id,
                kind=kind,
                address=row["address"],
                label=row["label"],
                position=row["position"],
                place_id=row.get("place_id"),
                lat=row.get("lat"),
                lng=row.get("lng"),
                approx_lat=row.get("approx_lat"),
                approx_lng=row.get("approx_lng"),
                neighborhood=row.get("neighborhood"),
            )
