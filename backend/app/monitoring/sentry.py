# backend/app/monitoring/sentry.py
from __future__ import annotations

import logging
import os
import subprocess  # nosec B404 - subprocess used with hardcoded safe command
from typing import Any, Mapping

from fastapi import Request

try:  # pragma: no cover - optional dependency in some test environments
    import sentry_sdk as _sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration as _FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration as _LoggingIntegration
except Exception:  # pragma: no cover
    sentry_sdk: Any | None = None
    FastApiIntegration: Any | None = None
    LoggingIntegration: Any | None = None
else:
    sentry_sdk = _sentry_sdk
    FastApiIntegration = _FastApiIntegration
    LoggingIntegration = _LoggingIntegration

try:  # pragma: no cover - optional dependency in some test environments
    from sentry_sdk.integrations.celery import CeleryIntegration as _CeleryIntegration
except Exception:  # pragma: no cover
    CeleryIntegration: Any | None = None
else:
    CeleryIntegration = _CeleryIntegration

try:
    from app.monitoring.sentry_crons import CRITICAL_BEAT_MONITOR_EXCLUDES
except Exception:
    CRITICAL_BEAT_MONITOR_EXCLUDES = ()

logger = logging.getLogger(__name__)

DEFAULT_TRACES_SAMPLE_RATE = 0.1
DEFAULT_PROFILES_SAMPLE_RATE = 0.1
FAILED_REQUEST_STATUS_CODES = {403, *range(500, 600)}

_HEALTHCHECK_PATH_SUFFIXES = (
    "/health",
    "/health/lite",
    "/ready",
)


def _resolve_environment() -> str | None:
    environment = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "").strip()
    if environment:
        return environment
    sentry_env = (os.getenv("SENTRY_ENVIRONMENT") or "").strip()
    if sentry_env:
        return sentry_env
    try:
        from app.core.config import settings

        resolved = getattr(settings, "environment", None)
        return str(resolved) if resolved else None
    except Exception:
        return None


def _resolve_release() -> str | None:
    release = (os.getenv("GIT_SHA") or os.getenv("RENDER_GIT_COMMIT") or "").strip()
    if release:
        return release
    return _resolve_git_sha()


def _resolve_git_sha() -> str | None:
    try:
        output = subprocess.check_output(  # nosec B603 B607 - hardcoded git command, no user input
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return output or None
    except Exception:
        return None


def _is_healthcheck_path(path: str | None) -> bool:
    if not path:
        return False
    normalized = path.rstrip("/") or "/"
    return any(normalized.endswith(suffix) for suffix in _HEALTHCHECK_PATH_SUFFIXES)


def _extract_sampling_path(sampling_context: Mapping[str, Any]) -> str | None:
    scope = sampling_context.get("asgi_scope")
    if isinstance(scope, Mapping):
        path = scope.get("path")
        if isinstance(path, str):
            return path
    request = sampling_context.get("request")
    if request is not None:
        try:
            path_value = getattr(getattr(request, "url", None), "path", None)
            if isinstance(path_value, str):
                return path_value
        except Exception:
            return None
    return None


def _traces_sampler(sampling_context: Mapping[str, Any]) -> float:
    path = _extract_sampling_path(sampling_context)
    if _is_healthcheck_path(path):
        return 0.0
    return DEFAULT_TRACES_SAMPLE_RATE


def init_sentry() -> bool:
    if sentry_sdk is None:
        logger.debug("Sentry disabled: sentry_sdk not installed")
        return False
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        logger.debug("Sentry disabled: SENTRY_DSN not set")
        return False

    integrations: list[Any] = []
    if LoggingIntegration:
        integrations.append(LoggingIntegration(level=logging.INFO, event_level=logging.ERROR))
    if FastApiIntegration:
        integrations.append(
            FastApiIntegration(
                transaction_style="endpoint",
                failed_request_status_codes=FAILED_REQUEST_STATUS_CODES,
            )
        )
    if CeleryIntegration:
        integrations.append(
            CeleryIntegration(
                monitor_beat_tasks=True,
                exclude_beat_tasks=list(CRITICAL_BEAT_MONITOR_EXCLUDES),
            )
        )

    sentry_sdk.init(
        dsn=dsn,
        environment=_resolve_environment(),
        release=_resolve_release(),
        integrations=integrations or None,
        send_default_pii=True,
        traces_sample_rate=DEFAULT_TRACES_SAMPLE_RATE,
        traces_sampler=_traces_sampler,
        profiles_sample_rate=DEFAULT_PROFILES_SAMPLE_RATE,
        enable_logs=True,
    )
    logger.info("Sentry initialized")
    return True


def _extract_request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return str(request_id)
    header_id = request.headers.get("x-request-id")
    return str(header_id) if header_id else None


def _extract_user_context(request: Request) -> tuple[str | None, str | None]:
    user = getattr(request.state, "current_user", None) or getattr(request.state, "user", None)
    user_id = getattr(user, "id", None) if user is not None else None
    user_email = getattr(user, "email", None) if user is not None else None

    if not user_id:
        user_id = getattr(request.state, "user_id", None)
    if not user_email:
        user_email = getattr(request.state, "user_email", None)

    user_id_str = str(user_id) if user_id is not None else None
    user_email_str = str(user_email) if user_email else None
    return user_id_str, user_email_str


def _apply_scope_context(scope: Any, request: Request) -> None:
    request_id = _extract_request_id(request)
    if request_id:
        scope.set_tag("request_id", request_id)

    user_id, user_email = _extract_user_context(request)
    if user_id or user_email:
        user_payload: dict[str, str] = {}
        if user_id:
            user_payload["id"] = user_id
        if user_email:
            user_payload["email"] = user_email
        scope.set_user(user_payload)


def _apply_event_context(event: dict[str, Any], request: Request) -> dict[str, Any]:
    request_id = _extract_request_id(request)
    if request_id:
        tags = event.setdefault("tags", {})
        tags.setdefault("request_id", request_id)

    user_id, user_email = _extract_user_context(request)
    if user_id or user_email:
        user_payload = event.get("user") or {}
        if user_id:
            user_payload.setdefault("id", user_id)
        if user_email:
            user_payload.setdefault("email", user_email)
        event["user"] = user_payload

    return event


def is_sentry_configured() -> bool:
    if sentry_sdk is None:
        return False
    return sentry_sdk.Hub.current.client is not None


class SentryContextMiddleware:
    """Attach request/user context to Sentry scope for errors."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not is_sentry_configured() or sentry_sdk is None:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        def _processor(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
            return _apply_event_context(event, request)

        with sentry_sdk.configure_scope() as scope_obj:
            scope_obj.add_event_processor(_processor)
            _apply_scope_context(scope_obj, request)
            await self.app(scope, receive, send)
