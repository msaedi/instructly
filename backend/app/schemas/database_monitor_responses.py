"""
Response models for database monitoring endpoints.

These models ensure consistent API responses for database health
and monitoring endpoints.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictModel


class DatabasePoolMetrics(BaseModel):
    """Database connection pool metrics."""

    size: int = Field(description="Base pool size")
    max_overflow: int = Field(description="Maximum overflow connections")
    max_capacity: int = Field(description="Total possible connections (size + max_overflow)")
    checked_in: int = Field(description="Available connections")
    checked_out: int = Field(description="Active connections")
    overflow_in_use: int = Field(
        description="Current overflow connections (negative when below base size)"
    )
    utilization_pct: float = Field(description="Pool utilization percentage")


class DatabasePoolConfiguration(BaseModel):
    """SQLAlchemy pool configuration."""

    pool_size: int = Field(description="Base pool size")
    max_overflow: int = Field(description="Maximum overflow connections")
    timeout: Optional[float] = Field(None, description="Connection timeout seconds")
    recycle: Optional[float] = Field(None, description="Connection recycle time seconds")


class DatabaseRecommendations(BaseModel):
    """Database pool recommendations."""

    increase_pool_size: bool = Field(description="Whether pool size should be increased")
    current_load: Literal["low", "normal", "high"] = Field(description="Current load level")


class DatabaseHealthMetrics(BaseModel):
    """Database health metrics."""

    status: str = Field(description="Health status")
    utilization_pct: float = Field(description="Pool utilization percentage")


class DatabaseHealthResponse(StrictModel):
    """Response for database health check endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(description="Health status (healthy/unhealthy)")
    message: str = Field(description="Health check message")
    pool_status: Optional[DatabasePoolMetrics] = Field(
        default=None, description="Connection pool status"
    )
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")


class DatabasePoolStatusResponse(StrictModel):
    """Response for database pool status endpoint."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    status: str
    pool: DatabasePoolMetrics
    configuration: DatabasePoolConfiguration
    recommendations: DatabaseRecommendations


class DatabaseStatsResponse(StrictModel):
    """Response for database statistics endpoint."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    status: str
    pool: DatabasePoolMetrics
    configuration: DatabasePoolConfiguration
    health: DatabaseHealthMetrics
