"""Mapbox geocoding provider."""

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
        self, query: str, session_token: Optional[str] = None
    ) -> List[AutocompleteResult]:
        async with httpx.AsyncClient(timeout=10) as client:
            encoded = quote(query, safe="")
            resp = await client.get(
                f"{self.base_url}/geocoding/v5/mapbox.places/{encoded}.json",
                params={
                    "access_token": self.access_token,
                    "autocomplete": "true",
                    "types": "address,poi,place",
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results: List[AutocompleteResult] = []
            for f in data.get("features", []):
                results.append(
                    AutocompleteResult(
                        text=f.get("text", ""),
                        place_id=f.get("id", ""),
                        description=f.get("place_name", ""),
                        types=[t for t in (f.get("place_type") or [])],
                    )
                )
            return results

    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]:
        # Mapbox allows fetching by feature id using the same geocoding endpoint
        async with httpx.AsyncClient(timeout=10) as client:
            encoded = quote(place_id, safe=".")
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
        context = {
            (c.get("id", "").split(".")[0]): c.get("text") for c in feature.get("context", [])
        }
        # Some fields may be directly on the feature
        city = context.get("place") or context.get("locality") or feature.get("place_name")
        state = context.get("region")
        postal = context.get("postcode")
        country = context.get("country")
        neighborhood = context.get("neighborhood")
        # Normalize country to ISO alpha-2 if Mapbox returned full name
        raw_country = country
        if raw_country and len(raw_country) != 2:
            country = (
                "US"
                if raw_country.lower() in {"united states", "united states of america", "usa"}
                else raw_country[:2].upper()
            )
        return GeocodedAddress(
            latitude=lat,
            longitude=lng,
            formatted_address=feature.get("place_name", ""),
            street_number=feature.get("address"),
            street_name=feature.get("text"),
            city=city,
            state=state,
            postal_code=postal,
            country=country,
            neighborhood=neighborhood,
            provider_id=feature.get("id", ""),
            provider_data=feature,
            confidence_score=float(feature.get("relevance", 1.0)),
        )
