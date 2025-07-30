# backend/app/core/config_production.py
"""
Production-optimized configuration for Render + Upstash deployment.

This module contains performance-tuned settings specifically for:
- Render Standard plan ($25/month) constraints
- Upstash Redis serverless architecture
- Supabase PostgreSQL connection pooling
"""

import os
from typing import Any, Dict

# Database Connection Pooling (Optimized for Render + Supabase)
DATABASE_POOL_CONFIG = {
    "pool_size": int(os.getenv("DATABASE_POOL_SIZE", "20")),  # Increased from 5 to 20
    "max_overflow": int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),  # Increased from 5 to 10
    "pool_timeout": 30,  # Increased from 10 to 30
    "pool_recycle": 1800,  # 30 minutes - more aggressive recycling
    "pool_pre_ping": True,  # Test connections before using
    "echo_pool": os.getenv("DATABASE_ECHO_POOL", "false").lower() == "true",
    "connect_args": {
        "connect_timeout": 5,  # Reduced from 10
        "application_name": "instainstru_render",
        "options": "-c statement_timeout=30000",  # 30s query timeout
    },
}

# Redis/Upstash Configuration (Optimized for serverless)
REDIS_CONFIG = {
    "max_connections": int(os.getenv("REDIS_MAX_CONNECTIONS", "10")),  # Reduced from 50
    "socket_connect_timeout": 2,  # Reduced from 5
    "socket_timeout": 2,
    "retry_on_timeout": True,
    "health_check_interval": 60,  # Increased from 30
    "decode_responses": True,
    "connection_pool_kwargs": {
        "max_connections": 10,
        "retry": 3,
        "retry_on_error": [ConnectionError, TimeoutError],
    },
}

# Upstash-specific optimizations
UPSTASH_CONFIG = {
    "enable_auto_pipelining": True,  # Batch commands automatically
    "pipeline_max_size": 50,  # Max commands per pipeline
    "pipeline_timeout_ms": 10,  # Auto-flush pipeline after 10ms
}

# Cache TTL Optimizations (Shorter for Upstash pricing)
CACHE_TTL_TIERS = {
    "hot": 180,  # 3 minutes (was 5)
    "warm": 1800,  # 30 minutes (was 1 hour)
    "cold": 43200,  # 12 hours (was 24)
    "static": 86400,  # 24 hours (was 7 days)
}

# Gunicorn Worker Configuration (Render Standard constraints)
GUNICORN_CONFIG = {
    "workers": int(os.getenv("GUNICORN_WORKERS", "2")),
    "worker_class": "uvicorn.workers.UvicornWorker",
    "worker_connections": 100,  # Reduced from default 1000
    "max_requests": 1000,  # Restart workers after 1000 requests
    "max_requests_jitter": 100,  # Add jitter to prevent thundering herd
    "timeout": 120,
    "graceful_timeout": 30,
    "keepalive": 5,
    "threads": int(os.getenv("GUNICORN_THREADS", "4")),
    "accesslog": "-",
    "errorlog": "-",
    "preload_app": True,  # Share memory between workers
    "enable_stdio_inheritance": True,
}

# Celery Worker Configuration (Memory-optimized)
CELERY_WORKER_CONFIG = {
    "concurrency": int(os.getenv("CELERY_WORKER_CONCURRENCY", "2")),
    "prefetch_multiplier": 1,  # Reduced from 4
    "max_tasks_per_child": 100,  # Reduced from 1000
    "task_compression": "gzip",
    "result_compression": "gzip",
    "result_expires": 900,  # 15 minutes (reduced from 1 hour)
    "task_time_limit": 300,  # 5 minutes
    "task_soft_time_limit": 240,  # 4 minutes
    "worker_max_memory_per_child": 200000,  # 200MB limit
}

# Performance Monitoring Thresholds
PERFORMANCE_THRESHOLDS = {
    "slow_query_threshold_ms": 100,  # Log queries over 100ms
    "slow_request_threshold_ms": 500,  # Log requests over 500ms
    "cache_miss_alert_threshold": 0.3,  # Alert if cache miss rate > 30%
    "db_connection_alert_threshold": 0.8,  # Alert if using > 80% connections
}

# Request Optimization
REQUEST_CONFIG = {
    "max_request_size": 1048576,  # 1MB max request size
    "request_timeout": 30,  # 30 second timeout
    "enable_request_id": True,
    "enable_correlation_id": True,
}

# Startup Optimization
STARTUP_CONFIG = {
    "lazy_apps": True,  # Delay app initialization
    "preload_models": False,  # Don't preload all models
    "warm_cache_on_startup": False,  # Don't warm cache on startup
    "check_migrations_on_startup": False,  # Skip in production
}


def get_production_settings() -> Dict[str, Any]:
    """
    Get all production-optimized settings.

    Returns:
        Dict containing all production configuration
    """
    return {
        "database": DATABASE_POOL_CONFIG,
        "redis": REDIS_CONFIG,
        "upstash": UPSTASH_CONFIG,
        "cache_ttl": CACHE_TTL_TIERS,
        "gunicorn": GUNICORN_CONFIG,
        "celery": CELERY_WORKER_CONFIG,
        "performance": PERFORMANCE_THRESHOLDS,
        "request": REQUEST_CONFIG,
        "startup": STARTUP_CONFIG,
    }


# Circuit breaker settings for external services
CIRCUIT_BREAKER_CONFIG = {
    "database": {
        "failure_threshold": 3,  # Reduced from 5
        "recovery_timeout": 30,  # Reduced from 60
        "expected_exception": "OperationalError",
    },
    "redis": {
        "failure_threshold": 3,
        "recovery_timeout": 20,
        "expected_exception": "RedisError",
    },
    "email": {
        "failure_threshold": 5,
        "recovery_timeout": 60,
        "expected_exception": "Exception",
    },
}

# Memory optimization settings
MEMORY_CONFIG = {
    "max_memory_percent": 80,  # Restart if using > 80% memory
    "gc_collect_interval": 100,  # Run garbage collection every 100 requests
    "clear_sqlalchemy_cache_interval": 500,  # Clear SQLAlchemy cache periodically
}
