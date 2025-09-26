"""Provider-agnostic geocoding interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


class GeocodedAddress(BaseModel):
    latitude: float
    longitude: float
    formatted_address: str
    street_number: Optional[str] = None
    street_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    neighborhood: Optional[str] = None
    provider_id: str
    provider_data: dict[str, Any]
    confidence_score: float = 1.0


class AutocompleteResult(BaseModel):
    text: str
    place_id: str
    description: str
    types: list[str] = []


class GeocodingProvider(ABC):
    @abstractmethod
    async def geocode(self, address: str) -> Optional[GeocodedAddress]:
        pass

    @abstractmethod
    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]:
        pass

    @abstractmethod
    async def autocomplete(
        self, query: str, session_token: Optional[str] = None
    ) -> list[AutocompleteResult]:
        pass

    @abstractmethod
    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]:
        pass
