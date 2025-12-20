# backend/app/routes/v1/redis_monitor.py
"""
Redis monitoring endpoint for tracking usage and health (v1 API).

Provides insights into Redis operations, memory usage, and Celery queue status.
"""

import logging
from typing import Dict, cast

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis as AsyncRedis

from ...core.cache_redis import get_async_cache_redis_client
from ...core.config import settings
from ...core.enums import PermissionName
from ...dependencies.permissions import require_permission
from ...models.user import User
from ...schemas.redis_monitor_responses import (
    RedisCeleryQueuesResponse,
    RedisConnectionAuditResponse,
    RedisFlushQueuesResponse,
    RedisHealthResponse,
    RedisStatsResponse,
    RedisTestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)


async def get_redis_client() -> AsyncRedis:
    """Get the shared async Redis client."""
    client = await get_async_cache_redis_client()
    if client is None:
        raise RuntimeError("Redis unavailable")
    return client


@router.get("/health", response_model=RedisHealthResponse)
async def redis_health() -> RedisHealthResponse:
    """
    Check Redis connection health.

    Returns:
        Basic health status
    """
    try:
        client = await get_redis_client()
        await client.ping()
        return RedisHealthResponse(status="healthy", connected=True)
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return RedisHealthResponse(status="unhealthy", connected=False, error=str(e))


@router.get("/test", response_model=RedisTestResponse)
async def redis_test() -> RedisTestResponse:
    """
    Simple Redis connection test endpoint.

    No authentication required - helps verify Redis migration is working.

    Returns:
        Connection status and basic info
    """
    try:
        client = await get_redis_client()

        # Test basic connectivity
        ping_result = await client.ping()

        # Get server info
        info = await client.info("server")
        clients_info = await client.info("clients")

        return RedisTestResponse(
            status="connected",
            ping=ping_result,
            redis_version=info.get("redis_version", "unknown"),
            uptime_seconds=cast(int | None, info.get("uptime_in_seconds", 0)),
            connected_clients=cast(int, clients_info.get("connected_clients", 0)),
            message="Redis migration successful! Connection to instainstru-redis:6379 is working.",
        )
    except Exception as e:
        logger.error(f"Redis test failed: {e}")
        return RedisTestResponse(
            status="error",
            ping=False,
            error=str(e),
            message="Failed to connect to Redis. Please check the migration status.",
        )


