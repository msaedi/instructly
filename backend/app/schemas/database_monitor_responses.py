from ._strict_base import StrictModel

"""
Response models for database monitoring endpoints.

These models ensure consistent API responses for database health
and monitoring endpoints.
"""

from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field


class DatabaseHealthResponse(StrictModel):
    """Response for database health check endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(description="Health status (healthy/unhealthy)")
    message: str = Field(description="Health check message")
    pool_status: Optional[Dict[str, Any]] = Field(
        default=None, description="Connection pool status"
    )
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")


class DatabasePoolStatusResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for database pool status endpoint."""

    status: str
    pool: Dict[str, Any]
    configuration: Dict[str, Any]
    recommendations: Dict[str, Any]


class DatabaseStatsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for database statistics endpoint."""

    status: str
    pool: Dict[str, Any]
    configuration: Dict[str, Any]
    health: Dict[str, Any]
