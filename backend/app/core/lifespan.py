from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
import logging
import os
import threading
from typing import Any, AsyncGenerator, cast

from fastapi import FastAPI

from app.core.broadcast import connect_broadcast, disconnect_broadcast
from app.core.config import assert_env, secret_or_plain, settings
from app.core.constants import BRAND_NAME
from app.core.internal_metrics import prewarm_metrics_cache
from app.core.redis import close_async_redis_client
from app.database.sessions import SessionLocal, init_session_factories
from app.monitoring.otel import (
    init_otel,
    instrument_additional_libraries,
    instrument_fastapi,
    shutdown_otel,
)
from app.services.template_registry import TemplateRegistry
from app.services.template_service import TemplateService
from app.workers.background_jobs import (
    _ensure_expiry_job_scheduled,
    background_jobs_worker_sync,
)

logger = logging.getLogger("app.main")

try:  # pragma: no cover - optional dependency for warmup
    import httpx
except Exception:  # pragma: no cover
    httpx = None


def _validate_startup_config() -> None:
    """Validate encryption configuration for production startups."""

    from app.core.config import settings as runtime_settings

    mode = (getattr(runtime_settings, "site_mode", "") or "").strip().lower()
    if mode == "prod":
        from app.core.crypto import validate_bgc_encryption_key

        validate_bgc_encryption_key(getattr(runtime_settings, "bgc_encryption_key", None))
        logger.info("Background-check report encryption enabled for production")
    elif secret_or_plain(getattr(runtime_settings, "bgc_encryption_key", None)).strip():
        logger.info("Background-check report encryption enabled")

    if not getattr(runtime_settings, "hundredms_enabled", False):
        return

    access_key = (getattr(runtime_settings, "hundredms_access_key", None) or "").strip()
    app_secret = secret_or_plain(getattr(runtime_settings, "hundredms_app_secret", None)).strip()
    template_id = (getattr(runtime_settings, "hundredms_template_id", None) or "").strip()
    webhook_secret = secret_or_plain(
        getattr(runtime_settings, "hundredms_webhook_secret", None)
    ).strip()

    missing: list[str] = []
    if not access_key:
        missing.append("HUNDREDMS_ACCESS_KEY")
    if not app_secret:
        missing.append("HUNDREDMS_APP_SECRET")
    if not template_id:
        missing.append("HUNDREDMS_TEMPLATE_ID")
    if not webhook_secret:
        missing.append("HUNDREDMS_WEBHOOK_SECRET")
    if missing:
        raise ValueError(
            "HUNDREDMS_ENABLED=True but required configuration is missing: " + ", ".join(missing)
        )


def _log_startup_banner(app: FastAPI) -> None:
    app_state = cast(Any, app).state
    logger.info("%s API starting up...", BRAND_NAME)
    logger.info(
        "Environment: %s (SITE_MODE=%s)",
        settings.environment,
        os.getenv("SITE_MODE", "") or "unset",
    )
    logger.info("Allowed origins: %s", getattr(app_state, "allowed_origins", []))
    logger.info("GZip compression enabled for responses > 500 bytes")
    logger.info("Rate limiting enabled for DDoS and brute force protection")
    if settings.environment == "production":
        logger.info("🔐 HTTPS redirect enabled for production")
        return
    logger.info("🔓 HTTPS redirect disabled for development")


def _initialize_database() -> None:
    init_session_factories()
    logger.info("Database session factories initialized")


def _initialize_observability(app: FastAPI) -> None:
    try:
        if init_otel():
            instrument_fastapi(app)
            instrument_additional_libraries()
    except Exception as exc:
        logger.error("OpenTelemetry initialization failed: %s", exc, exc_info=True)


def _set_cache_event_loop() -> None:
    try:
        from app.services.cache_service import set_cache_event_loop

        set_cache_event_loop(asyncio.get_running_loop())
    except Exception as exc:
        logger.warning("Failed to set cache event loop: %s", exc)


def _assert_runtime_environment() -> None:
    site_mode_raw = os.getenv("SITE_MODE", "")
    assert_env(
        site_mode_raw,
        settings.checkr_env,
        fake=settings.checkr_fake,
        allow_override=settings.allow_sandbox_checkr_in_prod,
    )
    _validate_startup_config()


def _log_pytest_mode() -> None:
    try:
        from app.core.config import is_running_tests

        if is_running_tests():
            logger.info("Running under pytest (test mode active)")
    except Exception as exc:
        logger.debug("Test detection check failed: %s", exc)


async def _prewarm_health_endpoint(app: FastAPI) -> None:
    if httpx is None:
        return

    with contextlib.suppress(Exception):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/api/v1/health")


def _log_database_safety_score() -> None:
    from app.core.database_config import DatabaseConfig

    db_config = DatabaseConfig()
    logger.info(
        "Database safety score: %s%%",
        cast(Any, db_config).get_safety_score()["score"],
    )


