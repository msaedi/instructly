from typing import Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from ...core.constants import MAX_SESSION_DURATION, MIN_SESSION_DURATION
from .._strict_base import StrictRequestModel
from ..base import Money, StandardizedModel
from ..service_pricing import (
    ServiceFormatPriceIn,
    ServiceFormatPriceOut,
    validate_unique_format_prices,
)


class _ServiceCommonBase(StandardizedModel):
    """
    Shared schema fields for instructor services.

    Attributes:
        service_catalog_id: ID of the service from the catalog
        description: Optional description of the service
        duration_options: Available duration options for this service in minutes
    """

    service_catalog_id: str = Field(..., description="ID of the service from catalog")
    description: Optional[str] = Field(None, max_length=500)
    requirements: Optional[str] = Field(None, max_length=500)
    age_groups: Optional[List[str]] = Field(
        default=None,
        description=(
            "Age groups this service is offered to. "
            "Allowed: 'toddler', 'kids', 'teens', 'adults'."
        ),
    )
    equipment_required: Optional[List[str]] = Field(
        default=None,
        description="List of equipment required (strings)",
    )
    filter_selections: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Instructor's filter choices for this service (e.g., {'grade_level': ['elementary']})",
    )
    duration_options: List[int] = Field(
        default=[60],
        description="Available duration options for this service in minutes",
        min_length=1,
    )

    @field_validator("duration_options")
    def validate_duration_range(cls, v: List[int]) -> List[int]:
        """Ensure each duration is within valid range."""
        if not v:
            raise ValueError("At least one duration option is required")
        for duration in v:
            if not MIN_SESSION_DURATION <= duration <= MAX_SESSION_DURATION:
                raise ValueError(
                    f"Duration must be between {MIN_SESSION_DURATION} and {MAX_SESSION_DURATION} minutes"
                )
        return v

    @field_validator("age_groups")
    def validate_age_groups(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize and validate age groups."""
        if v is None:
            return v
        allowed = {"toddler", "kids", "teens", "adults"}
        normalized: List[str] = []
        for item in v:
            value = str(item).strip().lower()
            if value in allowed:
                normalized.append(value)
            else:
                raise ValueError(
                    "age_groups must be one or more of: 'toddler', 'kids', 'teens', 'adults'"
                )
        seen: set[str] = set()
        deduped: List[str] = []
        for item in normalized:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped


class ServiceBase(_ServiceCommonBase):
    """
    Base request schema for instructor services.

    Attributes:
        format_prices: Enabled per-format hourly pricing rows
    """

    format_prices: List[ServiceFormatPriceIn] = Field(
        ..., min_length=1, description="Per-format hourly pricing for this service"
    )

    @field_validator("format_prices")
    def validate_format_prices(
        cls, value: List[ServiceFormatPriceIn]
    ) -> List[ServiceFormatPriceIn]:
        validate_unique_format_prices(value)
        return value


class ServiceCreate(StrictRequestModel, ServiceBase):
    """Schema for creating a new service."""

    model_config = ConfigDict(
        **ServiceBase.model_config,
        **StrictRequestModel.model_config,
    )


class ServiceResponse(_ServiceCommonBase):
    """
    Schema for service responses.

    Includes the service ID and catalog information.
    """

    id: str
    name: str | None = Field(
        default=None,
        description="Resolved name of the service from the catalog",
    )
    service_catalog_name: str = Field(
        ...,
        max_length=255,
        description="Human-readable name of the catalog service",
    )
    min_hourly_rate: Money | None = Field(
        default=None,
        description="Lowest enabled hourly rate for this service",
    )
    format_prices: List[ServiceFormatPriceOut] = Field(
        default_factory=list,
        description="Enabled per-format hourly pricing rows",
    )
    offers_travel: bool = Field(
        default=False,
        description="Whether the instructor travels to student locations for this service",
    )
    offers_at_location: bool = Field(
        default=False,
        description="Whether the instructor offers lessons at their location for this service",
    )
    offers_online: bool = Field(
        default=True,
        description="Whether the instructor offers online lessons for this service",
    )
    display_order: int | None = Field(
        default=None,
        description="Display order hint from the catalog (nullable)",
    )
    online_capable: bool | None = Field(
        default=None,
        description="Whether the catalog service supports online delivery",
    )
    requires_certification: bool | None = Field(
        default=None,
        description="Whether the catalog service requires certification",
    )
    is_active: bool | None = Field(
        default=None,
        description="Whether this service is currently active for the instructor",
    )

    @field_validator("format_prices")
    def validate_response_format_prices(
        cls, value: List[ServiceFormatPriceOut]
    ) -> List[ServiceFormatPriceOut]:
        validate_unique_format_prices(value)
        return value

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)
