"""
Response models for Redis monitoring endpoints.

These models ensure consistent API responses for Redis health
and monitoring endpoints.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RedisHealthResponse(BaseModel):
    """Response for Redis health check endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(description="Health status (healthy/unhealthy)")
    connected: bool = Field(description="Whether Redis is connected")
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")


class RedisTestResponse(BaseModel):
    """Response for Redis test endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(description="Connection status")
    ping: Optional[bool] = Field(default=None, description="Ping result")
    redis_version: Optional[str] = Field(default="unknown", description="Redis server version")
    uptime_seconds: Optional[int] = Field(default=0, description="Redis uptime in seconds")
    connected_clients: Optional[int] = Field(default=0, description="Number of connected clients")
    message: Optional[str] = Field(default=None, description="Status message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class RedisStatsResponse(BaseModel):
    """Response for Redis statistics."""

    stats: Dict[str, Any]


class RedisCeleryQueuesResponse(BaseModel):
    """Response for Redis Celery queues."""

    queues: Dict[str, Any]


class RedisConnectionAuditResponse(BaseModel):
    """Response for Redis connection audit."""

    connections: List[Dict[str, Any]]


class RedisFlushQueuesResponse(BaseModel):
    """Response for flushing Redis queues."""

    message: str
    queues_flushed: List[str]
