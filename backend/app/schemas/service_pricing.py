"""Shared schemas for per-format instructor service pricing."""

from __future__ import annotations

from typing import Sequence, TypeVar

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel
from .base import Money
from .common import ServicePricingFormatLiteral


class ServiceFormatPriceIn(StrictRequestModel):
    """Writable per-format hourly rate for a service."""

    format: ServicePricingFormatLiteral
    hourly_rate: Money = Field(..., gt=0, le=1000)


class ServiceFormatPriceOut(StrictModel):
    """Read-only per-format hourly rate for a service."""

    format: ServicePricingFormatLiteral
    hourly_rate: Money

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


TServiceFormatPrice = TypeVar(
    "TServiceFormatPrice",
    ServiceFormatPriceIn,
    ServiceFormatPriceOut,
)


def validate_unique_format_prices(
    format_prices: Sequence[TServiceFormatPrice],
) -> Sequence[TServiceFormatPrice]:
    """Ensure format_prices contains no duplicate formats."""
    if not format_prices:
        raise ValueError("At least one format price is required")
    formats = [item.format for item in format_prices]
    if len(formats) != len(set(formats)):
        raise ValueError("Each format may only appear once in format_prices")
    return format_prices


__all__ = [
    "ServiceFormatPriceIn",
    "ServiceFormatPriceOut",
    "validate_unique_format_prices",
]
