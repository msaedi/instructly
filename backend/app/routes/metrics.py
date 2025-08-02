# backend/app/routes/metrics.py
"""
Simple metrics endpoint for performance monitoring.

This gives us immediate visibility without Prometheus complexity.
"""

from datetime import datetime

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user, get_current_user
from ..api.dependencies.services import (
    get_availability_service,
    get_booking_service,
    get_cache_service_dep,
    get_conflict_checker,
)
from ..database import get_db, get_db_pool_status
from ..middleware.rate_limiter import RateLimitAdmin, RateLimitKeyType, rate_limit
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

router = APIRouter(prefix="/metrics", tags=["monitoring"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Basic health check endpoint."""
    return HealthCheckResponse(
        status="healthy",
        service="InstaInstru API",
        version="1.0.0",
        timestamp=datetime.utcnow(),
        checks={"api": True},
    )


@router.get("/performance", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
    availability_service=Depends(get_availability_service),
    booking_service=Depends(get_booking_service),
    conflict_checker=Depends(get_conflict_checker),
    cache_service: CacheService = Depends(get_cache_service_dep),
    db: Session = Depends(get_db),
) -> PerformanceMetricsResponse:
    """Get performance metrics from all services."""

    # Only allow admin users or specific monitoring user
    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com", "sarah.chen@example.com"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Cache metrics
    cache_stats = cache_service.get_stats() if cache_service else {"error": "Cache service not available"}

    # System metrics
    system_metrics = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage("/").percent,
    }

    # Database metrics
    db_stats = db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
    database_metrics = {
        "active_connections": db_stats,
        "pool_status": get_db_pool_status(),
    }

    return PerformanceMetricsResponse(
        availability_service=availability_service.get_metrics(),
        booking_service=booking_service.get_metrics(),
        conflict_checker=conflict_checker.get_metrics(),
        cache=cache_stats,
        system=system_metrics,
        database=database_metrics,
    )


@router.get("/cache", response_model=CacheMetricsResponse)
async def get_cache_metrics(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> CacheMetricsResponse:
    """Get detailed cache metrics including availability-specific stats."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if not cache_service:
        raise HTTPException(status_code=503, detail="Cache service not available")

    # Get basic cache stats
    stats = cache_service.get_stats()

    # Add availability-specific metrics
    availability_stats = {
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
    redis_info = None
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


def _get_cache_performance_insights(stats):
    """Generate performance insights from cache statistics."""
    insights = []

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


@router.get("/cache/availability", response_model=AvailabilityCacheMetricsResponse)
async def get_availability_cache_metrics(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> AvailabilityCacheMetricsResponse:
    """Get detailed availability-specific cache metrics and top cached keys."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

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
    top_keys = []
    if hasattr(cache_service, "redis") and cache_service.redis:
        try:
            # Sample some availability-related keys
            sample_keys = []
            for pattern in ["avail:*", "availability:*"]:
                keys = list(cache_service.redis.scan_iter(match=pattern, count=10))
                sample_keys.extend(keys[:5])  # Limit to 5 per pattern

            top_keys = sample_keys[:10]  # Top 10 keys
        except Exception as e:
            top_keys = [f"Error retrieving keys: {e}"]

    # Performance recommendations
    recommendations = []
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


@router.get("/slow-queries", response_model=SlowQueriesResponse)
async def get_slow_queries(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SlowQueriesResponse:
    """Get recent slow queries."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

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

        slow_queries = []
        for row in result:
            slow_queries.append(
                {
                    "query": row[0][:200],  # First 200 chars
                    "duration_ms": float(row[1]),
                    "timestamp": datetime.utcnow(),  # Approximate timestamp
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


@router.post("/cache/reset-stats", response_model=SuccessResponse)
async def reset_cache_stats(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> SuccessResponse:
    """Reset cache statistics."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if cache_service:
        cache_service.reset_stats()
        return SuccessResponse(
            success=True,
            message="Cache statistics have been reset",
        )

    raise HTTPException(status_code=503, detail="Cache service not available")


@router.get("/rate-limits", response_model=RateLimitStats)
def get_rate_limit_stats(
    current_user: User = Depends(get_current_active_user),
) -> RateLimitStats:
    """
    Get current rate limit statistics.

    Shows:
    - Total rate limit keys
    - Breakdown by endpoint/type
    - Top limited clients

    Requires authentication.
    """
    return RateLimitAdmin.get_rate_limit_stats()


@router.post("/rate-limits/reset", response_model=RateLimitResetResponse)
def reset_rate_limits(
    pattern: str = Query(..., description="Pattern to match (e.g., 'email_*', 'ip_192.168.*')"),
    current_user: User = Depends(get_current_active_user),
) -> RateLimitResetResponse:
    """
    Reset rate limits matching a pattern.

    Useful for:
    - Unblocking legitimate users
    - Testing
    - Emergency response

    Requires admin privileges.
    """
    # Simple admin check - improve in production
    if current_user.email not in ["admin@instainstru.com", "support@instainstru.com"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can reset rate limits")

    count = RateLimitAdmin.reset_all_limits(pattern)

    return RateLimitResetResponse(
        status="success",
        pattern=pattern,
        limits_reset=count,
        message=f"Reset {count} rate limits matching pattern '{pattern}'",
    )


@router.get("/rate-limits/test", response_model=RateLimitTestResponse)
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
