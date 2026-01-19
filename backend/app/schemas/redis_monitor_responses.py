"""
Response models for Redis monitoring endpoints.

These models ensure consistent API responses for Redis health
and monitoring endpoints.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictModel


class RedisHealthResponse(StrictModel):
    """Response for Redis health check endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(description="Health status (healthy/unhealthy)")
    connected: bool = Field(description="Whether Redis is connected")
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")


class RedisTestResponse(StrictModel):
    """Response for Redis test endpoint."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(description="Connection status")
    ping: Optional[bool] = Field(default=None, description="Ping result")
    redis_version: Optional[str] = Field(default="unknown", description="Redis server version")
    uptime_seconds: Optional[int] = Field(default=0, description="Redis uptime in seconds")
    connected_clients: Optional[int] = Field(default=0, description="Number of connected clients")
    message: Optional[str] = Field(default=None, description="Status message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# Redis Stats typed models
class RedisServerInfo(BaseModel):
    """Redis server information."""

    redis_version: str = "unknown"
    uptime_in_days: int = 0


class RedisMemoryInfo(BaseModel):
    """Redis memory metrics."""

    used_memory_human: str = "N/A"
    used_memory_peak_human: str = "N/A"
    used_memory_rss_human: str = "N/A"
    maxmemory_human: str = "N/A"
    mem_fragmentation_ratio: float = 0


class RedisConnectionStats(BaseModel):
    """Redis connection statistics."""

    total_connections_received: int = 0
    total_commands_processed: int = 0
    instantaneous_ops_per_sec: int = 0
    rejected_connections: int = 0
    expired_keys: int = 0
    evicted_keys: int = 0


class RedisClientStats(BaseModel):
    """Redis client statistics."""

    connected_clients: int = 0
    blocked_clients: int = 0


class RedisOperationMetrics(BaseModel):
    """Redis operation rate metrics."""

    current_ops_per_sec: int = 0
    estimated_daily_ops: int = 0
    estimated_monthly_ops: int = 0


class RedisStatsData(BaseModel):
    """Complete Redis statistics data."""

    status: str = "unknown"
    server: RedisServerInfo = Field(default_factory=RedisServerInfo)
    memory: RedisMemoryInfo = Field(default_factory=RedisMemoryInfo)
    stats: RedisConnectionStats = Field(default_factory=RedisConnectionStats)
    clients: RedisClientStats = Field(default_factory=RedisClientStats)
    celery: Dict[str, int] = Field(default_factory=dict)
    operations: RedisOperationMetrics = Field(default_factory=RedisOperationMetrics)


class RedisStatsResponse(StrictModel):
    """Response for Redis statistics."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    stats: RedisStatsData


# Celery queues typed models
class CeleryQueuesData(BaseModel):
    """Celery queue status data."""

    status: str = "unknown"
    queues: Dict[str, int] = Field(default_factory=dict)
    total_pending: int = 0


class RedisCeleryQueuesResponse(StrictModel):
    """Response for Redis Celery queues."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    queues: CeleryQueuesData


# Connection audit typed models
class RedisServiceConnection(BaseModel):
    """Redis connection info for a service."""

    url: str
    host: str
    type: str


class RedisActiveConnections(BaseModel):
    """Active Redis connection counts."""

    local_redis: int = 0
    upstash: int = 0


class RedisConnectionAuditData(BaseModel):
    """Redis connection audit data."""

    api_cache: str
    celery_broker: str
    active_connections: RedisActiveConnections = Field(default_factory=RedisActiveConnections)
    upstash_detected: bool = False
    service_connections: Dict[str, RedisServiceConnection] = Field(default_factory=dict)
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    migration_status: str = "unknown"
    recommendation: str = ""


class RedisConnectionAuditResponse(StrictModel):
    """Response for Redis connection audit."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    connections: List[RedisConnectionAuditData]


class RedisFlushQueuesResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for flushing Redis queues."""

    message: str
    queues_flushed: List[str]
