from ._strict_base import StrictModel

"""
Response models for main application endpoints.

These models ensure consistent API responses for root, health check,
and performance monitoring endpoints.
"""

from typing import Any, Dict

from pydantic import ConfigDict, Field


class RootResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for root endpoint."""

    message: str = Field(description="Welcome message")
    version: str = Field(description="API version")
    docs: str = Field(description="Documentation URL")
    environment: str = Field(description="Environment name")
    secure: bool = Field(description="Whether running in secure mode")


class HealthResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for health check endpoint."""

    status: str = Field(description="Health status")
    service: str = Field(description="Service name")
    version: str = Field(description="API version")
    environment: str = Field(description="Environment name")
    timestamp: str = Field(description="UTC ISO8601Z timestamp of the health response")


class HealthLiteResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for lightweight health check endpoint."""

    status: str = Field(description="Health status (ok/error)")


class PerformanceMetricsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for performance metrics endpoint."""

    metrics: Dict[str, Any] = Field(description="Performance metrics data")
