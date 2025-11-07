from abc import ABC
from typing import Any, Optional

from pydantic import BaseModel

class GeocodedAddress(BaseModel):
    latitude: float
    longitude: float
    formatted_address: str
    street_number: Optional[str]
    street_name: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    country: Optional[str]
    neighborhood: Optional[str]
    provider_id: str
    provider_data: dict[str, Any]
    confidence_score: float


class AutocompleteResult(BaseModel):
    text: str
    place_id: str
    description: str
    types: list[str]


class GeocodingProvider(ABC):
    async def geocode(self, address: str) -> Optional[GeocodedAddress]: ...
    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]: ...
    async def autocomplete(
        self,
        query: str,
        session_token: Optional[str] = ...,
        *,
        country: Optional[str] = ...,
        location_bias: Optional[dict[str, float]] = ...,
    ) -> list[AutocompleteResult]: ...
    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]: ...
