"""Mapbox geocoding provider."""

import re
from typing import Any, List, Optional
from urllib.parse import quote

import httpx

from ...core.config import settings
from .base import AutocompleteResult, GeocodedAddress, GeocodingProvider


class MapboxProvider(GeocodingProvider):
    def __init__(self) -> None:
        self.access_token = settings.mapbox_access_token
        self.base_url = "https://api.mapbox.com"

    async def geocode(self, address: str) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            encoded = quote(address, safe="")
            resp = await client.get(
                f"{self.base_url}/geocoding/v5/mapbox.places/{encoded}.json",
                params={"access_token": self.access_token, "types": "address,poi,place"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            features = data.get("features") or []
            if not features:
                return None
            return self._parse_feature(features[0])

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            coord = f"{lng},{lat}"
            encoded = quote(coord, safe=",")
            resp = await client.get(
                f"{self.base_url}/geocoding/v5/mapbox.places/{encoded}.json",
                params={"access_token": self.access_token, "types": "address,poi,place"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            features = data.get("features") or []
            if not features:
                return None
            return self._parse_feature(features[0])

    async def autocomplete(
        self,
        query: str,
        session_token: Optional[str] = None,
        *,
        country: Optional[str] = None,
        location_bias: Optional[dict[str, float]] = None,
    ) -> List[AutocompleteResult]:
        async with httpx.AsyncClient(timeout=10) as client:
            encoded = quote(query, safe="")
            params = {
                "access_token": self.access_token,
                "autocomplete": "true",
                "types": "address,poi,place",
            }
            if isinstance(country, str) and country:
                params["country"] = country.lower()
            if location_bias:
                lat = location_bias.get("lat")
                lng = location_bias.get("lng")
                if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                    params["proximity"] = f"{lng},{lat}"
            resp = await client.get(
                f"{self.base_url}/geocoding/v5/mapbox.places/{encoded}.json",
                params=params,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        results: List[AutocompleteResult] = []
        for f in data.get("features", []):
            results.append(
                AutocompleteResult(
                    text=f.get("text", ""),
                    place_id=(f.get("id", "") or ""),
                    description=f.get("place_name", ""),
                    types=[t for t in (f.get("place_type") or [])],
                )
            )
        return results

    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]:
        # Mapbox allows fetching by feature id using the same geocoding endpoint
        clean_id = self._strip_prefix(place_id)
        async with httpx.AsyncClient(timeout=10) as client:
            encoded = quote(clean_id, safe=".")
            resp = await client.get(
                f"{self.base_url}/geocoding/v5/mapbox.places/{encoded}.json",
                params={"access_token": self.access_token},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            features = data.get("features") or []
            if not features:
                return None
            return self._parse_feature(features[0])

    def _parse_feature(self, feature: dict[str, Any]) -> GeocodedAddress:
        center = feature.get("center") or [None, None]
        lng, lat = (center[0], center[1]) if len(center) >= 2 else (None, None)

        raw_context = feature.get("context", []) or []
        context_entries: list[dict[str, Any]] = [
            entry for entry in raw_context if isinstance(entry, dict)
        ]

        def _find_context(pref: str) -> dict[str, Any] | None:
            for entry in context_entries:
                ctx_id = entry.get("id", "")
                if isinstance(ctx_id, str) and ctx_id.startswith(pref):
                    return entry
            return None

        def _context_text(pref: str) -> str | None:
            entry = _find_context(pref)
            value = entry.get("text") if entry else None
            return value if isinstance(value, str) else None

        def _context_code(pref: str) -> str | None:
            entry = _find_context(pref)
            value = entry.get("short_code") if entry else None
            return value if isinstance(value, str) else None

        properties = feature.get("properties") or {}

        house_number = properties.get("address") or feature.get("address")
        street_name = properties.get("street") or feature.get("text")

        house_number = (
            str(house_number).strip() if isinstance(house_number, (str, int, float)) else None
        )
        street_name = (
            str(street_name).strip() if isinstance(street_name, (str, int, float)) else None
        )
        house_number = house_number or None
        street_name = street_name or None

        place_name = feature.get("place_name") or ""
        leading_segment = place_name.split(",", 1)[0].strip()

        if (not house_number or not isinstance(house_number, str)) and leading_segment:
            house_number = properties.get("address") or feature.get("address")

        if (not street_name or not isinstance(street_name, str)) and leading_segment:
            # Attempt to split "320 East 46th Street" into number + street name
            match = re.match(r"^(\d+[A-Za-z]?\b)\s+(.*)$", leading_segment)
            if match:
                number_candidate, street_candidate = match.groups()
                if not house_number:
                    house_number = number_candidate.strip()
                if not street_name:
                    street_name = street_candidate.strip()
            elif not street_name:
                street_name = leading_segment

        city_candidate = _context_text("place.") or _context_text("locality.")
        state_code = _context_code("region.") or _context_text("region.")
        postal_code = _context_text("postcode.")
        country_code = _context_code("country.") or _context_text("country.")
        neighborhood = _context_text("neighborhood.")

        city = city_candidate.strip() if city_candidate else (leading_segment or None)

        state = state_code.strip() if state_code else None
        if state:
            if "-" in state:
                state = state.split("-")[-1]
            state = state.upper()

        postal = postal_code.strip() if postal_code else None

        country = country_code.strip() if country_code else None
        if country:
            if "-" in country:
                country = country.split("-")[-1]
            country = country.upper()
        # Normalize common country names when code missing
        if country and len(country) != 2:
            country = (
                "US"
                if country.lower() in {"united states", "united states of america", "usa"}
                else country[:2].upper()
            )

        provider_id = self._format_provider_id(feature.get("id", ""))

        latitude = float(lat) if isinstance(lat, (int, float)) else 0.0
        longitude = float(lng) if isinstance(lng, (int, float)) else 0.0

        return GeocodedAddress(
            latitude=latitude,
            longitude=longitude,
            formatted_address=place_name,
            street_number=house_number,
            street_name=street_name,
            city=city,
            state=state,
            postal_code=postal,
            country=country,
            neighborhood=neighborhood,
            provider_id=provider_id,
            provider_data=feature,
            confidence_score=float(feature.get("relevance", 1.0)),
        )

    @staticmethod
    def _format_provider_id(place_id: str) -> str:
        if not place_id:
            return ""
        return place_id if place_id.startswith("mapbox:") else f"mapbox:{place_id}"

    @staticmethod
    def _strip_prefix(place_id: str) -> str:
        if place_id.startswith("mapbox:"):
            return place_id.split(":", 1)[1]
        return place_id
