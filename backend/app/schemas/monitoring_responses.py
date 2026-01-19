"""
Response schemas for monitoring endpoints.

These schemas ensure consistent response formats for all monitoring
and metrics endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictModel

# ============================================================================
# Typed metrics models for monitoring responses
# ============================================================================


class BasicCacheStats(BaseModel):
    """Basic cache statistics."""

    hits: int = Field(default=0, description="Cache hits")
    misses: int = Field(default=0, description="Cache misses")
    errors: int = Field(default=0, description="Cache errors")
    hit_rate: str = Field(default="0.0%", description="Cache hit rate percentage")


class PerformanceCacheStats(BaseModel):
    """Cache statistics for performance metrics."""

    hits: int = Field(default=0, description="Cache hits")
    misses: int = Field(default=0, description="Cache misses")
    hit_rate: str = Field(default="0.0%", description="Cache hit rate percentage")


class AvailabilityMetrics(BaseModel):
    """Availability-specific cache metrics."""

    availability_hit_rate: str = Field(default="0.0%", description="Availability cache hit rate")
    availability_total_requests: int = Field(default=0, description="Total availability requests")
    availability_invalidations: int = Field(
        default=0, description="Availability cache invalidations"
    )


class AvailabilityCacheMetrics(BaseModel):
    """Detailed availability cache metrics."""

    hit_rate: str = Field(default="0.0%", description="Cache hit rate percentage")
    total_requests: int = Field(default=0, description="Total cache requests")
    hits: int = Field(default=0, description="Cache hits")
    misses: int = Field(default=0, description="Cache misses")
    invalidations: int = Field(default=0, description="Cache invalidations")
    cache_efficiency: str = Field(default="unknown", description="Cache efficiency rating")


class RateLimitedClient(BaseModel):
    """Rate-limited client information."""

    key: str = Field(description="Client identifier key")
    count: int = Field(description="Request count")
    endpoint: str = Field(description="Most rate-limited endpoint")


class DatabasePoolStatus(BaseModel):
    """Database connection pool status."""

    pool_size: int = Field(description="Total pool size")
    checked_in: int = Field(description="Available connections")
    checked_out: int = Field(description="Active connections")
    overflow: int = Field(description="Overflow connections")
    usage_percent: float = Field(description="Pool usage percentage")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pool_size": 20,
                "checked_in": 15,
                "checked_out": 5,
                "overflow": 0,
                "usage_percent": 25.0,
            }
        }
    )


class DatabaseDashboardMetrics(BaseModel):
    """Database metrics for monitoring dashboard."""

    average_pool_usage_percent: float = Field(
        default=0.0, description="Average pool usage percentage"
    )
    slow_queries_count: int = Field(default=0, description="Number of slow queries")
    pool: DatabasePoolStatus = Field(description="Connection pool status")


class PerformanceDatabaseMetrics(BaseModel):
    """Database metrics for performance monitoring."""

    active_connections: int = Field(default=0, description="Active database connections")
    pool_status: DatabasePoolStatus = Field(description="Connection pool status")


class CacheHealthStatus(BaseModel):
    """Cache health and performance status."""

    status: str = Field(description="Health status (healthy/degraded/unhealthy)")
    hit_rate: str = Field(description="Cache hit rate percentage")
    total_requests: int = Field(description="Total cache requests")
    errors: int = Field(description="Cache error count")
    recommendations: List[str] = Field(description="Performance recommendations")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "hit_rate": "85.5%",
                "total_requests": 10000,
                "errors": 0,
                "recommendations": ["Cache performance is optimal"],
            }
        }
    )


class MemoryMetrics(BaseModel):
    """System memory metrics."""

    used_mb: float = Field(description="Used memory in MB")
    total_mb: float = Field(description="Total memory in MB")
    percent: float = Field(description="Memory usage percentage")

    model_config = ConfigDict(
        json_schema_extra={"example": {"used_mb": 2048.5, "total_mb": 8192.0, "percent": 25.0}}
    )


class RequestMetrics(BaseModel):
    """Request processing metrics."""

    active_count: int = Field(description="Currently active requests")
    total_count: int = Field(description="Total requests processed")
    average_response_time_ms: float = Field(description="Average response time in milliseconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"active_count": 5, "total_count": 10000, "average_response_time_ms": 45.2}
        }
    )


class AlertInfo(BaseModel):
    """Alert information."""

    type: str = Field(description="Alert type")
    severity: str = Field(description="Alert severity (info/warning/critical)")
    message: str = Field(description="Alert message")
    timestamp: datetime = Field(description="Alert timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "high_memory_usage",
                "severity": "warning",
                "message": "Memory usage is above 80%",
                "timestamp": "2025-01-20T10:30:00Z",
            }
        }
    )


class PerformanceRecommendation(BaseModel):
    """Performance optimization recommendation."""

    type: str = Field(description="Recommendation type (database/cache/memory/requests)")
    severity: str = Field(description="Severity level (info/warning)")
    message: str = Field(description="Recommendation message")
    action: str = Field(description="Suggested action")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "database",
                "severity": "warning",
                "message": "High database pool usage",
                "action": "Consider optimizing queries or increasing pool size",
            }
        }
    )


class MonitoringDashboardResponse(StrictModel):
    """Comprehensive monitoring dashboard response."""

    status: str = Field(description="Overall system status")
    timestamp: datetime = Field(description="Dashboard snapshot timestamp")
    database: DatabaseDashboardMetrics = Field(description="Database metrics and pool status")
    cache: CacheHealthStatus = Field(description="Cache health status")
    requests: RequestMetrics = Field(description="Request processing metrics")
    memory: MemoryMetrics = Field(description="System memory metrics")
    alerts: List[AlertInfo] = Field(description="Active system alerts")
    recommendations: List[PerformanceRecommendation] = Field(
        description="Performance recommendations"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "timestamp": "2025-01-20T10:30:00Z",
                "database": {
                    "average_pool_usage_percent": 25.0,
                    "slow_queries_count": 5,
                    "pool": {
                        "pool_size": 20,
                        "checked_in": 15,
                        "checked_out": 5,
                        "overflow": 0,
                        "usage_percent": 25.0,
                    },
                },
                "cache": {
                    "status": "healthy",
                    "hit_rate": "85.5%",
                    "total_requests": 10000,
                    "errors": 0,
                    "recommendations": ["Cache performance is optimal"],
                },
                "requests": {
                    "active_count": 5,
                    "total_count": 10000,
                    "average_response_time_ms": 45.2,
                },
                "memory": {"used_mb": 2048.5, "total_mb": 8192.0, "percent": 25.0},
                "alerts": [],
                "recommendations": [],
            }
        }
    )


class SlowQueryInfo(BaseModel):
    """Slow query information."""

    query: str = Field(description="SQL query (truncated)")
    duration_ms: float = Field(description="Query duration in milliseconds")
    timestamp: datetime = Field(description="Query execution timestamp")
    endpoint: Optional[str] = Field(
        default=None, description="API endpoint that triggered the query"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "SELECT * FROM bookings WHERE ...",
                "duration_ms": 523.4,
                "timestamp": "2025-01-20T10:30:00Z",
                "endpoint": "/api/v1/bookings",
            }
        }
    )


class SlowQueriesResponse(StrictModel):
    """Slow queries response."""

    slow_queries: List[SlowQueryInfo] = Field(description="List of slow queries")
    total_count: int = Field(description="Total number of slow queries tracked")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slow_queries": [
                    {
                        "query": "SELECT * FROM bookings WHERE ...",
                        "duration_ms": 523.4,
                        "timestamp": "2025-01-20T10:30:00Z",
                        "endpoint": "/api/v1/bookings",
                    }
                ],
                "total_count": 42,
            }
        }
    )


class SlowRequestInfo(BaseModel):
    """Slow request information."""

    path: str = Field(description="Request path")
    method: str = Field(description="HTTP method")
    duration_ms: float = Field(description="Request duration in milliseconds")
    timestamp: datetime = Field(description="Request timestamp")
    status_code: int = Field(description="Response status code")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "path": "/api/v1/instructors/search",
                "method": "GET",
                "duration_ms": 1234.5,
                "timestamp": "2025-01-20T10:30:00Z",
                "status_code": 200,
            }
        }
    )


class SlowRequestsResponse(StrictModel):
    """Slow requests response."""

    slow_requests: List[SlowRequestInfo] = Field(description="List of slow requests")
    total_count: int = Field(description="Total number of slow requests tracked")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slow_requests": [
                    {
                        "path": "/api/v1/instructors/search",
                        "method": "GET",
                        "duration_ms": 1234.5,
                        "timestamp": "2025-01-20T10:30:00Z",
                        "status_code": 200,
                    }
                ],
                "total_count": 15,
            }
        }
    )


class ExtendedCacheStats(BaseModel):
    """Extended cache statistics."""

    basic_stats: BasicCacheStats = Field(description="Basic cache statistics")
    # redis_info remains Dict[str, Any] - external Redis server returns dynamic fields
    redis_info: Optional[Dict[str, Any]] = Field(
        default=None, description="Redis server information"
    )
    key_patterns: Optional[Dict[str, int]] = Field(
        default=None, description="Cache key pattern counts"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "basic_stats": {"hits": 8500, "misses": 1500, "errors": 0, "hit_rate": "85.0%"},
                "redis_info": {
                    "used_memory_human": "12.5M",
                    "keyspace_hits": 50000,
                    "keyspace_misses": 5000,
                    "evicted_keys": 0,
                },
                "key_patterns": {"avail:*": 450, "instructor:*": 200, "booking:*": 150},
            }
        }
    )


class AlertAcknowledgeResponse(StrictModel):
    """Alert acknowledgement response."""

    status: str = Field(description="Acknowledgement status")
    alert_type: str = Field(description="Alert type that was acknowledged")

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "acknowledged", "alert_type": "high_memory_usage"}}
    )


class ServiceMetrics(BaseModel):
    """Service-level performance metrics."""

    operations: Dict[str, int] = Field(description="Operation counts by type")
    total_operations: int = Field(description="Total operations performed")
    cache_operations: int = Field(description="Cache operations performed")
    db_operations: int = Field(description="Database operations performed")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "operations": {
                    "get_availability": 1000,
                    "create_booking": 50,
                    "check_conflicts": 200,
                },
                "total_operations": 1250,
                "cache_operations": 800,
                "db_operations": 450,
            }
        }
    )


class PerformanceMetricsResponse(StrictModel):
    """Comprehensive performance metrics response."""

    availability_service: ServiceMetrics = Field(description="Availability service metrics")
    booking_service: ServiceMetrics = Field(description="Booking service metrics")
    conflict_checker: ServiceMetrics = Field(description="Conflict checker metrics")
    cache: PerformanceCacheStats = Field(description="Cache statistics")
    system: Dict[str, float] = Field(description="System resource metrics")
    database: PerformanceDatabaseMetrics = Field(description="Database connection metrics")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "availability_service": {
                    "operations": {"get_availability": 1000},
                    "total_operations": 1000,
                    "cache_operations": 800,
                    "db_operations": 200,
                },
                "booking_service": {
                    "operations": {"create_booking": 50},
                    "total_operations": 50,
                    "cache_operations": 10,
                    "db_operations": 40,
                },
                "conflict_checker": {
                    "operations": {"check_conflicts": 200},
                    "total_operations": 200,
                    "cache_operations": 150,
                    "db_operations": 50,
                },
                "cache": {"hits": 8500, "misses": 1500, "hit_rate": "85.0%"},
                "system": {"cpu_percent": 25.5, "memory_percent": 45.2, "disk_usage": 60.0},
                "database": {
                    "active_connections": 5,
                    "pool_status": {"pool_size": 20, "usage_percent": 25.0},
                },
            }
        },
    )


class CacheMetricsResponse(StrictModel):
    """Detailed cache metrics response."""

    hits: int = Field(description="Cache hits")
    misses: int = Field(description="Cache misses")
    errors: int = Field(description="Cache errors")
    hit_rate: str = Field(description="Cache hit rate percentage")
    availability_metrics: AvailabilityMetrics = Field(
        description="Availability-specific cache metrics"
    )
    # redis_info remains Dict[str, Any] - external Redis server returns dynamic fields
    redis_info: Optional[Dict[str, Any]] = Field(
        default=None, description="Redis server information"
    )
    performance_insights: List[str] = Field(description="Cache performance insights")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "hits": 8500,
                "misses": 1500,
                "errors": 0,
                "hit_rate": "85.0%",
                "availability_metrics": {
                    "availability_hit_rate": "87.5%",
                    "availability_total_requests": 2000,
                    "availability_invalidations": 50,
                },
                "redis_info": {"used_memory_human": "12.5M", "keyspace_hits": 50000},
                "performance_insights": ["Cache performance looks good"],
            }
        },
    )


class AvailabilityCacheMetricsResponse(StrictModel):
    """Availability-specific cache metrics response."""

    availability_cache_metrics: AvailabilityCacheMetrics = Field(
        description="Availability cache metrics"
    )
    top_cached_keys_sample: List[str] = Field(description="Sample of top cached keys")
    recommendations: List[str] = Field(description="Performance recommendations")
    cache_tiers_info: Dict[str, str] = Field(description="Cache tier configuration")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "availability_cache_metrics": {
                    "hit_rate": "87.5%",
                    "total_requests": 2000,
                    "hits": 1750,
                    "misses": 250,
                    "invalidations": 50,
                    "cache_efficiency": "excellent",
                },
                "top_cached_keys_sample": [
                    "avail:instructor:123:2025-01-20",
                    "availability:window:456",
                ],
                "recommendations": ["Availability caching performance is optimal"],
                "cache_tiers_info": {
                    "hot": "5 minutes (current/future availability)",
                    "warm": "1 hour (past availability)",
                    "cold": "24 hours (historical data)",
                },
            }
        },
    )


class RateLimitStats(StrictModel):
    """Rate limit statistics."""

    total_keys: int = Field(description="Total rate limit keys in Redis")
    breakdown_by_type: Dict[str, int] = Field(description="Breakdown by limit type")
    top_limited_clients: List[RateLimitedClient] = Field(description="Top rate-limited clients")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "total_keys": 42,
                "breakdown_by_type": {"email": 15, "ip": 20, "global": 7},
                "top_limited_clients": [
                    {"key": "ip_192.168.1.100", "count": 50, "endpoint": "/api/v1/search"}
                ],
            }
        },
    )


class RateLimitResetResponse(StrictModel):
    """Rate limit reset response."""

    status: str = Field(description="Operation status")
    pattern: str = Field(description="Pattern used for matching")
    limits_reset: int = Field(description="Number of limits reset")
    message: str = Field(description="Result message")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "status": "success",
                "pattern": "email_*",
                "limits_reset": 5,
                "message": "Reset 5 rate limits matching pattern 'email_*'",
            }
        },
    )


class RateLimitTestResponse(StrictModel):
    """Rate limit test endpoint response."""

    message: str = Field(description="Test message")
    timestamp: str = Field(description="Request timestamp")
    note: str = Field(description="Rate limit information")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "message": "Rate limit test successful",
                "timestamp": "2025-01-20T10:30:00.234567",
                "note": "This endpoint is rate limited to 3 requests per minute",
            }
        },
    )


class PaymentHealthResponse(StrictModel):
    """Payment system health monitoring response."""

    status: str = Field(description="Payment system health status (healthy/warning/critical)")
    timestamp: str = Field(description="Health check timestamp")
    payment_stats: Dict[str, int] = Field(description="Payment status counts")
    recent_events: Dict[str, int] = Field(description="Recent payment event counts")
    overdue_authorizations: int = Field(description="Number of overdue authorizations")
    minutes_since_last_auth: Optional[int] = Field(
        default=None, description="Minutes since last successful auth"
    )
    alerts: List[str] = Field(description="Current payment system alerts")
    metrics: Dict[str, int] = Field(description="Payment metrics breakdown")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "timestamp": "2025-01-20T10:30:00.234567",
                "payment_stats": {
                    "payment_method_required": 5,
                    "scheduled": 12,
                    "authorized": 25,
                    "locked": 3,
                    "manual_review": 1,
                    "settled": 150,
                },
                "recent_events": {"auth_succeeded": 15, "auth_failed": 2, "payment_captured": 8},
                "overdue_authorizations": 0,
                "minutes_since_last_auth": 45,
                "alerts": [],
                "metrics": {
                    "payment_method_required": 5,
                    "scheduled": 12,
                    "authorized": 25,
                    "locked": 3,
                    "manual_review": 1,
                    "settled": 150,
                },
            }
        }
    )


class PaymentHealthCheckTriggerResponse(StrictModel):
    """Response for manually triggered payment health check."""

    status: str = Field(description="Trigger status")
    task_id: str = Field(description="Celery task ID")
    message: str = Field(description="Status message")
    timestamp: str = Field(description="Trigger timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "triggered",
                "task_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
                "message": "Health check task has been queued",
                "timestamp": "2025-01-20T10:30:00.234567",
            }
        }
    )
