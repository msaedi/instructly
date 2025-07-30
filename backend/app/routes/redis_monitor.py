# backend/app/routes/redis_monitor.py
"""
Redis monitoring endpoint for tracking usage and health.

Provides insights into Redis operations, memory usage, and Celery queue status.
"""

import logging
from typing import Any, Dict

import redis
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.enums import PermissionName
from app.dependencies.permissions import require_permission
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/redis",
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)


def get_redis_client() -> redis.Redis:
    """Get Redis client instance."""
    redis_url = settings.redis_url or "redis://localhost:6379/0"
    return redis.from_url(redis_url, decode_responses=True)


@router.get("/health", response_model=Dict[str, Any])
async def redis_health() -> Dict[str, Any]:
    """
    Check Redis connection health.

    Returns:
        Basic health status
    """
    try:
        client = get_redis_client()
        client.ping()
        return {"status": "healthy", "connected": True}
    except (redis.ConnectionError, redis.TimeoutError) as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "connected": False, "error": str(e)}


@router.get("/stats", response_model=Dict[str, Any])
async def redis_stats(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> Dict[str, Any]:
    """
    Get detailed Redis statistics and metrics.

    Requires ACCESS_MONITORING permission.

    Returns:
        Comprehensive Redis metrics including:
        - Memory usage
        - Connection stats
        - Operation counts
        - Celery queue lengths
    """

    try:
        client = get_redis_client()

        # Get Redis INFO
        info = client.info()

        # Extract key metrics
        memory_info = {
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "N/A"),
            "used_memory_rss_human": info.get("used_memory_rss_human", "N/A"),
            "maxmemory_human": info.get("maxmemory_human", "N/A"),
            "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0),
        }

        stats = {
            "total_connections_received": info.get("total_connections_received", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "rejected_connections": info.get("rejected_connections", 0),
            "expired_keys": info.get("expired_keys", 0),
            "evicted_keys": info.get("evicted_keys", 0),
        }

        clients = {
            "connected_clients": info.get("connected_clients", 0),
            "blocked_clients": info.get("blocked_clients", 0),
        }

        # Get Celery queue lengths
        celery_queues = _get_celery_queue_lengths(client)

        # Estimate daily operations based on current rate
        ops_per_sec = info.get("instantaneous_ops_per_sec", 0)
        estimated_daily_ops = ops_per_sec * 86400  # seconds in a day

        return {
            "status": "connected",
            "server": {
                "redis_version": info.get("redis_version", "unknown"),
                "uptime_in_days": info.get("uptime_in_days", 0),
            },
            "memory": memory_info,
            "stats": stats,
            "clients": clients,
            "celery": celery_queues,
            "operations": {
                "current_ops_per_sec": ops_per_sec,
                "estimated_daily_ops": int(estimated_daily_ops),
                "estimated_monthly_ops": int(estimated_daily_ops * 30),
            },
        }

    except Exception as e:
        logger.error(f"Failed to get Redis stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve Redis statistics: {str(e)}"
        )


@router.get("/celery-queues", response_model=Dict[str, Any])
async def celery_queue_status(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> Dict[str, Any]:
    """
    Get Celery queue status and pending tasks.

    Requires ACCESS_MONITORING permission.

    Returns:
        Queue lengths and task counts
    """

    try:
        client = get_redis_client()
        queues = _get_celery_queue_lengths(client)

        return {
            "status": "ok",
            "queues": queues,
            "total_pending": sum(queues.values()),
        }

    except Exception as e:
        logger.error(f"Failed to get Celery queue status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve queue status: {str(e)}"
        )


def _get_celery_queue_lengths(client: redis.Redis) -> Dict[str, int]:
    """Get lengths of all Celery queues."""
    queue_names = [
        "celery",
        "email",
        "notifications",
        "analytics",
        "maintenance",
        "bookings",
        "cache",
    ]

    queue_lengths = {}
    for queue in queue_names:
        try:
            # Celery uses the queue name as the Redis key
            length = client.llen(queue)
            if length > 0:
                queue_lengths[queue] = length
        except Exception as e:
            logger.warning(f"Failed to get length of queue {queue}: {e}")
            queue_lengths[queue] = -1

    return queue_lengths


@router.delete("/flush-queues", response_model=Dict[str, Any])
async def flush_celery_queues(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> Dict[str, Any]:
    """
    Flush all Celery queues (DANGER: removes all pending tasks).

    Requires ACCESS_MONITORING permission.
    Use with caution - this will delete all pending tasks!

    Returns:
        Number of tasks removed from each queue
    """

    try:
        client = get_redis_client()

        queue_names = [
            "celery",
            "email",
            "notifications",
            "analytics",
            "maintenance",
            "bookings",
            "cache",
        ]

        flushed = {}
        total_removed = 0

        for queue in queue_names:
            try:
                # Get current length before deletion
                length = client.llen(queue)
                if length > 0:
                    # Delete the queue
                    client.delete(queue)
                    flushed[queue] = length
                    total_removed += length
            except Exception as e:
                logger.error(f"Failed to flush queue {queue}: {e}")
                flushed[queue] = f"error: {str(e)}"

        return {
            "status": "completed",
            "queues_flushed": flushed,
            "total_tasks_removed": total_removed,
        }

    except Exception as e:
        logger.error(f"Failed to flush queues: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to flush queues: {str(e)}"
        )


# Optional: Add to your main.py router includes:
# app.include_router(redis_monitor.router)
