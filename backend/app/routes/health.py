# backend/app/routes/health.py
"""
Health check endpoints for the application.

These endpoints are used for monitoring application health,
database connectivity, and service availability.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.base_responses import HealthCheckResponse
from ..schemas.monitoring_responses import ComponentHealth, DetailedHealthCheckResponse
from ..services.cache_service import CacheService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class LiveHealthResponse(BaseModel):
    ok: bool


@router.get("/live", response_model=LiveHealthResponse)
def live_probe(response: Response) -> LiveHealthResponse:
    """Liveness probe that avoids touching external dependencies."""

    response.headers["Cache-Control"] = "no-store"
    response.headers["CDN-Cache-Control"] = "no-store"
    return LiveHealthResponse(ok=True)


@router.get("/health", response_model=HealthCheckResponse)
def health_check(db: Session = Depends(get_db)) -> HealthCheckResponse:
    """
    Basic health check endpoint.

    Returns:
        Simple status indicating the service is running.
    """
    # Check database connectivity
    try:
        db.execute(text("SELECT 1"))
        db_status = True
        status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = False
        status = "degraded"

    return HealthCheckResponse(
        status=status,
        service="InstaInstru API",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
        checks={"database": db_status},
    )


@router.get("/health/detailed", response_model=DetailedHealthCheckResponse)
def detailed_health_check(db: Session = Depends(get_db)) -> DetailedHealthCheckResponse:
    """
    Detailed health check with component status.

    Returns:
        Detailed status of all system components.
    """
    components: Dict[str, ComponentHealth] = {}
    overall_status = "healthy"
    cache_stats: Optional[Dict[str, Any]] = None

    # Database check
    try:
        result = db.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()
        components["database"] = ComponentHealth(
            status="healthy",
            type="postgresql",
            details={"user_count": user_count},
        )
    except Exception as e:
        components["database"] = ComponentHealth(
            status="unhealthy",
            type="postgresql",
            details={"error": str(e)},
        )
        overall_status = "degraded"

    # Cache check
    try:
        cache_service = CacheService(db)
        cache_type = type(cache_service.cache).__name__

        # Test cache operations
        test_key = "health:check:test"
        test_value = {"timestamp": "now", "test": True}
        cache_service.set(test_key, test_value, ttl=10)
        retrieved = cache_service.get(test_key)
        cache_working = retrieved == test_value

        # Check if Redis URL is configured
        redis_url = os.getenv("REDIS_URL", "Not configured")
        is_redis = "redis" in redis_url.lower()

        components["cache"] = ComponentHealth(
            status="healthy" if cache_working else "unhealthy",
            type=cache_type,
            details={
                "redis_configured": is_redis,
                "redis_url_set": redis_url != "Not configured",
                "test_passed": cache_working,
            },
        )

        # Get cache stats if available
        try:
            cache_stats = cache_service.get_stats()
        except Exception:
            pass

    except Exception as e:
        components["cache"] = ComponentHealth(
            status="unhealthy",
            type="unknown",
            details={"error": str(e)},
        )
        overall_status = "degraded"

    return DetailedHealthCheckResponse(
        status=overall_status,
        environment=os.getenv("ENVIRONMENT", "unknown"),
        components=components,
        cache_stats=cache_stats,
    )
