# backend/app/main.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
from types import ModuleType
from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.orm import Session
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

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
from .middleware.csrf_asgi import CsrfOriginMiddlewareASGI
from .middleware.https_redirect import create_https_redirect_middleware
from .middleware.monitoring import MonitoringMiddleware
from .middleware.performance import PerformanceMiddleware
from .middleware.prometheus_middleware import PrometheusMiddleware

# Use the new ASGI middleware to avoid "No response returned" errors
from .middleware.rate_limiter_asgi import RateLimitMiddlewareASGI
from .middleware.timing_asgi import TimingMiddlewareASGI
from .monitoring.prometheus_metrics import REGISTRY as PROM_REGISTRY
from .ratelimit.identity import resolve_identity
from .repositories.beta_repository import BetaSettingsRepository
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
    gated,
    instructor_bookings,
    instructors,
    internal,
    messages,
    metrics,
    monitoring,
    password_reset,
    payments,
    privacy,
    prometheus,
    public,
    redis_monitor,
    referrals,
    reviews,
    search,
    search_history,
    services,
    stripe_webhooks,
    two_factor_auth,
    uploads,
    users_profile_picture,
)
from .schemas.main_responses import (
    HealthLiteResponse,
    HealthResponse,
    RootResponse,
)
from .services.template_registry import TemplateRegistry
from .services.template_service import TemplateService

if TYPE_CHECKING:
    pass

# Ensure custom rate-limit metrics are registered with our Prometheus REGISTRY
_rl_metrics: ModuleType | None
try:
    from .ratelimit import metrics as _rl_metrics  # noqa: F401
except Exception:  # pragma: no cover
    _rl_metrics = None

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for startup and shutdown events.

    This replaces the deprecated @app.on_event decorators.
    """
    # Startup
    logger.info(f"{BRAND_NAME} API starting up...")
    import os

    logger.info(
        f"Environment: {settings.environment} (SITE_MODE={os.getenv('SITE_MODE','') or 'unset'})"
    )

    # Enforce is_testing discipline without changing preview/prod behavior otherwise
    try:
        site_mode = os.getenv("SITE_MODE", "").strip().lower()
        if site_mode in {"preview", "prod", "production", "live"} and bool(
            getattr(settings, "is_testing", False)
        ):
            logger.error("Refusing to start: is_testing=true is not allowed in preview/prod")
            raise SystemExit(2)
        if site_mode == "local" and bool(getattr(settings, "is_testing", False)):
            logger.warning("Local testing mode enabled (is_testing=true)")
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Startup guard evaluation failed: {e}")

    # Log database selection (this will show which database is being used)
    from .core.database_config import DatabaseConfig

    db_config = DatabaseConfig()
    logger.info(f"Database safety score: {db_config.get_safety_score()['score']}%")

    logger.info(f"Allowed origins: {_DYN_ALLOWED_ORIGINS}")
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
            TemplateRegistry.AUTH_PASSWORD_RESET,
            {"reset_url": "https://example.com", "user_name": "Test"},
        )
        _ = ts.render_template(
            TemplateRegistry.AUTH_PASSWORD_RESET_CONFIRMATION, {"user_name": "Test"}
        )
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


def _unique_operation_id(route: APIRoute) -> str:
    methods = "_".join(sorted(m.lower() for m in route.methods or []))
    path = route.path_format.replace("/", "_").replace("{", "").replace("}", "").strip("_")
    name = (route.name or "operation").lower().replace(" ", "_")
    return f"{methods}__{path}__{name}".strip("_")


app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,  # Use the new lifespan handler
    generate_unique_id_function=_unique_operation_id,
)
# Register unified error envelope handlers
from .errors import register_error_handlers  # noqa: E402

register_error_handlers(app)


@app.middleware("http")
async def add_site_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Emit X-Site-Mode and X-Phase on every response.

    - X-Site-Mode derived from SITE_MODE env (fallback "unset").
    - X-Phase prefers existing beta header if present; otherwise "beta".
    """
    response = await call_next(request)
    try:
        site_mode = (os.getenv("SITE_MODE", "") or "").strip().lower() or "unset"
        # Prefer phase from BetaPhaseHeaderMiddleware (x-beta-phase)
        existing_phase = response.headers.get("x-beta-phase") or response.headers.get(
            "X-Beta-Phase"
        )
        phase = (existing_phase or "beta").strip()
        response.headers["X-Site-Mode"] = site_mode
        response.headers["X-Phase"] = phase
    except Exception:
        # Never fail a response due to header attachment
        pass
    return response


