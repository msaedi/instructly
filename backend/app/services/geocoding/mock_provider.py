"""Mock geocoding provider for unit tests (no network calls)."""

from typing import List, Optional

from .base import AutocompleteResult, GeocodedAddress, GeocodingProvider


class MockGeocodingProvider(GeocodingProvider):
    async def geocode(self, address: str) -> Optional[GeocodedAddress]:
        # Return a deterministic coordinate for any input
        return GeocodedAddress(
            latitude=40.7580,
            longitude=-73.9855,
            formatted_address=address or "Mock Address, New York, NY 10036, USA",
            street_number="1",
            street_name="Mock St",
            city="New York",
            state="NY",
            postal_code="10036",
            country="US",
            neighborhood="Midtown",
            provider_id="mock:geocode",
            provider_data={"source": "mock"},
            confidence_score=1.0,
        )

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]:
        return GeocodedAddress(
            latitude=lat,
            longitude=lng,
            formatted_address="Reverse Mock Address, New York, NY 10036, USA",
            street_number="1",
            street_name="Mock St",
            city="New York",
            state="NY",
            postal_code="10036",
            country="US",
            neighborhood="Midtown",
            provider_id="mock:reverse",
            provider_data={"source": "mock"},
            confidence_score=0.99,
        )

    async def autocomplete(
        self, query: str, session_token: Optional[str] = None
    ) -> List[AutocompleteResult]:
        base = [
            AutocompleteResult(
                text="Times Square",
                place_id="mock:times_square",
                description="Times Square, New York, NY, USA",
                types=["poi", "address"],
            ),
            AutocompleteResult(
                text="Needs Fallback",
                place_id="mock:needs_fallback",
                description="Address with missing coords",
                types=["address"],
            ),
        ]
        return base

    async def get_place_details(self, place_id: str) -> Optional[GeocodedAddress]:
        # Simulate a place details lookup; one id intentionally lacks coords (0.0) to trigger fallback
        if place_id == "mock:needs_fallback":
            return GeocodedAddress(
                latitude=0.0,
                longitude=0.0,
                formatted_address="Fallback Needed Address, New York, NY 10036, USA",
                street_number="1515",
                street_name="Broadway",
                city="New York",
                state="NY",
                postal_code="10036",
                country="US",
                neighborhood="Midtown",
                provider_id=place_id,
                provider_data={"source": "mock", "note": "coords missing"},
                confidence_score=0.8,
            )
        # Default: Times Square style
        return GeocodedAddress(
            latitude=40.7580,
            longitude=-73.9855,
            formatted_address="Times Square, New York, NY 10036, USA",
            street_number="1515",
            street_name="Broadway",
            city="New York",
            state="NY",
            postal_code="10036",
            country="US",
            neighborhood="Midtown",
            provider_id=place_id,
            provider_data={"source": "mock"},
            confidence_score=0.99,
        )
