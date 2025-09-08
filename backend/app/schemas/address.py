"""Pydantic schemas for user addresses and service areas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AddressBase(BaseModel):
    label: Optional[str] = Field(None, description="home|work|other")
    custom_label: Optional[str] = None
    recipient_name: Optional[str] = None
    street_line1: str
    street_line2: Optional[str] = None
    locality: str
    administrative_area: str
    postal_code: str
    country_code: str = "US"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_id: Optional[str] = None
    verification_status: Optional[str] = "unverified"
    is_default: bool = False


class AddressCreate(AddressBase):
    pass


class AddressUpdate(BaseModel):
    label: Optional[str] = None
    custom_label: Optional[str] = None
    recipient_name: Optional[str] = None
    street_line1: Optional[str] = None
    street_line2: Optional[str] = None
    locality: Optional[str] = None
    administrative_area: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_id: Optional[str] = None
    verification_status: Optional[str] = None
    is_default: Optional[bool] = None


class AddressResponse(AddressBase):
    id: str
    is_active: bool
    district: Optional[str] = None
    neighborhood: Optional[str] = None
    subneighborhood: Optional[str] = None
    location_metadata: Optional[Dict[str, Any]] = None


class AddressListResponse(BaseModel):
    items: List[AddressResponse]
    total: int


class ServiceAreasUpdateRequest(BaseModel):
    neighborhood_ids: List[str]


class ServiceAreaItem(BaseModel):
    neighborhood_id: str
    ntacode: Optional[str] = None
    name: Optional[str] = None
    borough: Optional[str] = None


class ServiceAreasResponse(BaseModel):
    items: List[ServiceAreaItem]
    total: int


class PlaceSuggestion(BaseModel):
    text: str
    place_id: str
    description: str
    types: List[str] = []


class AutocompleteResponse(BaseModel):
    items: List[PlaceSuggestion]
    total: int


class PlaceDetails(BaseModel):
    formatted_address: str
    latitude: float
    longitude: float
    street_number: Optional[str] = None
    street_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    provider_id: str
