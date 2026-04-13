from __future__ import annotations

import base64
import hmac
from ipaddress import ip_address, ip_network
import logging
import threading
from time import monotonic
from typing import Optional, Tuple, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.core.metrics import METRICS_AUTH_FAILURE_TOTAL
from app.monitoring.prometheus_metrics import REGISTRY as PROM_REGISTRY, prometheus_metrics

logger = logging.getLogger("app.main")

_METRICS_CACHE_TTL_SECONDS = 1.0
_metrics_cache: Optional[Tuple[float, bytes]] = None
_metrics_cache_lock = threading.Lock()


def _metrics_auth_failure(reason: str) -> None:
    try:
        METRICS_AUTH_FAILURE_TOTAL.labels(reason=reason).inc()
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)


def _extract_metrics_client_ip(request: Request) -> str:
    for header_name in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header_name)
        if value:
            candidate: str = value.split(",")[0].strip()
            if candidate:
                return candidate
    client = request.client
    if client and getattr(client, "host", None):
        return str(client.host)
    return ""


def _ip_allowed(ip_str: str, allowlist: list[str]) -> bool:
    if not ip_str:
        return False
    try:
        ip_obj = ip_address(ip_str)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if ip_obj in ip_network(entry, strict=False):
                return True
        except ValueError:
            logger.warning("Malformed metrics_ip_allowlist entry (skipping): %s", entry)
            continue
    return False


def _metrics_method_not_allowed() -> None:
    _metrics_auth_failure("method")
    raise HTTPException(
        status_code=HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
        headers={"Allow": "GET"},
    )


def _check_metrics_basic_auth(request: Request) -> None:
    from app.core.config import settings as auth_settings

    if not auth_settings.metrics_basic_auth_enabled:
        return

    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("basic "):
        _metrics_auth_failure("unauthorized")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )

    try:
        encoded = auth_header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8", "strict")
    except Exception:
        _metrics_auth_failure("unauthorized")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        ) from None

    username, _, password = decoded.partition(":")
    expected_user = (
        auth_settings.metrics_basic_auth_user.get_secret_value()
        if auth_settings.metrics_basic_auth_user
        else ""
    )
    expected_pass = (
        auth_settings.metrics_basic_auth_pass.get_secret_value()
        if auth_settings.metrics_basic_auth_pass
        else ""
    )
    if hmac.compare_digest(username, expected_user) and hmac.compare_digest(
        password,
        expected_pass,
    ):
        return

    _metrics_auth_failure("unauthorized")
    raise HTTPException(
        status_code=HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": 'Basic realm="metrics"'},
    )


def _load_metrics_payload(metrics_max_bytes: int) -> bytes | Response:
    global _metrics_cache

    now = monotonic()
    payload: bytes | None = None
    with _metrics_cache_lock:
        if _metrics_cache is not None:
            cached_at, cached_payload = _metrics_cache
            if now - cached_at <= _METRICS_CACHE_TTL_SECONDS:
                payload = cached_payload

    if payload is not None:
        return payload

    fresh = cast(bytes, generate_latest(PROM_REGISTRY))
    if len(fresh) > metrics_max_bytes:
        return Response(
            content=b"metrics payload exceeds configured limit",
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    with _metrics_cache_lock:
        _metrics_cache = (now, fresh)
    return fresh


internal_metrics_router = APIRouter(tags=["internal"])


@internal_metrics_router.get("/metrics", include_in_schema=False)
def internal_metrics_endpoint(
    request: Request,
    _: None = Depends(_check_metrics_basic_auth),
) -> Response:
    from app.core.config import settings as metrics_settings

    allowlist = metrics_settings.metrics_ip_allowlist
    if allowlist:
        client_ip = _extract_metrics_client_ip(request)
        if not _ip_allowed(client_ip, allowlist):
            _metrics_auth_failure("forbidden")
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")

    payload = _load_metrics_payload(metrics_settings.metrics_max_bytes)
    if isinstance(payload, Response):
        return payload
    return Response(
        content=payload,
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@internal_metrics_router.head("/metrics", include_in_schema=False)
def internal_metrics_head() -> None:
    _metrics_method_not_allowed()


@internal_metrics_router.post("/metrics", include_in_schema=False)
def internal_metrics_post() -> None:
    _metrics_method_not_allowed()


@internal_metrics_router.put("/metrics", include_in_schema=False)
def internal_metrics_put() -> None:
    _metrics_method_not_allowed()


@internal_metrics_router.patch("/metrics", include_in_schema=False)
def internal_metrics_patch() -> None:
    _metrics_method_not_allowed()


@internal_metrics_router.delete("/metrics", include_in_schema=False)
def internal_metrics_delete() -> None:
    _metrics_method_not_allowed()


@internal_metrics_router.options("/metrics", include_in_schema=False)
def internal_metrics_options() -> None:
    _metrics_method_not_allowed()


def prewarm_metrics_cache() -> None:
    """Warm metrics cache so the first scrape is fast."""

    prometheus_metrics.prewarm()
    try:
        from app.routes.v1.prometheus import warm_prometheus_metrics_response_cache

        warm_prometheus_metrics_response_cache()
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)


__all__ = [
    "internal_metrics_router",
    "prewarm_metrics_cache",
    "_check_metrics_basic_auth",
    "_extract_metrics_client_ip",
    "_ip_allowed",
    "_metrics_auth_failure",
    "_metrics_method_not_allowed",
]
