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
from ..services.cache_service import CacheService

router = APIRouter(prefix="/metrics", tags=["monitoring"])


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "InstaInstru API"}


@router.get("/performance")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
    availability_service=Depends(get_availability_service),
    booking_service=Depends(get_booking_service),
    conflict_checker=Depends(get_conflict_checker),
    cache_service: CacheService = Depends(get_cache_service_dep),
    db: Session = Depends(get_db),
):
    """Get performance metrics from all services."""

    # Only allow admin users or specific monitoring user
    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com", "sarah.chen@example.com"]:
        return {"error": "Unauthorized"}

    # Collect service metrics
    metrics = {
        "availability_service": availability_service.get_metrics(),
        "booking_service": booking_service.get_metrics(),
        "conflict_checker": conflict_checker.get_metrics(),
    }

    # Cache metrics
    if cache_service:
        metrics["cache"] = cache_service.get_stats()
    else:
        metrics["cache"] = {"error": "Cache service not available"}

    # System metrics
    metrics["system"] = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage("/").percent,
    }

    # Database metrics
    db_stats = db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
    metrics["database"] = {
        "active_connections": db_stats,
        "pool_status": get_db_pool_status(),
    }

    return metrics


@router.get("/cache")
async def get_cache_metrics(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep),
):
    """Get detailed cache metrics including availability-specific stats."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}

    if not cache_service:
        return {"error": "Cache service not available"}

    # Get basic cache stats
    stats = cache_service.get_stats()

    # Add availability-specific metrics
    availability_stats = {
        "availability_hit_rate": 0,
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
    cache_info = {}
    if hasattr(cache_service, "redis") and cache_service.redis:
        try:
            # Get approximate cache size
            info = cache_service.redis.info()
            cache_info = {
                "used_memory_human": info.get("used_memory_human", "Unknown"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
            }
        except Exception as e:
            cache_info = {"error": f"Could not get Redis info: {e}"}

    # Combine all metrics
    enhanced_stats = {
        **stats,
        "availability_metrics": availability_stats,
        "redis_info": cache_info,
        "performance_insights": _get_cache_performance_insights(stats),
    }

    return enhanced_stats


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


@router.get("/cache/availability")
async def get_availability_cache_metrics(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep),
):
    """Get detailed availability-specific cache metrics and top cached keys."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}

    if not cache_service:
        return {"error": "Cache service not available"}

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

    return {
        "availability_cache_metrics": availability_metrics,
        "top_cached_keys_sample": top_keys,
        "recommendations": recommendations,
        "cache_tiers_info": {
            "hot": "5 minutes (current/future availability)",
            "warm": "1 hour (past availability)",
            "cold": "24 hours (historical data)",
        },
    }


@router.get("/slow-queries")
async def get_slow_queries(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get recent slow queries."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}

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
                    "avg_time_ms": row[1],
                    "calls": row[2],
                    "total_time_ms": row[3],
                }
            )

        return {"slow_queries": slow_queries}
    except Exception as e:
        return {"error": f"pg_stat_statements not available: {str(e)}"}


@router.post("/cache/reset-stats")
async def reset_cache_stats(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep),
):
    """Reset cache statistics."""

    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}

    if cache_service:
        cache_service.reset_stats()
        return {"status": "Cache stats reset"}

    return {"error": "Cache service not available"}


@router.get("/rate-limits")
def get_rate_limit_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current rate limit statistics.

    Shows:
    - Total rate limit keys
    - Breakdown by endpoint/type
    - Top limited clients

    Requires authentication.
    """
    return RateLimitAdmin.get_rate_limit_stats()


@router.post("/rate-limits/reset")
def reset_rate_limits(
    pattern: str = Query(..., description="Pattern to match (e.g., 'email_*', 'ip_192.168.*')"),
    current_user: User = Depends(get_current_active_user),
):
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

    return {
        "status": "success",
        "pattern": pattern,
        "limits_reset": count,
        "message": f"Reset {count} rate limits matching pattern '{pattern}'",
    }


@router.get("/rate-limits/test")
@rate_limit("3/minute", key_type=RateLimitKeyType.IP)
async def test_rate_limit(
    request: Request,  # Add this for rate limiting
    requests: int = Query(default=5, ge=1, le=20, description="Number of requests to simulate"),
):
    """
    Test endpoint to verify rate limiting is working.

    This endpoint has a low rate limit for testing purposes.
    Try making multiple requests to see rate limiting in action.
    """
    return {
        "message": "Rate limit test successful",
        "timestamp": datetime.now().isoformat(),
        "note": "This endpoint is rate limited to 3 requests per minute",
    }


# Apply rate limit to the test endpoint
test_rate_limit = rate_limit("3/minute", key_type=RateLimitKeyType.IP)(test_rate_limit)
