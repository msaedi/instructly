# backend/app/routes/database_monitor.py
"""
Database monitoring endpoint for tracking PostgreSQL/Supabase health and performance.

Provides insights into connection pool usage, query performance, and database health.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.enums import PermissionName
from app.database import engine, get_db_pool_status
from app.dependencies.permissions import require_permission
from app.models.user import User
from app.schemas.database_monitor_responses import (
    DatabaseHealthResponse,
    DatabasePoolStatusResponse,
    DatabaseStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/database",
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)


@router.get("/health", response_model=DatabaseHealthResponse)
async def database_health() -> DatabaseHealthResponse:
    """
    Simple database health check endpoint.

    No authentication required - helps verify database connectivity.

    Returns:
        Database connection status
    """
    try:
        # Test basic connectivity by getting pool status
        pool_status = get_db_pool_status()

        return DatabaseHealthResponse(
            status="healthy",
            message="Database connection is working",
            pool_status=pool_status,
        )
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return DatabaseHealthResponse(
            status="unhealthy",
            message="Database connection failed",
            error=str(e),
        )


@router.get("/pool-status", response_model=DatabasePoolStatusResponse)
async def database_pool_status(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> DatabasePoolStatusResponse:
    """
    Get detailed database connection pool statistics.

    Requires ACCESS_MONITORING permission.

    Returns:
        Connection pool metrics including:
        - Active connections
        - Available connections
        - Pool configuration
        - Usage percentage
    """
    try:
        pool = engine.pool

        # Get detailed pool metrics
        pool_size = pool.size()
        checked_in = pool.checkedin()
        checked_out = pool.checkedout()
        overflow = pool.overflow()
        total = pool_size + overflow
        max_size = pool_size + pool._max_overflow

        # Calculate usage percentage
        usage_percent = (checked_out / max_size * 100) if max_size > 0 else 0

        # Determine health status
        health_status = "healthy" if usage_percent < 80 else "critical"

        return DatabasePoolStatusResponse(
            status=health_status,
            pool={
                "size": pool_size,
                "checked_in": checked_in,
                "checked_out": checked_out,
                "overflow": overflow,
                "total": total,
                "max_size": max_size,
                "usage_percent": round(usage_percent, 2),
            },
            configuration={
                "pool_size": pool._pool.maxsize if hasattr(pool._pool, "maxsize") else pool_size,
                "max_overflow": pool._max_overflow,
                "timeout": pool._timeout,
                "recycle": pool._recycle,
            },
            recommendations={
                "increase_pool_size": usage_percent > 80,
                "current_load": "high" if usage_percent > 60 else "normal" if usage_percent > 30 else "low",
            },
        )
    except Exception as e:
        logger.error(f"Failed to get database pool status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve pool statistics: {str(e)}"
        )


@router.get("/stats", response_model=DatabaseStatsResponse)
async def database_stats(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> DatabaseStatsResponse:
    """
    Get comprehensive database statistics.

    Requires ACCESS_MONITORING permission.

    Returns:
        Database metrics including pool status and performance indicators
    """
    try:
        # Get pool status
        pool_status = await database_pool_status(current_user)

        # Additional stats can be added here:
        # - Query performance metrics
        # - Table sizes
        # - Index usage
        # - Cache hit rates

        return DatabaseStatsResponse(
            status="connected",
            pool=pool_status.pool,
            configuration=pool_status.configuration,
            health={
                "status": pool_status.status,
                "usage_percent": pool_status.pool["usage_percent"],
            },
        )
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve database statistics: {str(e)}",
        )
