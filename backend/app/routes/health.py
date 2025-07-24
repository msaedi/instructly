# backend/app/routes/health.py
"""
Health check endpoints for the application.

These endpoints are used for monitoring application health,
database connectivity, and service availability.
"""

import logging
import os
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.cache_service import CacheService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> Dict[str, str]:
    """
    Basic health check endpoint.

    Returns:
        Simple status indicating the service is running.
    """
    # Check database connectivity
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "service": "InstaInstru API",
        "version": "1.0.0",
    }


@router.get("/health/detailed")
def detailed_health_check(db: Session = Depends(get_db)) -> Dict[str, any]:
    """
    Detailed health check with component status.

    Returns:
        Detailed status of all system components.
    """
    health_status = {
        "status": "healthy",
        "components": {},
        "environment": os.getenv("ENVIRONMENT", "unknown"),
    }

    # Database check
    try:
        result = db.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()
        health_status["components"]["database"] = {
            "status": "healthy",
            "type": "postgresql",
            "user_count": user_count,
        }
    except Exception as e:
        health_status["components"]["database"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

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

        health_status["components"]["cache"] = {
            "status": "healthy" if cache_working else "unhealthy",
            "type": cache_type,
            "redis_configured": is_redis,
            "redis_url_set": redis_url != "Not configured",
            "test_passed": cache_working,
        }
    except Exception as e:
        health_status["components"]["cache"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

    # Add cache stats if available
    try:
        stats = cache_service.get_stats()
        health_status["components"]["cache"]["stats"] = stats
    except:
        pass

    return health_status
