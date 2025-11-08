# backend/app/routes/metrics.py
"""
Simple metrics endpoint for performance monitoring.

This gives us immediate visibility without Prometheus complexity.
"""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Mapping, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
import psutil
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.dependencies.authz import require_roles
from ..api.dependencies.services import (
    get_availability_service,
    get_booking_service,
    get_cache_service_dep,
    get_conflict_checker,
)
from ..auth import get_current_user_optional as auth_get_current_user_optional
from ..core.config import settings
from ..database import get_db, get_db_pool_status
from ..metrics import retention_metrics
from ..middleware import rate_limiter as rate_limiter_module
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..models.user import User
from ..schemas.base_responses import HealthCheckResponse, SuccessResponse
from ..schemas.monitoring_responses import (
    AvailabilityCacheMetricsResponse,
    CacheMetricsResponse,
    PerformanceMetricsResponse,
    RateLimitResetResponse,
    RateLimitStats,
    RateLimitTestResponse,
    SlowQueriesResponse,
)
from ..services.cache_service import CacheService

router = APIRouter(prefix="/ops", tags=["monitoring"])
metrics_lite_router = APIRouter(
    prefix="/ops",
    tags=["ops-internal"],
    dependencies=[Depends(require_roles("admin"))],
)


RateLimitAdmin = cast(Any, getattr(rate_limiter_module, "RateLimitAdmin"))


@metrics_lite_router.get(
    "/metrics-lite",
    include_in_schema=False,
    response_class=PlainTextResponse,
)
def metrics_lite() -> str:
    """Return retention metrics in plain text."""
    return retention_metrics.render_text()


def _ops_admin_required() -> bool:
    mode = (settings.site_mode or "").lower()
    raw_mode = (os.getenv("SITE_MODE", "") or "").strip().lower()
    return mode in {"preview", "prod"} or raw_mode == "beta"