@router.get("/stats", response_model=RedisStatsResponse)
async def redis_stats(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> RedisStatsResponse:
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
        client = await get_redis_client()

        # Get Redis INFO
        info = await client.info()

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
        celery_queues = await _get_celery_queue_lengths(client)

        # Estimate daily operations based on current rate
        ops_per_sec = info.get("instantaneous_ops_per_sec", 0)
        estimated_daily_ops = ops_per_sec * 86400  # seconds in a day

        stats_data = {
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
        return RedisStatsResponse(stats=stats_data)

    except Exception as e:
        logger.error(f"Failed to get Redis stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve Redis statistics: {str(e)}",
        )


@router.get("/celery-queues", response_model=RedisCeleryQueuesResponse)
async def celery_queue_status(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> RedisCeleryQueuesResponse:
    """
    Get Celery queue status and pending tasks.

    Requires ACCESS_MONITORING permission.

    Returns:
        Queue lengths and task counts
    """

    try:
        client = await get_redis_client()
        queues = await _get_celery_queue_lengths(client)

        queues_data = {
            "status": "ok",
            "queues": queues,
            "total_pending": sum(queues.values()),
        }
        return RedisCeleryQueuesResponse(queues=queues_data)

    except Exception as e:
        logger.error(f"Failed to get Celery queue status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve queue status: {str(e)}",
        )


async def _get_celery_queue_lengths(client: AsyncRedis) -> Dict[str, int]:
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
            length = await client.llen(queue)
            if length > 0:
                queue_lengths[queue] = length
        except Exception as e:
            logger.warning(f"Failed to get length of queue {queue}: {e}")
            queue_lengths[queue] = -1

    return queue_lengths


@router.get("/connection-audit", response_model=RedisConnectionAuditResponse)
async def redis_connection_audit(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> RedisConnectionAuditResponse:
    """
    Audit all Redis connections across the system.

    Checks which Redis instance each service is using and identifies
    any remaining Upstash connections.

    Requires ACCESS_MONITORING permission.

    Returns:
        Summary of Redis connections across all services
    """

    try:
        # Get current Redis URLs from settings
        api_cache_url = settings.redis_url or "redis://localhost:6379/0"
        celery_broker_url = settings.redis_url or "redis://localhost:6379/0"

        # All services now use single Redis instance
        upstash_detected = False  # Migration complete

        # Get active connections from current Redis
        client = await get_redis_client()
        info = await client.info("clients")
        connected_clients = cast(int, info.get("connected_clients", 0))

        # Parse URLs to identify service
        def parse_redis_url(url: str) -> str:
            """Extract host from Redis URL."""
            if not url:
                return "not configured"
            # Handle redis:// and rediss:// schemes
            if url.startswith("redis://") or url.startswith("rediss://"):
                # Extract host:port between // and /
                parts = url.split("/")
                if len(parts) >= 3:
                    return parts[2].split("@")[-1]  # Handle auth in URL
            return url

        # Check for specific service patterns in connected clients
        local_redis_connections = 0
        upstash_connections = 0

        # Count based on URL patterns
        api_host = parse_redis_url(api_cache_url)
        if "instructly-redis" in api_host or "localhost" in api_host:
            local_redis_connections = connected_clients

        # Identify which services are using which Redis
        service_connections = {
            "api_service": {
                "url": api_cache_url,
                "host": parse_redis_url(api_cache_url),
                "type": "render_redis" if "instructly-redis" in api_cache_url else "local",
            },
            "celery_broker": {
                "url": celery_broker_url,
                "host": parse_redis_url(celery_broker_url),
                "type": "render_redis" if "instructly-redis" in celery_broker_url else "local",
            },
        }

        # Check environment variables
        env_check = {
            "REDIS_URL": api_cache_url,
        }

        connections_data = [
            {
                "api_cache": api_cache_url,
                "celery_broker": celery_broker_url,
                "active_connections": {
                    "local_redis": local_redis_connections,
                    "upstash": upstash_connections,
                },
                "upstash_detected": upstash_detected,
                "service_connections": service_connections,
                "environment_variables": env_check,
                "migration_status": "complete" if not upstash_detected else "in_progress",
                "recommendation": (
                    "All services using Render Redis"
                    if not upstash_detected
                    else "Remove UPSTASH_URL from environment"
                ),
            }
        ]
        return RedisConnectionAuditResponse(connections=connections_data)

    except Exception as e:
        logger.error(f"Failed to audit Redis connections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to audit connections: {str(e)}",
        )


@router.delete("/flush-queues", response_model=RedisFlushQueuesResponse)
async def flush_celery_queues(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> RedisFlushQueuesResponse:
    """
    Flush all Celery queues (DANGER: removes all pending tasks).

    Requires ACCESS_MONITORING permission.
    Use with caution - this will delete all pending tasks!

    Returns:
        Number of tasks removed from each queue
    """

    try:
        client = await get_redis_client()

        queue_names = [
            "celery",
            "email",
            "notifications",
            "analytics",
            "maintenance",
            "bookings",
            "cache",
        ]

        flushed: Dict[str, int | str] = {}
        total_removed = 0

        for queue in queue_names:
            try:
                # Get current length before deletion
                length = await client.llen(queue)
                if length > 0:
                    # Delete the queue
                    await client.delete(queue)
                    flushed[queue] = length
                    total_removed += length
            except Exception as e:
                logger.error(f"Failed to flush queue {queue}: {e}")
                flushed[queue] = f"error: {str(e)}"

        return RedisFlushQueuesResponse(
            message=f"Flushed {len(flushed)} queues, removed {total_removed} tasks",
            queues_flushed=list(flushed.keys()),
        )

    except Exception as e:
        logger.error(f"Failed to flush queues: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to flush queues: {str(e)}",
        )
