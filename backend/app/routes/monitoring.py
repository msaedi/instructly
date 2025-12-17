"""
Monitoring endpoints for health checks and diagnostics.

These endpoints are secured and used for internal monitoring and operations.
"""

import asyncio
from datetime import datetime, timezone
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from ..repositories.payment_monitoring_repository import PaymentMonitoringRepository

from ..core.config import settings
from ..database import get_db, get_db_pool_status
from ..monitoring.production_monitor import monitor
from ..schemas.monitoring_responses import (
    AlertAcknowledgeResponse,
    ExtendedCacheStats,
    MonitoringDashboardResponse,
    PaymentHealthCheckTriggerResponse,
    PaymentHealthResponse,
    SlowQueriesResponse,
    SlowRequestsResponse,
)
from ..services.cache_service import get_cache_service

router = APIRouter(
    prefix="/api/monitoring",
    tags=["Monitoring"],
    responses={404: {"description": "Not found"}},
)


async def verify_monitoring_api_key(
    api_key: Optional[str] = Header(None, alias="X-Monitoring-API-Key"),
) -> None:
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


@router.get("/dashboard", response_model=MonitoringDashboardResponse)
async def get_monitoring_dashboard(
    db: Session = Depends(get_db), _: None = Depends(verify_monitoring_api_key)
) -> MonitoringDashboardResponse:
    """
    Get comprehensive monitoring dashboard data.

    Requires monitoring API key in production.
    """
    try:
        # Get performance summary from monitor
        performance = monitor.get_performance_summary()

        # Get cache statistics
        cache_service = get_cache_service(db)
        cache_stats = await cache_service.get_stats()
        cache_health = monitor.check_cache_health(cache_stats)

        # Get current database pool status
        db_pool = get_db_pool_status()

        # Build dashboard response
        return MonitoringDashboardResponse(
            status="ok",
            timestamp=performance["timestamp"],
            database={
                **performance["database"],
                "pool": db_pool,
            },
            cache=cache_health,
            requests=performance["requests"],
            memory=performance["memory"],
            alerts=performance["alerts"],
            recommendations=_generate_recommendations(performance, cache_health),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Monitoring error: {str(e)}")


@router.get("/slow-queries", response_model=SlowQueriesResponse)
async def get_slow_queries(
    limit: int = 10, _: None = Depends(verify_monitoring_api_key)
) -> SlowQueriesResponse:
    """Get recent slow queries."""
    return SlowQueriesResponse(
        slow_queries=list(monitor.slow_queries)[-limit:],
        total_count=len(monitor.slow_queries),
    )


@router.get("/slow-requests", response_model=SlowRequestsResponse)
async def get_slow_requests(
    limit: int = 10, _: None = Depends(verify_monitoring_api_key)
) -> SlowRequestsResponse:
    """Get recent slow requests."""
    return SlowRequestsResponse(
        slow_requests=list(monitor.slow_requests)[-limit:],
        total_count=len(monitor.slow_requests),
    )


@router.get("/cache/extended-stats", response_model=ExtendedCacheStats)
async def get_extended_cache_stats(
    db: Session = Depends(get_db), _: None = Depends(verify_monitoring_api_key)
) -> ExtendedCacheStats:
    """Get extended cache statistics."""
    cache_service = get_cache_service(db)

    stats = await cache_service.get_stats()

    return ExtendedCacheStats(
        basic_stats=stats.get("basic_stats", stats),
        redis_info=stats.get("redis_info") or stats.get("redis"),
        key_patterns=stats.get("key_patterns"),
    )


@router.post("/alerts/acknowledge/{alert_type}", response_model=AlertAcknowledgeResponse)
async def acknowledge_alert(
    alert_type: str, _: None = Depends(verify_monitoring_api_key)
) -> AlertAcknowledgeResponse:
    """Acknowledge an alert to reset its cooldown."""
    if alert_type in monitor._last_alert_time:
        del monitor._last_alert_time[alert_type]
        return AlertAcknowledgeResponse(status="acknowledged", alert_type=alert_type)
    else:
        raise HTTPException(status_code=404, detail=f"Alert type '{alert_type}' not found")


def _generate_recommendations(
    performance: Dict[str, Any], cache_health: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Generate performance recommendations based on current metrics."""
    recommendations: List[Dict[str, str]] = []

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


# ==================== Payment System Monitoring ====================


def get_payment_monitoring_repository(
    db: Session = Depends(get_db),
) -> "PaymentMonitoringRepository":
    """Get an instance of the payment monitoring repository."""
    from ..repositories.payment_monitoring_repository import PaymentMonitoringRepository

    return PaymentMonitoringRepository(db)


@router.get("/payment-health", response_model=PaymentHealthResponse)
async def get_payment_system_health(
    repository: "PaymentMonitoringRepository" = Depends(get_payment_monitoring_repository),
    _: None = Depends(verify_monitoring_api_key),
) -> PaymentHealthResponse:
    """
    Get payment system health metrics.

    Returns metrics about:
    - Pending authorizations
    - Failed authorizations
    - Recent processing activity
    - System alerts

    Requires monitoring API key in production.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Count bookings by payment status
    payment_stats = await asyncio.to_thread(repository.get_payment_status_counts, now)
    stats_dict = {stat.payment_status: stat.count for stat in payment_stats if stat.payment_status}

    # Count recent events
    recent_events = await asyncio.to_thread(
        repository.get_recent_event_counts, now - timedelta(hours=24)
    )
    events_dict = {event.event_type: event.count for event in recent_events}

    # Find overdue authorizations
    overdue_bookings = await asyncio.to_thread(repository.count_overdue_authorizations, now)

    # Get last successful authorization
    last_auth = await asyncio.to_thread(repository.get_last_successful_authorization)

    minutes_since_auth = None
    if last_auth:
        time_diff = now - last_auth.created_at
        minutes_since_auth = int(time_diff.total_seconds() / 60)

    # Determine health status
    health_status = "healthy"
    alerts = []

    if overdue_bookings > 5:
        health_status = "warning"
        alerts.append(f"{overdue_bookings} bookings overdue for authorization")

    if overdue_bookings > 10:
        health_status = "critical"

    if minutes_since_auth and minutes_since_auth > 120:
        if health_status == "healthy":
            health_status = "warning"
        alerts.append(f"No successful authorizations in {minutes_since_auth} minutes")

    failed_auth_count = stats_dict.get("auth_failed", 0)
    if failed_auth_count > 5:
        alerts.append(f"{failed_auth_count} bookings with failed authorization")

    return PaymentHealthResponse(
        status=health_status,
        timestamp=now.isoformat(),
        payment_stats=stats_dict,
        recent_events=events_dict,
        overdue_authorizations=overdue_bookings,
        minutes_since_last_auth=minutes_since_auth,
        alerts=alerts,
        metrics={
            "pending": stats_dict.get("pending_payment_method", 0),
            "scheduled": stats_dict.get("scheduled", 0),
            "authorized": stats_dict.get("authorized", 0),
            "captured": stats_dict.get("captured", 0),
            "failed": failed_auth_count,
            "abandoned": stats_dict.get("auth_abandoned", 0),
        },
    )


@router.post("/trigger-payment-health-check", response_model=PaymentHealthCheckTriggerResponse)
async def trigger_payment_health_check(
    _: None = Depends(verify_monitoring_api_key),
) -> PaymentHealthCheckTriggerResponse:
    """
    Manually trigger a payment system health check.

    This will run the health check task immediately and return the results.

    Requires monitoring API key in production.
    """
    # datetime already available where needed above; avoid re-import
    try:
        from app.tasks.payment_tasks import check_authorization_health

        # Trigger the task asynchronously
        task = check_authorization_health.delay()

        return PaymentHealthCheckTriggerResponse(
            status="triggered",
            task_id=task.id,
            message="Health check task has been queued",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger health check: {str(e)}")