def _warm_beta_settings_cache() -> None:
    from app.middleware.beta_phase_header import refresh_beta_settings_cache

    db = SessionLocal()
    try:
        refresh_beta_settings_cache(db)
    finally:
        db.close()


def _smoke_check_templates() -> None:
    try:
        template_service = TemplateService(None, None)
        template_service.render_template(
            TemplateRegistry.AUTH_PW_RESET,
            {"reset_url": "https://example.com", "user_name": "Test"},
        )
        template_service.render_template(
            TemplateRegistry.AUTH_PW_RESET_CONFIRMATION,
            {"user_name": "Test"},
        )
        template_service.render_template(
            TemplateRegistry.REFERRALS_INVITE_STANDALONE,
            {"inviter_name": "Test", "referral_link": "https://example.com"},
        )
        logger.info("Template smoke-check passed")
    except Exception as exc:
        logger.error("Template smoke-check failed: %s", exc)


async def _initialize_production_startup() -> None:
    if settings.environment != "production":
        return

    from app.core.production_startup import ProductionStartup

    await ProductionStartup.initialize()


def _initialize_search_cache() -> None:
    try:
        from app.services.cache_service import CacheService
        from app.services.search.cache_invalidation import init_search_cache

        init_search_cache(CacheService())
    except Exception as exc:
        logger.warning("Failed to initialize search cache: %s", exc)


async def _connect_sse_broadcast() -> None:
    try:
        await connect_broadcast()
        logger.info("[BROADCAST] SSE multiplexer initialized")
    except Exception as exc:
        logger.error("[BROADCAST] Failed to initialize broadcaster: %s", exc)


def _start_background_job_worker() -> tuple[asyncio.Task[None] | None, threading.Event | None]:
    if getattr(settings, "bgc_expiry_enabled", False):
        _ensure_expiry_job_scheduled()

    if not getattr(settings, "scheduler_enabled", True) or getattr(settings, "is_testing", False):
        return None, None

    stop_event = threading.Event()
    task = asyncio.create_task(asyncio.to_thread(background_jobs_worker_sync, stop_event))
    return task, stop_event


async def _shutdown_background_job_worker(
    task: asyncio.Task[None] | None,
    stop_event: threading.Event | None,
) -> None:
    if task is None:
        return
    if stop_event is not None:
        stop_event.set()
    with contextlib.suppress(BaseException):
        await task


async def _disconnect_sse_broadcast() -> None:
    try:
        await disconnect_broadcast()
        logger.info("[BROADCAST] SSE multiplexer disconnected")
    except Exception as exc:
        logger.error("[BROADCAST] Error disconnecting broadcaster: %s", exc)


async def _close_redis_clients() -> None:
    try:
        await close_async_redis_client()
        logger.info("[REDIS-PUBSUB] Async Redis client closed")
    except Exception as exc:
        logger.error("[REDIS-PUBSUB] Error closing async Redis client: %s", exc)

    try:
        from app.core.cache_redis import close_async_cache_redis_client

        await close_async_cache_redis_client()
        logger.info("[REDIS-CACHE] Async Redis client closed")
    except Exception as exc:
        logger.error("[REDIS-CACHE] Error closing async Redis client: %s", exc)

    try:
        from app.ratelimit.redis_backend import close_async_rate_limit_redis_client

        await close_async_rate_limit_redis_client()
        logger.info("[REDIS-RATELIMIT] Async Redis client closed")
    except Exception as exc:
        logger.error("[REDIS-RATELIMIT] Error closing async Redis client: %s", exc)


def _clear_cache_event_loop_reference() -> None:
    try:
        from app.services.cache_service import clear_cache_event_loop

        clear_cache_event_loop()
    except Exception as exc:
        logger.debug("Failed to clear cache event loop: %s", exc)


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup/shutdown without deprecated events."""

    _log_startup_banner(app)
    _initialize_database()
    _initialize_observability(app)
    _set_cache_event_loop()
    _assert_runtime_environment()
    _log_pytest_mode()
    await _prewarm_health_endpoint(app)
    _log_database_safety_score()
    _warm_beta_settings_cache()
    _smoke_check_templates()
    await _initialize_production_startup()
    _initialize_search_cache()
    await _connect_sse_broadcast()
    job_worker_task, job_worker_stop_event = _start_background_job_worker()
    prewarm_metrics_cache()

    yield

    logger.info("%s API shutting down...", BRAND_NAME)
    shutdown_otel()
    await _shutdown_background_job_worker(job_worker_task, job_worker_stop_event)
    await _disconnect_sse_broadcast()
    await _close_redis_clients()
    _clear_cache_event_loop_reference()


__all__ = ["app_lifespan", "_validate_startup_config"]
