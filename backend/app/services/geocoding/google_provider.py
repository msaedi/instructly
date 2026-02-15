"""Google Maps geocoding provider."""

import logging
from typing import Any, List, Optional

import httpx

from ...core.config import secret_or_plain, settings
from .base import (
    AutocompleteResult,
    GeocodedAddress,
    GeocodingProvider,
    GeocodingProviderError,
)
from .mapbox_provider import MapboxProvider

logger = logging.getLogger(__name__)


class GoogleMapsProvider(GeocodingProvider):
    def __init__(self) -> None:
        self.api_key = secret_or_plain(settings.google_maps_api_key).strip()
        self.base_url = "https://maps.googleapis.com/maps/api"
        self.provider_name = "google_geocode"

    async def geocode(self, address: str) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/geocode/json", params={"address": address, "key": self.api_key}
            )
            if resp.status_code != 200:
                raise GeocodingProviderError(
                    provider=self.provider_name,
                    status=f"HTTP_{resp.status_code}",
                    message="Non-200 response from Google Geocoding API",
                    payload={"zip": address},
                )
            data = resp.json()
            status = data.get("status", "")
            if status == "OK":
                results = data.get("results") or []
                if not results:
                    return None
                return self._parse_result(results[0])
            if status == "ZERO_RESULTS":
                return None
            raise GeocodingProviderError(
                provider=self.provider_name,
                status=status or "UNKNOWN_STATUS",
                message=data.get("error_message"),
                payload={"zip": address},
            )

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/geocode/json",
                params={"latlng": f"{lat},{lng}", "key": self.api_key},
            )
            if resp.status_code != 200:
                raise GeocodingProviderError(
                    provider=self.provider_name,
                    status=f"HTTP_{resp.status_code}",
                    message="Non-200 response from Google Geocoding API",
                    payload={"lat": lat, "lng": lng},
                )
            data = resp.json()
            status = data.get("status", "")
            if status == "OK":
                results = data.get("results") or []
                if not results:
                    return None
                return self._parse_result(results[0])
            if status == "ZERO_RESULTS":
                return None
            raise GeocodingProviderError(
                provider=self.provider_name,
                status=status or "UNKNOWN_STATUS",
                message=data.get("error_message"),
                payload={"lat": lat, "lng": lng},
            )

    async def autocomplete(
        self,
        query: str,
        session_token: Optional[str] = None,
        *,
        country: Optional[str] = None,
        location_bias: Optional[dict[str, float]] = None,
    ) -> List[AutocompleteResult]:
        async with httpx.AsyncClient(timeout=10) as client:
            params = {"input": query, "key": self.api_key, "types": "address"}
            if session_token:
                params["sessiontoken"] = session_token
            if country:
                params["components"] = f"country:{country.lower()}"
            if location_bias:
                lat = location_bias.get("lat")
                lng = location_bias.get("lng")
                radius = location_bias.get("radius_m") or 50000
                if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                    try:
                        radius_int = int(radius)
                    except (TypeError, ValueError):
                        radius_int = 50000
                    params["locationbias"] = f"circle:{max(radius_int, 1000)}@{lat},{lng}"
            resp = await client.get(f"{self.base_url}/place/autocomplete/json", params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            status = data.get("status")
            results: List[AutocompleteResult] = []
            for p in data.get("predictions", []):
                results.append(
                    AutocompleteResult(
                        text=p.get("structured_formatting", {}).get("main_text", ""),
                        place_id=p.get("place_id", "") or "",
                        description=p.get("description", ""),
                        types=p.get("types", []),
                    )
                )
            if results or status in {"OK", "ZERO_RESULTS"}:
                return results

            # Attempt graceful fallback to Mapbox when Google denies the request (e.g. disabled key)
            logger.warning(
                "Google Places autocomplete returned status %s; attempting Mapbox fallback", status
            )
            if secret_or_plain(settings.mapbox_access_token).strip():
                fallback = MapboxProvider()
                return await fallback.autocomplete(
                    query,
                    session_token=session_token,
                    country=country,
                    location_bias=location_bias,
                )
            return []

    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]:
        clean_id = self._strip_prefix(place_id)
        async with httpx.AsyncClient(timeout=10) as client:
            # Use correct field names per Google Places Details API
            # https://developers.google.com/maps/documentation/places/web-service/details
            fields = "formatted_address,geometry,address_components,place_id"
            resp = await client.get(
                f"{self.base_url}/place/details/json",
                params={
                    "place_id": clean_id,
                    "key": self.api_key,
                    "fields": fields,
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("result")
            if not result:
                return None
            parsed = self._parse_result(result)
            # Treat (0.0, 0.0) as missing coords
            if (parsed.latitude or 0.0) == 0.0 and (parsed.longitude or 0.0) == 0.0:
                return None
            return parsed

    def _parse_result(self, result: dict[str, Any]) -> GeocodedAddress:
        comps: dict[str, str] = {}
        short_comps: dict[str, str] = {}
        # Google returns 'address_components' in Details; support both keys defensively
        addr_components = result.get("address_components") or result.get("address_component") or []
        for c in addr_components:
            long_name = c.get("long_name")
            short_name = c.get("short_name")
            for t in c.get("types", []):
                if isinstance(long_name, str) and long_name:
                    comps[t] = long_name
                if isinstance(short_name, str) and short_name:
                    short_comps[t] = short_name
        geom = result.get("geometry", {})
        loc = geom.get("location", {})
        # Normalize country to ISO alpha-2 if Google returns full name
        raw_country = comps.get("country")
        country_short = short_comps.get("country")
        country_code = None
        if country_short and len(country_short) == 2:
            country_code = country_short.upper()
        elif raw_country:
            if len(raw_country) == 2:
                country_code = raw_country.upper()
            else:
                country_code = (
                    "US"
                    if raw_country.lower() in {"united states", "united states of america", "usa"}
                    else raw_country[:2].upper()
                )

        provider_id = self._format_provider_id(result.get("place_id", ""))
        return GeocodedAddress(
            latitude=loc.get("lat", 0.0),
            longitude=loc.get("lng", 0.0),
            formatted_address=result.get("formatted_address", ""),
            street_number=comps.get("street_number"),
            street_name=comps.get("route"),
            city=comps.get("locality") or comps.get("postal_town") or comps.get("sublocality"),
            state=short_comps.get("administrative_area_level_1")
            or comps.get("administrative_area_level_1"),
            postal_code=comps.get("postal_code"),
            country=country_code or comps.get("country"),
            neighborhood=comps.get("neighborhood"),
            provider_id=provider_id,
            provider_data=result,
            confidence_score=1.0,
        )

    @staticmethod
    def _format_provider_id(place_id: str) -> str:
        if not place_id:
            return ""
        return place_id if place_id.startswith("google:") else f"google:{place_id}"

    @staticmethod
    def _strip_prefix(place_id: str) -> str:
        if place_id.startswith("google:"):
            return place_id.split(":", 1)[1]
        return place_id
