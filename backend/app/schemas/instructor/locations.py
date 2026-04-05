from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from .._strict_base import StrictModel


class PreferredTeachingLocationIn(BaseModel):
    """Preferred teaching location input payload."""

    address: str = Field(..., min_length=1, max_length=512)
    label: str | None = Field(default=None, min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PreferredPublicSpaceIn(BaseModel):
    """Preferred public space input payload."""

    address: str = Field(..., min_length=1, max_length=512)
    label: str | None = Field(default=None, min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServiceAreaCheckCoordinates(StrictModel):
    """Coordinates payload for service area checks."""

    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")


class InstructorServiceAreaCheckResponse(StrictModel):
    """Response payload for instructor service area coverage checks."""

    instructor_id: str = Field(..., description="Instructor user ULID")
    is_covered: bool = Field(
        ...,
        description="True when the coordinates fall inside an instructor's active service areas",
    )
    coordinates: ServiceAreaCheckCoordinates


class PreferredTeachingLocationOut(BaseModel):
    """Preferred teaching location response payload."""

    address: Optional[str] = None
    label: Optional[str] = None
    approx_lat: Optional[float] = None
    approx_lng: Optional[float] = None
    neighborhood: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.address:
            data["address"] = self.address
        if self.label is not None:
            data["label"] = self.label
        if self.approx_lat is not None:
            data["approx_lat"] = self.approx_lat
        if self.approx_lng is not None:
            data["approx_lng"] = self.approx_lng
        if self.neighborhood:
            data["neighborhood"] = self.neighborhood
        return data


class PreferredTeachingLocationPublicOut(BaseModel):
    """Public teaching location response payload without precise address."""

    label: Optional[str] = None
    approx_lat: Optional[float] = None
    approx_lng: Optional[float] = None
    neighborhood: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.label is not None:
            data["label"] = self.label
        if self.approx_lat is not None:
            data["approx_lat"] = self.approx_lat
        if self.approx_lng is not None:
            data["approx_lng"] = self.approx_lng
        if self.neighborhood:
            data["neighborhood"] = self.neighborhood
        return data


class PreferredPublicSpaceOut(PreferredPublicSpaceIn):
    """Preferred public space response payload."""

    model_config = ConfigDict(from_attributes=True)

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {"address": self.address}
        if self.label is not None:
            data["label"] = self.label
        return data
