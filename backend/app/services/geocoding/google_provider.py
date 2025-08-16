"""Google Maps geocoding provider."""

from typing import List, Optional

import httpx

from ...core.config import settings
from .base import AutocompleteResult, GeocodedAddress, GeocodingProvider


class GoogleMapsProvider(GeocodingProvider):
    def __init__(self):
        self.api_key = settings.google_maps_api_key
        self.base_url = "https://maps.googleapis.com/maps/api"

    async def geocode(self, address: str) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/geocode/json", params={"address": address, "key": self.api_key})
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("results"):
                return None
            return self._parse_result(data["results"][0])

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/geocode/json",
                params={"latlng": f"{lat},{lng}", "key": self.api_key},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("results"):
                return None
            return self._parse_result(data["results"][0])

    async def autocomplete(self, query: str, session_token: Optional[str] = None) -> List[AutocompleteResult]:
        async with httpx.AsyncClient(timeout=10) as client:
            params = {"input": query, "key": self.api_key, "types": "address"}
            if session_token:
                params["sessiontoken"] = session_token
            resp = await client.get(f"{self.base_url}/place/autocomplete/json", params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            for p in data.get("predictions", []):
                results.append(
                    AutocompleteResult(
                        text=p.get("structured_formatting", {}).get("main_text", ""),
                        place_id=p.get("place_id", ""),
                        description=p.get("description", ""),
                        types=p.get("types", []),
                    )
                )
            return results

    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/place/details/json",
                params={
                    "place_id": place_id,
                    "key": self.api_key,
                    "fields": "formatted_address,geometry,address_component,place_id",
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("result")
            if not result:
                return None
            return self._parse_result(result)

    def _parse_result(self, result: dict) -> GeocodedAddress:
        comps = {}
        for c in result.get("address_components", []):
            for t in c.get("types", []):
                comps[t] = c.get("long_name")
        geom = result.get("geometry", {})
        loc = geom.get("location", {})
        # Normalize country to ISO alpha-2 if Google returns full name
        raw_country = comps.get("country")
        country_code = None
        if raw_country:
            if len(raw_country) == 2:
                country_code = raw_country.upper()
            else:
                country_code = (
                    "US"
                    if raw_country.lower() in {"united states", "united states of america", "usa"}
                    else raw_country[:2].upper()
                )
        return GeocodedAddress(
            latitude=loc.get("lat", 0.0),
            longitude=loc.get("lng", 0.0),
            formatted_address=result.get("formatted_address", ""),
            street_number=comps.get("street_number"),
            street_name=comps.get("route"),
            city=comps.get("locality") or comps.get("sublocality") or comps.get("postal_town"),
            state=comps.get("administrative_area_level_1"),
            postal_code=comps.get("postal_code"),
            country=country_code or comps.get("country"),
            neighborhood=comps.get("neighborhood"),
            provider_id=result.get("place_id", ""),
            provider_data=result,
            confidence_score=1.0,
        )
