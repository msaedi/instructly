# backend/app/routes/monitoring.py
"""
Production monitoring endpoints for performance tracking.

Provides real-time insights into:
- Database performance
- Cache effectiveness
- Request latency
- System health
"""

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import get_db, get_db_pool_status
from ..monitoring.production_monitor import monitor
from ..services.cache_service import get_cache_service

router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)


async def verify_monitoring_api_key(api_key: Optional[str] = Header(None, alias="X-Monitoring-API-Key")):
    """
    Verify access to monitoring endpoints using API key.

    In production, requires valid monitoring API key.
    In development, allows access without key.

    For user-based access, use require_permission(PermissionName.ACCESS_MONITORING) instead.
    """
    # Allow in development without key
    if settings.environment != "production":
        return

    # Require API key for external monitoring
    monitoring_api_key = os.getenv("MONITORING_API_KEY")
    if not monitoring_api_key:
        raise HTTPException(status_code=503, detail="Monitoring API key not configured")

    if api_key != monitoring_api_key:
        raise HTTPException(status_code=403, detail="Invalid monitoring API key")


@router.get("/dashboard")
async def get_monitoring_dashboard(
    db: Session = Depends(get_db), _: None = Depends(verify_monitoring_api_key)
) -> Dict[str, Any]:
    """
    Get comprehensive monitoring dashboard data.

    Requires monitoring API key in production.
    """
    try:
        # Get performance summary from monitor
        performance = monitor.get_performance_summary()

        # Get cache statistics
        cache_service = get_cache_service(db)
        cache_stats = cache_service.get_stats()
        cache_health = monitor.check_cache_health(cache_stats)

        # Get current database pool status
        db_pool = get_db_pool_status()

        # Build dashboard response
        return {
            "status": "ok",
            "timestamp": performance["timestamp"],
            "database": {
                **performance["database"],
                "pool": db_pool,
            },
            "cache": cache_health,
            "requests": performance["requests"],
            "memory": performance["memory"],
            "alerts": performance["alerts"],
            "recommendations": _generate_recommendations(performance, cache_health),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Monitoring error: {str(e)}")


@router.get("/slow-queries")
async def get_slow_queries(limit: int = 10, _: None = Depends(verify_monitoring_api_key)) -> Dict[str, Any]:
    """Get recent slow queries."""
    return {
        "slow_queries": list(monitor.slow_queries)[-limit:],
        "total_count": len(monitor.slow_queries),
    }


@router.get("/slow-requests")
async def get_slow_requests(limit: int = 10, _: None = Depends(verify_monitoring_api_key)) -> Dict[str, Any]:
    """Get recent slow requests."""
    return {
        "slow_requests": list(monitor.slow_requests)[-limit:],
        "total_count": len(monitor.slow_requests),
    }


@router.get("/cache/extended-stats")
async def get_extended_cache_stats(
    db: Session = Depends(get_db), _: None = Depends(verify_monitoring_api_key)
) -> Dict[str, Any]:
    """Get extended cache statistics."""
    cache_service = get_cache_service(db)

    # Check if we have the extended stats method
    if hasattr(cache_service, "get_extended_stats"):
        return cache_service.get_extended_stats()
    else:
        return cache_service.get_stats()


@router.post("/alerts/acknowledge/{alert_type}")
async def acknowledge_alert(alert_type: str, _: None = Depends(verify_monitoring_api_key)) -> Dict[str, Any]:
    """Acknowledge an alert to reset its cooldown."""
    if alert_type in monitor._last_alert_time:
        del monitor._last_alert_time[alert_type]
        return {"status": "acknowledged", "alert_type": alert_type}
    else:
        raise HTTPException(status_code=404, detail=f"Alert type '{alert_type}' not found")


def _generate_recommendations(performance: Dict[str, Any], cache_health: Dict[str, Any]) -> list:
    """Generate performance recommendations based on current metrics."""
    recommendations = []

    # Database recommendations
    db_data = performance.get("database", {})
    if db_data.get("average_pool_usage_percent", 0) > 70:
        recommendations.append(
            {
                "type": "database",
                "severity": "warning",
                "message": "High database pool usage. Consider optimizing queries or increasing pool size.",
                "action": "Review slow queries and add indexes where needed.",
            }
        )

    if db_data.get("slow_queries_count", 0) > 20:
        recommendations.append(
            {
                "type": "database",
                "severity": "warning",
                "message": f"{db_data['slow_queries_count']} slow queries detected.",
                "action": "Analyze slow query log and optimize problematic queries.",
            }
        )

    # Cache recommendations
    if cache_health.get("recommendations"):
        for rec in cache_health["recommendations"]:
            recommendations.append(
                {
                    "type": "cache",
                    "severity": "info",
                    "message": rec,
                    "action": "Review cache usage patterns and TTL configuration.",
                }
            )

    # Memory recommendations
    memory_data = performance.get("memory", {})
    if memory_data.get("percent", 0) > 70:
        recommendations.append(
            {
                "type": "memory",
                "severity": "warning",
                "message": f"High memory usage: {memory_data['percent']}%",
                "action": "Consider restarting workers or investigating memory leaks.",
            }
        )

    # Request recommendations
    request_data = performance.get("requests", {})
    if request_data.get("active_count", 0) > 50:
        recommendations.append(
            {
                "type": "requests",
                "severity": "warning",
                "message": f"{request_data['active_count']} active requests (possible backlog)",
                "action": "Check for blocking operations or increase worker count.",
            }
        )

    return recommendations
