# backend/app/routes/v1/health.py
"""
Health check endpoints for monitoring and load balancer probes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.constants import API_VERSION, BRAND_NAME
from app.middleware.rate_limiter import RateLimitKeyType, rate_limit
from app.schemas.main_responses import HealthLiteResponse, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _apply_health_headers(response: Response) -> None:
    """Apply standard health check headers."""
    site_mode = os.getenv("SITE_MODE", "").lower().strip() or "unset"
    response.headers["X-Site-Mode"] = site_mode
    response.headers["X-Phase"] = os.getenv("BETA_PHASE", "beta")
    response.headers["X-Commit-Sha"] = _resolve_git_sha()
    try:
        if site_mode == "local" and bool(getattr(settings, "is_testing", False)):
            response.headers["X-Testing"] = "1"
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)


def _resolve_git_sha() -> str:
    candidates = [
        os.getenv("RENDER_GIT_COMMIT"),
        os.getenv("GIT_SHA"),
        os.getenv("COMMIT_SHA"),
    ]
    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return "unknown"


def _health_payload() -> HealthResponse:
    """Generate the standard health response payload."""
    return HealthResponse(
        status="healthy",
        service=f"{BRAND_NAME.lower()}-api",
        version=API_VERSION,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        git_sha=_resolve_git_sha(),
    )


@router.get("", response_model=HealthResponse)
def health_check(response: Response) -> HealthResponse:
    """
    Health check endpoint.

    Returns basic health status including service info and environment.
    Used by load balancers and monitoring systems.
    """
    _apply_health_headers(response)
    return _health_payload()


@router.get("/lite", response_model=HealthLiteResponse)
def health_check_lite() -> HealthLiteResponse:
    """
    Lightweight health check that doesn't hit database.

    Use this for high-frequency health probes.
    """
    return HealthLiteResponse(status="ok")


@router.get("/rate-limit-test", response_model=HealthLiteResponse)
@rate_limit("3/minute", key_type=RateLimitKeyType.IP)
def rate_limit_test(request: Request) -> HealthLiteResponse:
    """
    Public endpoint for CI rate limit testing.

    Has a strict 3/minute rate limit per IP.
    Used by env-contract CI workflow to verify rate limiting is active.
    """
    return HealthLiteResponse(status="ok")
