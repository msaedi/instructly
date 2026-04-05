from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
import logging
import os
import re
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.constants import ALLOWED_ORIGINS, CORS_ORIGIN_REGEX, SSE_PATH_PREFIX
from app.middleware.beta_phase_header import BetaPhaseHeaderMiddleware
from app.middleware.csrf_asgi import CsrfOriginMiddlewareASGI
from app.middleware.https_redirect import create_https_redirect_middleware
from app.middleware.monitoring import MonitoringMiddleware
from app.middleware.perf_counters import PerfCounterMiddleware, perf_counters_enabled
from app.middleware.performance import PerformanceMiddleware
from app.middleware.prometheus_middleware import PrometheusMiddleware
from app.monitoring.sentry import SentryContextMiddleware
from app.ratelimit.identity import resolve_identity

logger = logging.getLogger("app.main")

_BGC_ENV_LOGGED = False
_PROD_SITE_MODES = {"prod", "production", "beta", "preview"}


async def add_site_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Emit X-Site-Mode and X-Phase on every response."""

    response = await call_next(request)
    try:
        site_mode = (os.getenv("SITE_MODE", "") or "").strip().lower() or "unset"
        existing_phase = response.headers.get("x-beta-phase") or response.headers.get(
            "X-Beta-Phase"
        )
        response.headers["X-Site-Mode"] = site_mode
        response.headers["X-Phase"] = (existing_phase or "beta").strip()
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)
    return response


async def attach_identity(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    try:
        request.state.rate_identity = resolve_identity(request)
    except Exception:
        request.state.rate_identity = "ip:unknown"
    return await call_next(request)


def _compute_allowed_origins() -> list[str]:
    """Per-env explicit CORS allowlist."""

    site_mode = os.getenv("SITE_MODE", "").lower().strip()
    if site_mode == "preview":
        origins_set: set[str] = {f"https://{settings.preview_frontend_domain}"}
        extra = os.getenv("CORS_ALLOW_ORIGINS", "")
        if extra:
            for origin in extra.split(","):
                origin = origin.strip()
                if origin:
                    origins_set.add(origin)
        return list(origins_set)

    if site_mode in {"prod", "production", "beta"}:
        csv = (settings.prod_frontend_origins_csv or "").strip()
        origins_list = [origin.strip() for origin in csv.split(",") if origin.strip()]
        return origins_list or ["https://app.instainstru.com"]

    origins_set = set(ALLOWED_ORIGINS)
    extra = os.getenv("CORS_ALLOW_ORIGINS", "")
    if extra:
        for origin in extra.split(","):
            origin = origin.strip()
            if origin:
                origins_set.add(origin)
    return list(origins_set)


def _log_bgc_config_summary(allow_origins: Sequence[str]) -> None:
    """Emit a single startup log summarizing key Checkr/CORS settings."""

    global _BGC_ENV_LOGGED
    if _BGC_ENV_LOGGED:
        return

    try:
        api_key_value = ""
        secret = getattr(settings, "checkr_api_key", None)
        if secret:
            api_key_value = (
                secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
            )
        logger.info(
            "BGC config summary site_mode=%s cors_allow_origins=%s checkr_env=%s "
            "checkr_api_base=%s checkr_api_key_len=%s checkr_hosted_workflow=%s "
            "checkr_default_package=%s",
            getattr(settings, "site_mode", "local"),
            list(allow_origins),
            getattr(settings, "checkr_env", "sandbox"),
            getattr(settings, "checkr_api_base", ""),
            len(api_key_value or ""),
            getattr(settings, "checkr_hosted_workflow", None),
            getattr(settings, "checkr_package", getattr(settings, "checkr_default_package", None)),
        )
        _BGC_ENV_LOGGED = True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Unable to log BGC config summary: %s", exc)


def _resolve_origin_regex() -> str | None:
    site_mode = (os.getenv("SITE_MODE", "") or "").strip().lower()
    return None if site_mode in _PROD_SITE_MODES else CORS_ORIGIN_REGEX


class EnsureCorsOnErrorMiddleware(BaseHTTPMiddleware):
    """Backfill Access-Control headers on internal error responses."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: Sequence[str],
        origin_regex: str | None = None,
    ) -> None:
        super().__init__(app)
        self._allowed_origins = {origin.strip() for origin in allowed_origins if origin}
        self._origin_regex = re.compile(origin_regex) if origin_regex else None

    def _origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return False
        if origin in self._allowed_origins:
            return True
        return bool(self._origin_regex and self._origin_regex.match(origin))

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        origin = request.headers.get("origin")
        if (
            origin
            and "access-control-allow-origin" not in response.headers
            and self._origin_allowed(origin)
        ):
            response.headers["access-control-allow-origin"] = origin
            if "access-control-allow-credentials" not in response.headers:
                response.headers["access-control-allow-credentials"] = "true"
        return response


class SSEAwareGZipMiddleware(GZipMiddleware):
    """GZip middleware that skips SSE endpoints."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (
            path.startswith(SSE_PATH_PREFIX) or path == "/api/v1/internal/metrics"
        ):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def register_middleware(app: FastAPI) -> None:
    """Register all middleware in the exact semantic order required by the app."""

    # ORDER IS SEMANTIC. Reordering this stack can change auth, CORS, metrics,
    # SSE behavior, and request context propagation.
    app_state = cast(Any, app).state
    if settings.environment == "production":
        https_redirect = create_https_redirect_middleware(force_https=True)
        app.add_middleware(https_redirect)

    app.middleware("http")(add_site_headers)
    app.middleware("http")(attach_identity)

    allowed_origins = _compute_allowed_origins()
    if "*" in allowed_origins:
        raise RuntimeError("CORS allow_origins cannot include * when allow_credentials=True")

    origin_regex = _resolve_origin_regex()
    app_state.allowed_origins = allowed_origins
    app_state.cors_origin_regex = origin_regex
    _log_bgc_config_summary(allowed_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    logger.info("CORS allow_origins=%s allow_credentials=%s", allowed_origins, True)

    app.add_middleware(
        EnsureCorsOnErrorMiddleware,
        allowed_origins=allowed_origins,
        origin_regex=origin_regex,
    )
    app.add_middleware(MonitoringMiddleware)

    if perf_counters_enabled():
        app.add_middleware(PerfCounterMiddleware)
    if bool(getattr(app_state, "sentry_enabled", False)):
        app.add_middleware(SentryContextMiddleware)

    app.add_middleware(PerformanceMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(BetaPhaseHeaderMiddleware)
    app.add_middleware(CsrfOriginMiddlewareASGI)
    app.add_middleware(SSEAwareGZipMiddleware, minimum_size=500)


__all__ = [
    "EnsureCorsOnErrorMiddleware",
    "SSEAwareGZipMiddleware",
    "add_site_headers",
    "attach_identity",
    "register_middleware",
    "_BGC_ENV_LOGGED",
    "_compute_allowed_origins",
    "_log_bgc_config_summary",
]
