"""Response models for monitoring and infrastructure endpoints."""

from typing import Any, Dict, List

from pydantic import BaseModel


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


class DatabasePoolStatusResponse(BaseModel):
    """Response for database pool status."""

    pool_status: Dict[str, Any]


class DatabaseStatsResponse(BaseModel):
    """Response for database statistics."""

    stats: Dict[str, Any]


class HealthResponse(BaseModel):
    """Response for health check."""

    status: str
    timestamp: str
    checks: Dict[str, Any] = {}


class HealthLiteResponse(BaseModel):
    """Response for lite health check."""

    status: str


class RootResponse(BaseModel):
    """Response for root endpoint."""

    message: str
    version: str = "1.0.0"


class PrivacyRetentionResponse(BaseModel):
    """Response for privacy retention apply."""

    message: str
    records_processed: int
    records_deleted: int
