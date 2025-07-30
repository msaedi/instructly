# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core.config import settings
from .core.constants import ALLOWED_ORIGINS, API_DESCRIPTION, API_TITLE, API_VERSION, BRAND_NAME
from .middleware.https_redirect import create_https_redirect_middleware
from .middleware.monitoring import MonitoringMiddleware
from .middleware.performance import PerformanceMiddleware
from .middleware.prometheus_middleware import PrometheusMiddleware
from .middleware.rate_limiter import RateLimitMiddleware
from .middleware.timing import TimingMiddleware
from .routes import (
    alerts,
    analytics,
    auth,
    availability_windows,
    bookings,
    instructors,
    metrics,
    monitoring,
    password_reset,
    prometheus,
    public,
    redis_monitor,
    search,
    search_history,
    services,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    This replaces the deprecated @app.on_event decorators.
    """
    # Startup
    logger.info(f"{BRAND_NAME} API starting up...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Allowed origins: {ALLOWED_ORIGINS}")
    logger.info("GZip compression enabled for responses > 500 bytes")
    logger.info("Rate limiting enabled for DDoS and brute force protection")

    # Log HTTPS status
    if settings.environment == "production":
        logger.info("🔐 HTTPS redirect enabled for production")
    else:
        logger.info("🔓 HTTPS redirect disabled for development")

    # Production startup optimizations
    if settings.environment == "production":
        from .core.production_startup import ProductionStartup

        await ProductionStartup.initialize()

    yield

    # Shutdown
    logger.info(f"{BRAND_NAME} API shutting down...")
    # Here you can add cleanup logic like:
    # - Closing database connections
    # - Saving cache state
    # - Cleanup temporary files


app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,  # Use the new lifespan handler
)

# Add middleware in the correct order (reverse order of execution)
# HTTPS redirect should be first to handle before other processing
if settings.environment == "production":
    # Only force HTTPS in production
    HTTPSRedirectMiddleware = create_https_redirect_middleware(force_https=True)
    app.add_middleware(HTTPSRedirectMiddleware)

# Rate limiting should be early in the chain to block bad requests quickly
app.add_middleware(TimingMiddleware)
app.add_middleware(MonitoringMiddleware)
app.add_middleware(PerformanceMiddleware)  # Production performance monitoring
app.add_middleware(PrometheusMiddleware)  # Prometheus metrics collection
app.add_middleware(RateLimitMiddleware)  # Added rate limiting
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression middleware
app.add_middleware(GZipMiddleware, minimum_size=500)  # Compress responses larger than 500 bytes

# Include routers
app.include_router(auth.router)
app.include_router(instructors.router)
app.include_router(services.router)
app.include_router(availability_windows.router)
app.include_router(password_reset.router)
app.include_router(bookings.router)
app.include_router(metrics.router)
app.include_router(monitoring.router)
app.include_router(alerts.router)
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(public.router)
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(search_history.router, prefix="/api/search-history", tags=["search-history"])
app.include_router(redis_monitor.router)
app.include_router(prometheus.router)


@app.get("/")
def read_root():
    """Root endpoint - API information"""
    return {
        "message": f"Welcome to the {BRAND_NAME} API!",
        "version": API_VERSION,
        "docs": "/docs",
        "environment": settings.environment,
        "secure": settings.environment == "production",
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": f"{BRAND_NAME.lower()}-api",
        "version": API_VERSION,
        "environment": settings.environment,
    }


@app.get("/health/lite")
def health_check_lite():
    """Lightweight health check that doesn't hit database"""
    return {"status": "ok"}


@app.get("/metrics/performance")
def get_performance_metrics():
    from .middleware.monitoring import monitor

    return monitor.get_stats()
