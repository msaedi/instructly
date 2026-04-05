# backend/app/main.py
from __future__ import annotations

from collections.abc import Callable
import logging
from types import ModuleType
from typing import Any, Dict, cast

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.types import ASGIApp

from .core.config import settings
from .core.constants import API_DESCRIPTION, API_TITLE, API_VERSION, BRAND_NAME
from .core.lifespan import app_lifespan
from .core.middleware_setup import register_middleware
from .core.request_context import attach_request_id_filter
from .core.router_registry import register_all_routers
from .middleware.rate_limiter_asgi import RateLimitMiddlewareASGI
from .middleware.timing_asgi import TimingMiddlewareASGI
from .monitoring.sentry import init_sentry
from .schemas.audit import AuditLogView
from .schemas.availability_window import (
    ValidateWeekRequest,
    WeekSpecificScheduleCreate,
)
from .schemas.main_responses import RootResponse

for _model in (WeekSpecificScheduleCreate, ValidateWeekRequest, AuditLogView):
    try:
        _model.model_rebuild(force=True)
    except Exception:  # pragma: no cover - defensive init
        logging.getLogger(__name__).debug(
            "Failed to rebuild Pydantic model: %s",
            getattr(_model, "__name__", repr(_model)),
            exc_info=True,
        )

_rl_metrics: ModuleType | None = None
try:
    from .ratelimit import metrics as _loaded_rl_metrics  # noqa: F401

    _rl_metrics = _loaded_rl_metrics
except Exception:  # pragma: no cover
    _rl_metrics = None

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] "
        "[trace=%(otelTraceID)s span=%(otelSpanID)s] %(message)s"
    ),
)
attach_request_id_filter()

logger = logging.getLogger(__name__)
_SENTRY_ENABLED = init_sentry()


def _unique_operation_id(route: APIRoute) -> str:
    methods = "_".join(sorted(m.lower() for m in route.methods or []))
    path = route.path_format.replace("/", "_").replace("{", "").replace("}", "").strip("_")
    name = (route.name or "operation").lower().replace(" ", "_")
    return f"{methods}__{path}__{name}".strip("_")


fastapi_app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=app_lifespan,
    generate_unique_id_function=_unique_operation_id,
)

from .errors import register_error_handlers

register_error_handlers(fastapi_app)

_original_openapi = cast(Callable[[], Dict[str, Any]], getattr(fastapi_app, "openapi"))


def _availability_safe_openapi() -> Dict[str, Any]:
    """Ensure availability schemas are rebuilt before generating OpenAPI."""

    for _model in (WeekSpecificScheduleCreate, ValidateWeekRequest):
        try:
            _model.model_rebuild(force=True)
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
    return _original_openapi()


setattr(fastapi_app, "openapi", _availability_safe_openapi)

cast(Any, fastapi_app).state.sentry_enabled = _SENTRY_ENABLED
register_middleware(fastapi_app)
register_all_routers(fastapi_app)


@fastapi_app.get("/", response_model=RootResponse)
def read_root() -> RootResponse:
    """Root endpoint - API information."""

    return RootResponse(
        message=f"Welcome to the {BRAND_NAME} API!",
        version=API_VERSION,
        docs="/docs",
        environment=settings.environment,
        secure=settings.environment == "production",
    )


@fastapi_app.get("/sentry-debug")
def trigger_sentry_debug() -> None:
    """Trigger a test exception to verify Sentry integration."""

    raise RuntimeError("Sentry debug endpoint")


wrapped_app: ASGIApp = TimingMiddlewareASGI(fastapi_app)
wrapped_app = RateLimitMiddlewareASGI(wrapped_app)
if _SENTRY_ENABLED:
    from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

    wrapped_app = SentryAsgiMiddleware(wrapped_app)
app: ASGIApp = wrapped_app

__all__ = ["app", "fastapi_app"]