@app.middleware("http")
async def attach_identity(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # Attach a normalized identity for rate-limiter dependency (shadow in PR-2)
    try:
        request.state.rate_identity = resolve_identity(request)
    except Exception:
        request.state.rate_identity = "ip:unknown"
    return await call_next(request)


# Add middleware in the correct order (reverse order of execution)
# HTTPS redirect should be first to handle before other processing
if settings.environment == "production":
    # Only force HTTPS in production
    HTTPSRedirectMiddleware = create_https_redirect_middleware(force_https=True)
    app.add_middleware(HTTPSRedirectMiddleware)


def _compute_allowed_origins() -> list[str]:
    """Per-env explicit CORS allowlist."""
    site_mode = os.getenv("SITE_MODE", "").lower().strip()
    if site_mode == "preview":
        # Include preview frontend domain and optional extra CSV
        origins_set: set[str] = {f"https://{settings.preview_frontend_domain}"}
        extra = os.getenv("CORS_ALLOW_ORIGINS", "")
        if extra:
            for origin in extra.split(","):
                origin = origin.strip()
                if origin:
                    origins_set.add(origin)
        return list(origins_set)
    if site_mode in {"prod", "production", "live"}:
        csv = (settings.prod_frontend_origins_csv or "").strip()
        origins_list = [o.strip() for o in csv.split(",") if o.strip()]
        return origins_list or ["https://app.instainstru.com"]
    # local/dev: include env override or constants
    origins_set = set(ALLOWED_ORIGINS)
    extra = os.getenv("CORS_ALLOW_ORIGINS", "")
    if extra:
        for origin in extra.split(","):
            origin = origin.strip()
            if origin:
                origins_set.add(origin)
    return list(origins_set)


_DYN_ALLOWED_ORIGINS = _compute_allowed_origins()
assert (
    "*" not in _DYN_ALLOWED_ORIGINS
), "CORS allow_origins cannot include * when allow_credentials=True"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DYN_ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,  # Support Vercel preview deployments
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Keep MonitoringMiddleware (pure ASGI-style) below CORS
app.add_middleware(MonitoringMiddleware)

# Performance and metrics middleware with SSE support
# These middlewares now properly detect and bypass SSE endpoints
app.add_middleware(PerformanceMiddleware)  # Performance monitoring with SSE bypass
app.add_middleware(PrometheusMiddleware)  # Prometheus metrics with SSE bypass
app.add_middleware(BetaPhaseHeaderMiddleware)  # Attach x-beta-phase header for every response
app.add_middleware(
    CsrfOriginMiddlewareASGI
)  # CSRF Origin/Referer checks for state-changing methods

# Add GZip compression middleware with SSE exclusion
# SSE responses must NOT be compressed to work properly


class SSEAwareGZipMiddleware(GZipMiddleware):
    """GZip middleware that skips SSE endpoints."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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
app.include_router(referrals.public_router)
app.include_router(referrals.router)
app.include_router(referrals.admin_router)
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
app.include_router(gated.router)
app.include_router(internal.router)


# Identity + uploads: new endpoints are included via existing payments router and addresses router


# Import for Stripe webhook response model
from app.schemas.payment_schemas import WebhookResponse


# Redirect for Stripe webhook - handles the URL currently configured in Stripe Dashboard
@app.post("/api/webhooks/stripe", response_model=WebhookResponse)
async def redirect_stripe_webhook(
    request: Request, db: Session = Depends(get_db)
) -> WebhookResponse:
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
def health_check(response: Response, db: Session = Depends(get_db)) -> HealthResponse:
    """Health check endpoint with headers for mode/phase/commit."""
    import os as _os

    # Determine phase from settings table (fallback to 'beta')
    phase = "beta"
    try:
        s = BetaSettingsRepository(db).get_singleton()
        if getattr(s, "beta_phase", None):
            phase = str(s.beta_phase)
    except Exception:
        phase = "beta"

    # Headers
    site_mode = _os.getenv("SITE_MODE", "").lower().strip() or "unset"
    response.headers["X-Site-Mode"] = site_mode
    response.headers["X-Phase"] = phase
    response.headers["X-Commit-Sha"] = _os.getenv("COMMIT_SHA", "dev")
    # Local-only testing marker
    try:
        if site_mode == "local" and bool(getattr(settings, "is_testing", False)):
            response.headers["X-Testing"] = "1"
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        service=f"{BRAND_NAME.lower()}-api",
        version=API_VERSION,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@app.get("/api/health", response_model=HealthResponse)
def api_health(response: Response, db: Session = Depends(get_db)) -> HealthResponse:
    """Alias of /health under /api path for env-contract and monitors."""
    return health_check(response, db)


@app.get("/health/lite", response_model=HealthLiteResponse)
def health_check_lite() -> HealthLiteResponse:
    """Lightweight health check that doesn't hit database"""
    return HealthLiteResponse(status="ok")


@app.get("/metrics")
def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint (lightweight)."""
    return Response(generate_latest(PROM_REGISTRY), media_type=CONTENT_TYPE_LATEST)


# Keep the original FastAPI app for tools/tests that need access to routes
fastapi_app = app

# Wrap with ASGI middleware for production
wrapped_app: ASGIApp = TimingMiddlewareASGI(app)
wrapped_app = RateLimitMiddlewareASGI(wrapped_app)
app = wrapped_app

# Export what's needed
__all__ = ["app", "fastapi_app"]
