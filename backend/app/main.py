# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy.orm import Session

from .core.config import settings
from .core.constants import (
    ALLOWED_ORIGINS,
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    BRAND_NAME,
    CORS_ORIGIN_REGEX,
    SSE_PATH_PREFIX,
)
from .database import get_db
from .middleware.beta_phase_header import BetaPhaseHeaderMiddleware
from .middleware.https_redirect import create_https_redirect_middleware
from .middleware.monitoring import MonitoringMiddleware
from .middleware.performance import PerformanceMiddleware
from .middleware.prometheus_middleware import PrometheusMiddleware

# Use the new ASGI middleware to avoid "No response returned" errors
from .middleware.rate_limiter_asgi import RateLimitMiddlewareASGI
from .middleware.timing_asgi import TimingMiddlewareASGI
from .routes import (
    account_management,
    addresses,
    alerts,
    analytics,
    auth,
    availability_windows,
    beta,
    bookings,
    codebase_metrics,
    database_monitor,
    favorites,
    instructor_bookings,
    instructors,
    messages,
    metrics,
    monitoring,
    password_reset,
    payments,
    privacy,
    prometheus,
    public,
    redis_monitor,
    reviews,
    search,
    search_history,
    services,
    stripe_webhooks,
    two_factor_auth,
    uploads,
    users_profile_picture,
)
from .schemas.main_responses import HealthLiteResponse, HealthResponse, PerformanceMetricsResponse, RootResponse
from .services.template_registry import TemplateRegistry
from .services.template_service import TemplateService

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

    # Log database selection (this will show which database is being used)
    from .core.database_config import DatabaseConfig

    db_config = DatabaseConfig()
    logger.info(f"Database safety score: {db_config.get_safety_score()['score']}%")

    logger.info(f"Allowed origins: {ALLOWED_ORIGINS}")
    logger.info("GZip compression enabled for responses > 500 bytes")
    logger.info("Rate limiting enabled for DDoS and brute force protection")

    # Log HTTPS status
    if settings.environment == "production":
        logger.info("🔐 HTTPS redirect enabled for production")
    else:
        logger.info("🔓 HTTPS redirect disabled for development")

    # Smoke-check: render templates without sending to catch syntax/encoding issues
    try:
        ts = TemplateService(None, None)
        _ = ts.render_template(
            TemplateRegistry.AUTH_PASSWORD_RESET, {"reset_url": "https://example.com", "user_name": "Test"}
        )
        _ = ts.render_template(TemplateRegistry.AUTH_PASSWORD_RESET_CONFIRMATION, {"user_name": "Test"})
        _ = ts.render_template(
            TemplateRegistry.REFERRALS_INVITE_STANDALONE,
            {"inviter_name": "Test", "referral_link": "https://example.com"},
        )
        logger.info("Template smoke-check passed")
    except Exception as e:
        logger.error(f"Template smoke-check failed: {e}")

    # Production startup optimizations
    if settings.environment == "production":
        from .core.production_startup import ProductionStartup

        await ProductionStartup.initialize()

    # Initialize message notification service
    from .routes.messages import set_notification_service
    from .services.message_notification_service import MessageNotificationService

    notification_service = MessageNotificationService()
    try:
        await notification_service.start()
        set_notification_service(notification_service)
        logger.info("Message notification service started successfully")
    except Exception as e:
        logger.error(f"Failed to start message notification service: {str(e)}")
        # Continue without real-time messaging if it fails

    yield

    # Shutdown
    logger.info(f"{BRAND_NAME} API shutting down...")

    # Stop message notification service
    try:
        await notification_service.stop()
        logger.info("Message notification service stopped")
    except Exception as e:
        logger.error(f"Error stopping message notification service: {str(e)}")

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

# Place CORS as high as possible in the stack so it can process preflight/headers early
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,  # Support Vercel preview deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep MonitoringMiddleware (pure ASGI-style) below CORS
app.add_middleware(MonitoringMiddleware)

