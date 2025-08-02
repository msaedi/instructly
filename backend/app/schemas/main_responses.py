"""
Response models for main application endpoints.

These models ensure consistent API responses for root, health check,
and performance monitoring endpoints.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    """Response for root endpoint."""

    message: str = Field(description="Welcome message")
    version: str = Field(description="API version")
    docs: str = Field(description="Documentation URL")
    environment: str = Field(description="Environment name")
    secure: bool = Field(description="Whether running in secure mode")


class HealthResponse(BaseModel):
    """Response for health check endpoint."""

    status: str = Field(description="Health status")
    service: str = Field(description="Service name")
    version: str = Field(description="API version")
    environment: str = Field(description="Environment name")


class HealthLiteResponse(BaseModel):
    """Response for lightweight health check endpoint."""

    status: str = Field(description="Health status (ok/error)")


class PerformanceMetricsResponse(BaseModel):
    """Response for performance metrics endpoint."""

    metrics: Dict[str, Any] = Field(description="Performance metrics data")
