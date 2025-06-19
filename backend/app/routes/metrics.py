# backend/app/routes/metrics.py 
"""
Simple metrics endpoint for performance monitoring.

This gives us immediate visibility without Prometheus complexity.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
import psutil
from sqlalchemy import text
import os

from ..database import get_db, get_db_pool_status
from ..api.dependencies.auth import get_current_user
from ..models.user import User
from ..api.dependencies.services import (
    get_availability_service,
    get_booking_service,
    get_conflict_checker,
    get_cache_service_dep
)
from ..services.cache_service import CacheService

router = APIRouter(prefix="/metrics", tags=["monitoring"])

@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "InstaInstru API"}

@router.get("/performance")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
    availability_service = Depends(get_availability_service),
    booking_service = Depends(get_booking_service),
    conflict_checker = Depends(get_conflict_checker),
    cache_service: CacheService = Depends(get_cache_service_dep),
    db: Session = Depends(get_db)
):
    """Get performance metrics from all services."""
    
    # Only allow admin users or specific monitoring user
    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
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
        "disk_usage": psutil.disk_usage('/').percent,
    }
    
    # Database metrics
    db_stats = db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
    metrics["database"] = {
        "active_connections": db_stats,
        "pool_status": get_db_pool_status()
    }
    
    return metrics

@router.get("/cache")
async def get_cache_metrics(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep)
):
    """Get detailed cache metrics."""
    
    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}
    
    if not cache_service:
        return {"error": "Cache service not available"}
    
    return cache_service.get_stats()

@router.get("/slow-queries")
async def get_slow_queries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent slow queries."""
    
    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}
    
    # Get slow queries from PostgreSQL
    try:
        result = db.execute(text("""
            SELECT 
                query,
                mean_exec_time,
                calls,
                total_exec_time
            FROM pg_stat_statements
            WHERE mean_exec_time > 100
            ORDER BY mean_exec_time DESC
            LIMIT 20
        """))
        
        slow_queries = []
        for row in result:
            slow_queries.append({
                "query": row[0][:200],  # First 200 chars
                "avg_time_ms": row[1],
                "calls": row[2],
                "total_time_ms": row[3]
            })
        
        return {"slow_queries": slow_queries}
    except Exception as e:
        return {"error": f"pg_stat_statements not available: {str(e)}"}

@router.post("/cache/reset-stats")
async def reset_cache_stats(
    current_user: User = Depends(get_current_user),
    cache_service: CacheService = Depends(get_cache_service_dep)
):
    """Reset cache statistics."""
    
    if current_user.email not in ["admin@instainstru.com", "profiling@instainstru.com"]:
        return {"error": "Unauthorized"}
    
    if cache_service:
        cache_service.reset_stats()
        return {"status": "Cache stats reset"}
    
    return {"error": "Cache service not available"}