# Performance and metrics middleware with SSE support
# These middlewares now properly detect and bypass SSE endpoints
app.add_middleware(PerformanceMiddleware)  # Performance monitoring with SSE bypass
app.add_middleware(PrometheusMiddleware)  # Prometheus metrics with SSE bypass
app.add_middleware(BetaPhaseHeaderMiddleware)  # Attach x-beta-phase header for every response

# Add GZip compression middleware with SSE exclusion
# SSE responses must NOT be compressed to work properly
from starlette.middleware.gzip import GZipMiddleware


class SSEAwareGZipMiddleware(GZipMiddleware):
    """GZip middleware that skips SSE endpoints."""

    async def __call__(self, scope, receive, send):
        # Skip compression for SSE endpoints
        if scope["type"] == "http" and scope.get("path", "").startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


app.add_middleware(SSEAwareGZipMiddleware, minimum_size=500)

# Include routers
app.include_router(auth.router)
app.include_router(two_factor_auth.router)
app.include_router(instructors.router)
app.include_router(instructor_bookings.router)
app.include_router(account_management.router)
app.include_router(services.router)
app.include_router(availability_windows.router)
app.include_router(password_reset.router)
app.include_router(bookings.router)
app.include_router(favorites.router)
app.include_router(payments.router)
app.include_router(messages.router)
app.include_router(metrics.router)
app.include_router(monitoring.router)
app.include_router(alerts.router)
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(codebase_metrics.router)
app.include_router(public.router)
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(search_history.router, prefix="/api/search-history", tags=["search-history"])
app.include_router(addresses.router)
app.include_router(redis_monitor.router)
app.include_router(database_monitor.router)
app.include_router(privacy.router, prefix="/api", tags=["privacy"])
app.include_router(stripe_webhooks.router)
app.include_router(prometheus.router)
app.include_router(uploads.router)
app.include_router(users_profile_picture.router)
app.include_router(beta.router)
app.include_router(reviews.router)

# Identity + uploads: new endpoints are included via existing payments router and addresses router


# Import for Stripe webhook response model
from app.schemas.payment_schemas import WebhookResponse


# Redirect for Stripe webhook - handles the URL currently configured in Stripe Dashboard
@app.post("/api/webhooks/stripe", response_model=WebhookResponse)
async def redirect_stripe_webhook(request: Request, db: Session = Depends(get_db)) -> WebhookResponse:
    """
    Redirect old webhook URL to new location.

    This endpoint exists for backward compatibility with webhooks configured
    at /api/webhooks/stripe instead of /api/payments/webhooks/stripe.
    It simply forwards the request to the correct handler.
    """
    from app.routes.payments import handle_stripe_webhook

    return await handle_stripe_webhook(request, db)


@app.get("/", response_model=RootResponse)
def read_root() -> RootResponse:
    """Root endpoint - API information"""
    return RootResponse(
        message=f"Welcome to the {BRAND_NAME} API!",
        version=API_VERSION,
        docs="/docs",
        environment=settings.environment,
        secure=settings.environment == "production",
    )


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint for monitoring"""
    return HealthResponse(
        status="healthy",
        service=f"{BRAND_NAME.lower()}-api",
        version=API_VERSION,
        environment=settings.environment,
    )


@app.get("/health/lite", response_model=HealthLiteResponse)
def health_check_lite() -> HealthLiteResponse:
    """Lightweight health check that doesn't hit database"""
    return HealthLiteResponse(status="ok")


@app.get("/metrics/performance", response_model=PerformanceMetricsResponse)
def get_performance_metrics() -> PerformanceMetricsResponse:
    from .middleware.monitoring import monitor

    return PerformanceMetricsResponse(metrics=monitor.get_stats())


# Keep the original FastAPI app for tools/tests that need access to routes
fastapi_app = app

# Wrap with ASGI middleware for production
app = TimingMiddlewareASGI(app)
app = RateLimitMiddlewareASGI(app)

# Export what's needed
__all__ = ["app", "fastapi_app"]
