# backend/app/routes/v1/database_monitor.py
"""
Database monitoring endpoint for tracking PostgreSQL/Supabase health and performance (v1 API).

Provides insights into connection pool usage, query performance, and database health.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.pool import Pool

from app.core.enums import PermissionName
import app.database as database_module
from app.database import get_db_pool_status
from app.dependencies.permissions import require_permission
from app.models.user import User
from app.schemas.database_monitor_responses import (
    DatabaseHealthMetrics,
    DatabaseHealthResponse,
    DatabasePoolStatusResponse,
    DatabaseStatsResponse,
)

logger = logging.getLogger(__name__)

engine = cast(Any, database_module).engine

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    engine = cast("Engine", engine)


router = APIRouter(
    tags=["monitoring"],
    responses={404: {"description": "Not found"}},
)

T = TypeVar("T", bound=Callable[..., Any])

health_route: Callable[[T], T] = cast(
    Callable[[T], T], router.get("/health", response_model=DatabaseHealthResponse)
)


@health_route
async def database_health() -> DatabaseHealthResponse:
    """
    Simple database health check endpoint.

    No authentication required - helps verify database connectivity.

    Returns:
        Database connection status
    """
    try:
        # Test basic connectivity by getting pool status
        pool_status = cast(Dict[str, Any], get_db_pool_status())

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


pool_status_route: Callable[[T], T] = cast(
    Callable[[T], T],
    router.get("/pool-status", response_model=DatabasePoolStatusResponse),
)


@pool_status_route
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
        pool = cast(Pool, engine.pool)

        # Get detailed pool metrics
        pool_size = pool.size()
        checked_in = pool.checkedin()
        checked_out = pool.checkedout()
        overflow_in_use = pool.overflow()
        max_overflow = int(getattr(pool, "_max_overflow", 0) or 0)
        max_capacity = pool_size + max_overflow

        # Calculate usage percentage
        utilization_pct = (checked_out / max_capacity * 100) if max_capacity > 0 else 0

        # Determine health status
        health_status = "healthy" if utilization_pct < 80 else "critical"

        pool_configuration = {
            "pool_size": cast(
                int,
                getattr(getattr(pool, "_pool", None), "maxsize", pool_size),
            ),
            "max_overflow": max_overflow,
            "timeout": cast(float | None, getattr(pool, "_timeout", None)),
            "recycle": cast(float | None, getattr(pool, "_recycle", None)),
        }

        return DatabasePoolStatusResponse(
            status=health_status,
            pool={
                "size": pool_size,
                "max_overflow": max_overflow,
                "max_capacity": max_capacity,
                "checked_in": checked_in,
                "checked_out": checked_out,
                "overflow_in_use": overflow_in_use,
                "utilization_pct": round(utilization_pct, 2),
            },
            configuration=pool_configuration,
            recommendations={
                "increase_pool_size": utilization_pct > 80,
                "current_load": "high"
                if utilization_pct > 60
                else "normal"
                if utilization_pct > 30
                else "low",
            },
        )
    except Exception as e:
        logger.error(f"Failed to get database pool status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pool statistics: {str(e)}",
        )


stats_route: Callable[[T], T] = cast(
    Callable[[T], T], router.get("/stats", response_model=DatabaseStatsResponse)
)


@stats_route
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
            health=DatabaseHealthMetrics(
                status=pool_status.status,
                utilization_pct=pool_status.pool.utilization_pct,
            ),
        )
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve database statistics: {str(e)}",
        )