async def _get_optional_user(
    current_user_email: Optional[str] = Depends(auth_get_current_user_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not current_user_email:
        return None
    user = db.query(User).filter(User.email == current_user_email).first()
    return cast(Optional[User], user)


async def _ensure_ops_access(
    request: Request, current_user: Optional[User] = Depends(_get_optional_user)
) -> Optional[User]:
    if not _ops_admin_required():
        return current_user
    if current_user is None or not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


JsonDict = Dict[str, Any]
JsonList = List[JsonDict]


def _normalize_service_metrics(raw_metrics: Optional[Mapping[str, Any]]) -> JsonDict:
    """Convert BaseService.get_metrics() output into ServiceMetrics shape.

    Ensures required fields exist even when no metrics have been recorded yet.
    """
    if not raw_metrics:
        return {
            "operations": {},
            "total_operations": 0,
            "cache_operations": 0,
            "db_operations": 0,
        }

    # raw_metrics is a mapping: operation_name -> { count, total_time, ... }
    operations: Dict[str, int] = {}
    total_operations = 0
    for op_name, data in raw_metrics.items():
        count = 0
        if isinstance(data, Mapping):
            raw_count = data.get("count", 0)
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                count = 0
        operations[op_name] = count
        total_operations += count

    return {
        "operations": operations,
        "total_operations": total_operations,
        # Not tracked at this layer; keep zeros to satisfy schema
        "cache_operations": 0,
        "db_operations": 0,
    }


def _coerce_json_dict(value: Any, error_message: str) -> JsonDict:
    if isinstance(value, dict):
        return dict(value)
    return {"error": error_message}


@router.get(
    "/health", response_model=HealthCheckResponse, dependencies=[Depends(_ensure_ops_access)]
)
async def health_check() -> HealthCheckResponse:
    """Basic health check endpoint."""
    return HealthCheckResponse(
        status="healthy",
        service="InstaInstru API",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
        checks={"api": True},
    )


@router.get(
    "/performance",
    response_model=PerformanceMetricsResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
async def get_performance_metrics(
    availability_service: Any = Depends(get_availability_service),
    booking_service: Any = Depends(get_booking_service),
    conflict_checker: Any = Depends(get_conflict_checker),
    cache_service: Optional[CacheService] = Depends(get_cache_service_dep),
    db: Session = Depends(get_db),
) -> PerformanceMetricsResponse:
    """Get performance metrics from all services."""

    # Cache metrics
    if cache_service:
        raw_cache_stats = cache_service.get_stats()
        cache_stats = _coerce_json_dict(raw_cache_stats, "Unexpected cache stats format")
    else:
        cache_stats = {"error": "Cache service not available"}

    # System metrics
    system_metrics: JsonDict = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage("/").percent,
    }

    # Database metrics
    db_stats = db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
    database_metrics: JsonDict = {
        "active_connections": db_stats,
        "pool_status": get_db_pool_status(),
    }

    return PerformanceMetricsResponse(
        availability_service=_normalize_service_metrics(
            cast(Mapping[str, Any], availability_service.get_metrics())
        ),
        booking_service=_normalize_service_metrics(
            cast(Mapping[str, Any], booking_service.get_metrics())
        ),
        conflict_checker=_normalize_service_metrics(
            cast(Mapping[str, Any], conflict_checker.get_metrics())
        ),
        cache=cache_stats,
        system=system_metrics,
        database=database_metrics,
    )


@router.get(
    "/cache",
    response_model=CacheMetricsResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
async def get_cache_metrics(
    cache_service: Optional[CacheService] = Depends(get_cache_service_dep),
) -> CacheMetricsResponse:
    """Get detailed cache metrics including availability-specific stats."""

    if not cache_service:
        raise HTTPException(status_code=503, detail="Cache service not available")

    # Get basic cache stats
    stats = _coerce_json_dict(cache_service.get_stats(), "Unexpected cache stats format")

    # Add availability-specific metrics
    availability_stats: JsonDict = {
        "availability_hit_rate": "0%",
        "availability_total_requests": 0,
        "availability_invalidations": stats.get("availability_invalidations", 0),
    }

    # Calculate availability-specific hit rate
    avail_hits = stats.get("availability_hits", 0)
    avail_misses = stats.get("availability_misses", 0)
    avail_total = avail_hits + avail_misses

    if avail_total > 0:
        availability_stats["availability_hit_rate"] = f"{(avail_hits / avail_total * 100):.2f}%"
        availability_stats["availability_total_requests"] = avail_total

    # Add cache size estimates (if Redis is available)
    redis_info: Optional[JsonDict] = None
    if hasattr(cache_service, "redis") and cache_service.redis:
        try:
            # Get approximate cache size
            info = cache_service.redis.info()
            redis_info = {
                "used_memory_human": info.get("used_memory_human", "Unknown"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
            }
        except Exception:
            pass  # Redis info is optional

    return CacheMetricsResponse(
        hits=stats.get("hits", 0),
        misses=stats.get("misses", 0),
        errors=stats.get("errors", 0),
        hit_rate=f"{(stats.get('hits', 0) / (stats.get('hits', 0) + stats.get('misses', 0)) * 100):.2f}%"
        if (stats.get("hits", 0) + stats.get("misses", 0)) > 0
        else "0%",
        availability_metrics=availability_stats,
        redis_info=redis_info,
        performance_insights=_get_cache_performance_insights(stats),
    )


def _get_cache_performance_insights(stats: Mapping[str, Any]) -> List[str]:
    """Generate performance insights from cache statistics."""
    insights: List[str] = []

    total_requests = stats.get("hits", 0) + stats.get("misses", 0)
    if total_requests > 0:
        hit_rate = stats.get("hits", 0) / total_requests * 100

        if hit_rate < 60:
            insights.append("Low cache hit rate - consider adjusting TTL or cache strategy")
        elif hit_rate > 90:
            insights.append("Excellent cache performance")

        if stats.get("errors", 0) > 0:
            error_rate = stats.get("errors", 0) / total_requests * 100
            if error_rate > 5:
                insights.append(f"High error rate ({error_rate:.1f}%) - check cache service health")

    # Check availability-specific metrics
    avail_hits = stats.get("availability_hits", 0)
    avail_misses = stats.get("availability_misses", 0)
    avail_total = avail_hits + avail_misses

    if avail_total > 0:
        avail_hit_rate = avail_hits / avail_total * 100
        if avail_hit_rate < 70:
            insights.append("Availability cache hit rate is low - consider increasing TTL")

    if stats.get("availability_invalidations", 0) > 100:
        insights.append("High availability cache invalidation rate - check booking frequency")

    if not insights:
        insights.append("Cache performance looks good")

    return insights


@router.get(
    "/cache/availability",
    response_model=AvailabilityCacheMetricsResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
async def get_availability_cache_metrics(
    cache_service: Optional[CacheService] = Depends(get_cache_service_dep),
) -> AvailabilityCacheMetricsResponse:
    """Get detailed availability-specific cache metrics and top cached keys."""

    if not cache_service:
        raise HTTPException(status_code=503, detail="Cache service not available")

    stats = cache_service.get_stats()

    # Calculate availability-specific metrics
    avail_hits = stats.get("availability_hits", 0)
    avail_misses = stats.get("availability_misses", 0)
    avail_total = avail_hits + avail_misses
    avail_invalidations = stats.get("availability_invalidations", 0)

    availability_metrics = {
        "hit_rate": f"{(avail_hits / avail_total * 100):.2f}%" if avail_total > 0 else "0%",
        "total_requests": avail_total,
        "hits": avail_hits,
        "misses": avail_misses,
        "invalidations": avail_invalidations,
        "cache_efficiency": "excellent"
        if avail_total > 0 and (avail_hits / avail_total) > 0.8
        else "needs_improvement",
    }

    # Get top cached keys (if possible)
    top_keys: List[str] = []
    if hasattr(cache_service, "redis") and cache_service.redis:
        try:
            # Sample some availability-related keys
            sample_keys: List[str] = []
            for pattern in ["avail:*", "availability:*"]:
                keys = list(cache_service.redis.scan_iter(match=pattern, count=10))
                sample_keys.extend(keys[:5])  # Limit to 5 per pattern

            top_keys = sample_keys[:10]  # Top 10 keys
        except Exception as e:
            top_keys = [f"Error retrieving keys: {e}"]

    # Performance recommendations
    recommendations: List[str] = []
    if avail_total > 0:
        hit_rate = avail_hits / avail_total
        if hit_rate < 0.7:
            recommendations.append("Consider increasing availability cache TTL")
        if avail_invalidations > avail_hits * 0.5:
            recommendations.append("High invalidation rate - consider optimizing booking patterns")
        if avail_misses > avail_hits:
            recommendations.append("More misses than hits - check cache warming strategy")

    if not recommendations:
        recommendations.append("Availability caching performance is optimal")

    return AvailabilityCacheMetricsResponse(
        availability_cache_metrics=availability_metrics,
        top_cached_keys_sample=top_keys,
        recommendations=recommendations,
        cache_tiers_info={
            "hot": "5 minutes (current/future availability)",
            "warm": "1 hour (past availability)",
            "cold": "24 hours (historical data)",
        },
    )


@router.get(
    "/slow-queries",
    response_model=SlowQueriesResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
async def get_slow_queries(db: Session = Depends(get_db)) -> SlowQueriesResponse:
    """Get recent slow queries."""
    # Get slow queries from PostgreSQL
    try:
        result = db.execute(
            text(
                """
            SELECT
                query,
                mean_exec_time,
                calls,
                total_exec_time
            FROM pg_stat_statements
            WHERE mean_exec_time > 100
            ORDER BY mean_exec_time DESC
            LIMIT 20
        """
            )
        )

        slow_queries: JsonList = []
        for row in result:
            slow_queries.append(
                {
                    "query": row[0][:200],  # First 200 chars
                    "duration_ms": float(row[1]),
                    "timestamp": datetime.now(timezone.utc),  # Approximate timestamp
                    "endpoint": None,  # Not available from pg_stat_statements
                }
            )

        return SlowQueriesResponse(
            slow_queries=slow_queries,
            total_count=len(slow_queries),
        )
    except Exception:
        # Return empty list if pg_stat_statements not available
        return SlowQueriesResponse(
            slow_queries=[],
            total_count=0,
        )


@router.post(
    "/cache/reset-stats",
    response_model=SuccessResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
async def reset_cache_stats(
    cache_service: Optional[CacheService] = Depends(get_cache_service_dep),
) -> SuccessResponse:
    """Reset cache statistics."""

    if cache_service:
        cache_service.reset_stats()
        return SuccessResponse(
            success=True,
            message="Cache statistics have been reset",
        )

    raise HTTPException(status_code=503, detail="Cache service not available")


@router.get(
    "/rate-limits",
    response_model=RateLimitStats,
    dependencies=[Depends(_ensure_ops_access)],
)
def get_rate_limit_stats() -> RateLimitStats:
    """
    Get current rate limit statistics.

    Shows:
    - Total rate limit keys
    - Breakdown by endpoint/type
    - Top limited clients

    Requires authentication.
    """
    stats = _coerce_json_dict(
        RateLimitAdmin.get_rate_limit_stats(), "Unexpected rate limit stats format"
    )
    return RateLimitStats(**stats)


@router.post(
    "/rate-limits/reset",
    response_model=RateLimitResetResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
def reset_rate_limits(
    pattern: str = Query(..., description="Pattern to match (e.g., 'email_*', 'ip_192.168.*')"),
) -> RateLimitResetResponse:
    """
    Reset rate limits matching a pattern.

    Useful for:
    - Unblocking legitimate users
    - Testing
    - Emergency response

    Requires admin privileges.
    """
    count = RateLimitAdmin.reset_all_limits(pattern)

    return RateLimitResetResponse(
        status="success",
        pattern=pattern,
        limits_reset=count,
        message=f"Reset {count} rate limits matching pattern '{pattern}'",
    )


@router.get(
    "/rate-limits/test",
    response_model=RateLimitTestResponse,
    dependencies=[Depends(_ensure_ops_access)],
)
@rate_limit("3/minute", key_type=RateLimitKeyType.IP)
async def test_rate_limit(
    request: Request,  # Add this for rate limiting
    requests: int = Query(default=5, ge=1, le=20, description="Number of requests to simulate"),
) -> RateLimitTestResponse:
    """
    Test endpoint to verify rate limiting is working.

    This endpoint has a low rate limit for testing purposes.
    Try making multiple requests to see rate limiting in action.
    """
    return RateLimitTestResponse(
        message="Rate limit test successful",
        timestamp=datetime.now().isoformat(),
        note="This endpoint is rate limited to 3 requests per minute",
    )


# Apply rate limit to the test endpoint
test_rate_limit = rate_limit("3/minute", key_type=RateLimitKeyType.IP)(test_rate_limit)
