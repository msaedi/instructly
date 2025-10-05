from ._strict_base import StrictModel

"""Response models for monitoring and infrastructure endpoints."""

from typing import Any, Dict, List

from pydantic import ConfigDict


class RedisStatsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for Redis statistics."""

    stats: Dict[str, Any]


class RedisCeleryQueuesResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for Redis Celery queues."""

    queues: Dict[str, Any]


class RedisConnectionAuditResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for Redis connection audit."""

    connections: List[Dict[str, Any]]


class RedisFlushQueuesResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for flushing Redis queues."""

    message: str
    queues_flushed: List[str]


class DatabasePoolStatusResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for database pool status."""

    pool_status: Dict[str, Any]


class DatabaseStatsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for database statistics."""

    stats: Dict[str, Any]


class HealthResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for health check."""

    status: str
    timestamp: str
    checks: Dict[str, Any] = {}


class HealthLiteResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for lite health check."""

    status: str


class RootResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for root endpoint."""

    message: str
    version: str = "1.0.0"


class PrivacyRetentionResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for privacy retention apply."""

    message: str
    records_processed: int
    records_deleted: int
