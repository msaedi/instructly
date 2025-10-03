# backend/app/core/production_startup.py
"""
Production startup optimizations for Render deployment.

This module handles:
- Lazy loading of heavy dependencies
- Connection pool warming
- Cache preloading (optional)
- Health check verification
"""

import asyncio
import logging
import os

from .config import settings

logger = logging.getLogger(__name__)


class ProductionStartup:
    """Manages optimized startup for production environment."""

    @staticmethod
    async def initialize() -> None:
        """Initialize production optimizations."""
        if settings.environment != "production":
            logger.info("Skipping production optimizations (not in production)")
            return

        logger.info("🚀 Starting production optimizations...")

        # 1. Configure production logging
        ProductionStartup._configure_logging()

        # 2. Verify critical services
        await ProductionStartup._verify_services()

        # 3. Warm up connections (optional)
        if os.getenv("WARM_CONNECTIONS", "false").lower() == "true":
            await ProductionStartup._warm_connections()

        # 4. Set up monitoring
        await ProductionStartup._setup_monitoring()

        logger.info("✅ Production optimizations complete")

    @staticmethod
    def _configure_logging() -> None:
        """Configure production logging settings."""
        # Set appropriate log levels
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.INFO)

        # Reduce noise from libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

        # Enable structured logging format
        if os.getenv("STRUCTURED_LOGS", "true").lower() == "true":
            import json

            class StructuredFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    log_obj = {
                        "timestamp": self.formatTime(record),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                    }
                    if hasattr(record, "extra"):
                        log_obj.update(record.extra)
                    return json.dumps(log_obj)

            # Apply to root logger
            handler = logging.StreamHandler()
            handler.setFormatter(StructuredFormatter())
            logging.root.handlers = [handler]

    @staticmethod
    async def _verify_services() -> None:
        """Verify critical services are accessible."""
        logger.info("Verifying critical services...")

        # Check database
        try:
            from sqlalchemy import text

            from ..database import engine

            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✓ Database connection verified")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            if os.getenv("STRICT_STARTUP", "false").lower() == "true":
                raise

        # Check Redis/Upstash
        try:
            import redis

            r = redis.from_url(settings.redis_url or "redis://localhost:6379")
            r.ping()
            logger.info("✓ Redis/Upstash connection verified")
        except Exception as e:
            logger.warning(f"✗ Redis/Upstash connection failed: {e} (will use fallback)")

    @staticmethod
    async def _warm_connections() -> None:
        """Warm up connection pools."""
        logger.info("Warming up connection pools...")

        # Warm database pool
        try:
            from sqlalchemy import text

            from ..database import engine

            # Create multiple connections to fill pool
            connections = []
            pool_size = int(os.getenv("DATABASE_POOL_SIZE", "5"))

            for i in range(min(pool_size, 3)):  # Warm up to 3 connections
                conn = engine.connect()
                conn.execute(text("SELECT 1"))
                connections.append(conn)

            # Close connections to return to pool
            for conn in connections:
                conn.close()

            logger.info(f"✓ Warmed {len(connections)} database connections")
        except Exception as e:
            logger.warning(f"Failed to warm database connections: {e}")

    @staticmethod
    async def _setup_monitoring() -> None:
        """Set up production monitoring."""
        logger.info("Setting up monitoring...")

        if getattr(settings, "is_testing", False) or not getattr(
            settings, "scheduler_enabled", True
        ):
            logger.info("Skipping background monitoring task (scheduler disabled/testing mode)")
            return

        # Start periodic health check task
        from ..monitoring.production_monitor import periodic_health_check

        # Create background task for monitoring
        asyncio.create_task(periodic_health_check())
        logger.info("✓ Background monitoring task started")

        # Log initial metrics
        from ..monitoring.production_monitor import monitor

        summary = monitor.get_performance_summary()
        logger.info(f"Initial system state: {summary['memory']['rss_mb']}MB RSS")


# Lazy imports for heavy dependencies
_heavy_imports_loaded = False


def lazy_import_heavy_dependencies() -> None:
    """Lazy load heavy dependencies to improve startup time."""
    global _heavy_imports_loaded

    if _heavy_imports_loaded:
        return

    logger.info("Loading heavy dependencies...")

    # Import heavy libraries only when needed
    try:
        # ML/AI libraries (if used)
        if os.getenv("ENABLE_ML_FEATURES", "false").lower() == "true":
            import numpy  # noqa
            import pandas  # noqa

            logger.info("✓ ML dependencies loaded")
    except ImportError:
        pass

    _heavy_imports_loaded = True


# Circuit breaker for external services
class ServiceCircuitBreaker:
    """Simple circuit breaker for external service calls."""

    def __init__(self, service_name: str, failure_threshold: int = 3) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.failure_count = 0
        self.is_open = False

    def record_success(self) -> None:
        """Record successful call."""
        self.failure_count = 0
        if self.is_open:
            logger.info(f"Circuit breaker for {self.service_name} closed")
            self.is_open = False

    def record_failure(self) -> None:
        """Record failed call."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold and not self.is_open:
            logger.warning(f"Circuit breaker for {self.service_name} opened")
            self.is_open = True

    def can_proceed(self) -> bool:
        """Check if request can proceed."""
        return not self.is_open


# Global circuit breakers
circuit_breakers = {
    "email": ServiceCircuitBreaker("email", 5),
    "sms": ServiceCircuitBreaker("sms", 3),
    "payment": ServiceCircuitBreaker("payment", 3),
}
