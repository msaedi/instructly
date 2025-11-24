# backend/app/main.py
from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hmac
from ipaddress import ip_address, ip_network
import logging
import os
import re
import threading
from time import monotonic
from types import ModuleType
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, Optional, Sequence, Tuple, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_405_METHOD_NOT_ALLOWED,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from app.middleware.perf_counters import PerfCounterMiddleware, perf_counters_enabled

from .api.dependencies.authz import public_guard
from .core.config import assert_env, settings
from .core.constants import (
    ALLOWED_ORIGINS,
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    BRAND_NAME,
    CORS_ORIGIN_REGEX,
    SSE_PATH_PREFIX,
)
from .core.exceptions import RepositoryException
from .core.metrics import (
    BACKGROUND_JOB_FAILURES_TOTAL,
    BACKGROUND_JOBS_FAILED,
    BGC_PENDING_7D,
    METRICS_AUTH_FAILURE_TOTAL,
)
from .database import SessionLocal, get_db
from .middleware.beta_phase_header import BetaPhaseHeaderMiddleware
from .middleware.csrf_asgi import CsrfOriginMiddlewareASGI
from .middleware.https_redirect import create_https_redirect_middleware
from .middleware.monitoring import MonitoringMiddleware
from .middleware.performance import PerformanceMiddleware
from .middleware.prometheus_middleware import PrometheusMiddleware
from .schemas.audit import AuditLogView
from .schemas.availability_window import (
    ValidateWeekRequest,
    WeekSpecificScheduleCreate,
)

#
# Ensure Pydantic forward references for availability schemas are resolved before router setup
for _model in (WeekSpecificScheduleCreate, ValidateWeekRequest, AuditLogView):
    try:
        _model.model_rebuild(force=True)
    except Exception:  # pragma: no cover - defensive init
        pass

# Use the new ASGI middleware to avoid "No response returned" errors
from .middleware.rate_limiter_asgi import RateLimitMiddlewareASGI
from .middleware.timing_asgi import TimingMiddlewareASGI
from .monitoring.prometheus_metrics import REGISTRY as PROM_REGISTRY, prometheus_metrics
from .ratelimit.identity import resolve_identity
from .repositories.background_job_repository import BackgroundJobRepository
from .repositories.instructor_profile_repository import InstructorProfileRepository
from .routes import (
    account_management,
    addresses,
    admin_audit,
    admin_background_checks,
    admin_badges,
    admin_config,
    admin_instructors,
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
    instructor_background_checks,
    instructor_bookings,
    internal,
    messages,
    metrics,
    monitoring,
    password_reset,
    payments,
    pricing_config_public,
    pricing_preview,
    privacy,
    prometheus,
    public,
    ready,
    redis_monitor,
    referrals,
    reviews,
    search,
    search_history,
    services,
    stripe_webhooks,
    student_badges,
    two_factor_auth,
    uploads,
    users_profile_picture,
    webhooks_checkr,
)
from .routes.v1 import (
    bookings as bookings_v1,
    instructor_bookings as instructor_bookings_v1,
    instructors as instructors_v1,
)
from .schemas.main_responses import HealthLiteResponse, HealthResponse, RootResponse
from .services.background_check_workflow_service import (
    FINAL_ADVERSE_JOB_TYPE,
    BackgroundCheckWorkflowService,
    FinalAdversePayload,
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


try:  # pragma: no cover - optional dependency for warmup
    import httpx
except Exception:  # pragma: no cover
    httpx = None


_METRICS_CACHE_TTL_SECONDS = 1.0
_metrics_cache: Optional[Tuple[float, bytes]] = None
_metrics_cache_lock = threading.Lock()

metrics_router = APIRouter()


def _metrics_auth_failure(reason: str) -> None:
    try:
        METRICS_AUTH_FAILURE_TOTAL.labels(reason=reason).inc()
    except Exception:
        pass


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
            network = ip_network(entry, strict=False)
            if ip_obj in network:
                return True
        except ValueError:
            if ip_str == entry:
                return True
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
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8", "strict")
    except Exception:
        _metrics_auth_failure("unauthorized")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )

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

    if not (
        hmac.compare_digest(username, expected_user)
        and hmac.compare_digest(password, expected_pass)
    ):
        _metrics_auth_failure("unauthorized")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )


def _validate_startup_config() -> None:
    """Validate encryption configuration for production startups."""

    from app.core.config import settings as runtime_settings

    mode = (getattr(runtime_settings, "site_mode", "") or "").strip().lower()

    if mode == "prod":
        from app.core.crypto import validate_bgc_encryption_key

        validate_bgc_encryption_key(getattr(runtime_settings, "bgc_encryption_key", None))
        logger.info("Background-check report encryption enabled for production")
    elif getattr(runtime_settings, "bgc_encryption_key", None):
        logger.info("Background-check report encryption enabled")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup/shutdown without deprecated events."""
    # Startup
    logger.info(f"{BRAND_NAME} API starting up...")
    import os

    logger.info(
        f"Environment: {settings.environment} (SITE_MODE={os.getenv('SITE_MODE','') or 'unset'})"
    )

    site_mode_raw = os.getenv("SITE_MODE", "")
    assert_env(
        site_mode_raw,
        settings.checkr_env,
        fake=settings.checkr_fake,
        allow_override=settings.allow_sandbox_checkr_in_prod,
    )

    _validate_startup_config()

    # Enforce is_testing discipline without changing preview/prod behavior otherwise
    try:
        site_mode = site_mode_raw.strip().lower()
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

    # Pre-warm lightweight health endpoint to avoid first request cold start spikes
    if httpx is not None:
        with contextlib.suppress(Exception):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

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

    if getattr(settings, "bgc_expiry_enabled", False):
        _ensure_expiry_job_scheduled()

    job_worker_task: asyncio.Task[None] | None = None
    if getattr(settings, "scheduler_enabled", True) and not getattr(settings, "is_testing", False):
        job_worker_task = asyncio.create_task(_background_jobs_worker())

    _prewarm_metrics_cache()

    yield

    # Shutdown
    logger.info(f"{BRAND_NAME} API shutting down...")

    if job_worker_task is not None:
        job_worker_task.cancel()
        with contextlib.suppress(Exception):
            await job_worker_task

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
    lifespan=app_lifespan,  # Use the new lifespan handler
    generate_unique_id_function=_unique_operation_id,
)
# Register unified error envelope handlers
from .errors import register_error_handlers  # noqa: E402

register_error_handlers(app)

_original_openapi = cast(Callable[[], Dict[str, Any]], getattr(app, "openapi"))


def _availability_safe_openapi() -> Dict[str, Any]:
    """Ensure availability schemas are rebuilt before generating OpenAPI."""
    for _model in (WeekSpecificScheduleCreate, ValidateWeekRequest):
        try:
            _model.model_rebuild(force=True)
        except Exception:
            pass
    return _original_openapi()


setattr(app, "openapi", _availability_safe_openapi)


def _next_expiry_run(now: datetime | None = None) -> datetime:
    reference = now or datetime.now(timezone.utc)
    next_run = reference.replace(hour=3, minute=0, second=0, microsecond=0)
    if next_run <= reference:
        next_run += timedelta(days=1)
    return next_run


def _expiry_recheck_url() -> str:
    base_url = (settings.frontend_url or "").rstrip("/")
    return f"{base_url}/instructor/onboarding/verification"


async def _background_jobs_worker() -> None:
    """Process persisted background jobs with retry support."""

    poll_interval = max(1, int(getattr(settings, "jobs_poll_interval", 2)))
    batch_size = max(1, int(getattr(settings, "jobs_batch", 25)))

    while True:
        try:
            await asyncio.sleep(poll_interval)

            db = SessionLocal()
            try:
                job_repo = BackgroundJobRepository(db)
                repo = InstructorProfileRepository(db)
                workflow = BackgroundCheckWorkflowService(repo)

                jobs = job_repo.fetch_due(limit=batch_size)
                if not jobs:
                    db.commit()
                    continue

                for job in jobs:
                    try:
                        job_repo.mark_running(job.id)
                        db.flush()

                        payload = job.payload or {}

                        if job.type == "webhook.report_completed":
                            report_id = payload.get("report_id")
                            if not report_id:
                                raise RepositoryException("Missing report_id in job payload")

                            completed_raw = payload.get("completed_at")
                            if completed_raw:
                                completed_at = datetime.fromisoformat(completed_raw)
                                if completed_at.tzinfo is None:
                                    completed_at = completed_at.replace(tzinfo=timezone.utc)
                            else:
                                completed_at = datetime.now(timezone.utc)

                            result = payload.get("result", "unknown")
                            package = payload.get("package")
                            env = payload.get("env", settings.checkr_env)
                            assessment = payload.get("assessment")
                            candidate_id = payload.get("candidate_id")
                            invitation_id = payload.get("invitation_id")
                            includes_canceled = payload.get("includes_canceled")

                            status_value, profile, follow_up = workflow.handle_report_completed(
                                report_id=report_id,
                                result=result,
                                assessment=assessment,
                                package=package,
                                env=env,
                                completed_at=completed_at,
                                candidate_id=candidate_id,
                                invitation_id=invitation_id,
                                includes_canceled=includes_canceled,
                            )
                        elif job.type == "webhook.report_suspended":
                            report_id = payload.get("report_id")
                            if not report_id:
                                raise RepositoryException("Missing report_id in suspended payload")
                            workflow.handle_report_suspended(report_id)
                        elif job.type == "webhook.report_canceled":
                            report_id = payload.get("report_id")
                            if not report_id:
                                raise RepositoryException("Missing report_id in canceled payload")
                            canceled_raw = payload.get("canceled_at")
                            if canceled_raw:
                                canceled_at = datetime.fromisoformat(canceled_raw)
                                if canceled_at.tzinfo is None:
                                    canceled_at = canceled_at.replace(tzinfo=timezone.utc)
                                else:
                                    canceled_at = canceled_at.astimezone(timezone.utc)
                            else:
                                canceled_at = datetime.now(timezone.utc)
                            env = payload.get("env", settings.checkr_env)
                            candidate_id = payload.get("candidate_id")
                            invitation_id = payload.get("invitation_id")
                            workflow.handle_report_canceled(
                                report_id=report_id,
                                env=env,
                                canceled_at=canceled_at,
                                candidate_id=candidate_id,
                                invitation_id=invitation_id,
                            )
                        elif job.type == "webhook.report_eta":
                            report_id = payload.get("report_id")
                            if not report_id:
                                raise RepositoryException("Missing report_id in ETA payload")
                            eta_raw = payload.get("eta")
                            if eta_raw:
                                eta_dt = datetime.fromisoformat(eta_raw)
                                if eta_dt.tzinfo is None:
                                    eta_dt = eta_dt.replace(tzinfo=timezone.utc)
                                else:
                                    eta_dt = eta_dt.astimezone(timezone.utc)
                            else:
                                eta_dt = None
                            env = payload.get("env", settings.checkr_env)
                            candidate_id = payload.get("candidate_id")
                            workflow.handle_report_eta_updated(
                                report_id=report_id,
                                env=env,
                                eta=eta_dt,
                                candidate_id=candidate_id,
                            )
                        elif job.type == FINAL_ADVERSE_JOB_TYPE:
                            payload_raw = job.payload
                            if not isinstance(payload_raw, dict):
                                raise RepositoryException("Invalid payload for final adverse job")
                            final_payload = cast(FinalAdversePayload, payload_raw)
                            profile_id = final_payload["profile_id"]
                            notice_id = final_payload["pre_adverse_notice_id"]
                            scheduled_at = job.available_at or datetime.now(timezone.utc)
                            workflow.execute_final_adverse_action(
                                profile_id, notice_id, scheduled_at
                            )
                        elif job.type == "bgc.expiry_sweep":
                            if not getattr(settings, "bgc_expiry_enabled", False):
                                logger.info(
                                    "Skipping bgc.expiry_sweep job because expiry is disabled"
                                )
                            else:
                                days = int(payload.get("days", 30))

                                pending_over_7d = repo.count_pending_older_than(7)
                                BGC_PENDING_7D.set(pending_over_7d)

                                now_utc = datetime.now(timezone.utc)
                                recheck_url = _expiry_recheck_url()

                                expiring = repo.list_expiring_within(days)
                                for expiring_profile in expiring:
                                    expiry_dt = getattr(expiring_profile, "bgc_valid_until", None)
                                    expiry_dt_utc = (
                                        expiry_dt.astimezone(timezone.utc)
                                        if expiry_dt and expiry_dt.tzinfo
                                        else (
                                            expiry_dt.replace(tzinfo=timezone.utc)
                                            if expiry_dt
                                            else None
                                        )
                                    )
                                    context: dict[str, object] = {
                                        "candidate_name": workflow.candidate_name(expiring_profile)
                                        or "",
                                        "expiry_date": workflow.format_date(
                                            expiry_dt_utc or now_utc
                                        ),
                                        "is_past_due": False,
                                        "recheck_url": recheck_url,
                                        "support_email": settings.bgc_support_email,
                                    }
                                    workflow.send_expiry_recheck_email(expiring_profile, context)

                                expired_profiles = repo.list_expired()
                                for expired_profile in expired_profiles:
                                    repo.set_live(expired_profile.id, False)
                                    expiry_dt = getattr(expired_profile, "bgc_valid_until", None)
                                    expiry_dt_utc = (
                                        expiry_dt.astimezone(timezone.utc)
                                        if expiry_dt and expiry_dt.tzinfo
                                        else (
                                            expiry_dt.replace(tzinfo=timezone.utc)
                                            if expiry_dt
                                            else None
                                        )
                                    )
                                    context = {
                                        "candidate_name": workflow.candidate_name(expired_profile)
                                        or "",
                                        "expiry_date": workflow.format_date(
                                            expiry_dt_utc or now_utc
                                        ),
                                        "is_past_due": True,
                                        "recheck_url": recheck_url,
                                        "support_email": settings.bgc_support_email,
                                    }
                                    workflow.send_expiry_recheck_email(expired_profile, context)

                                next_available = _next_expiry_run()
                                job_repo.enqueue(
                                    type="bgc.expiry_sweep",
                                    payload={"days": days},
                                    available_at=next_available,
                                )
                        else:
                            logger.warning(
                                "Unknown background job type encountered",
                                extra={"job_id": job.id, "type": job.type},
                            )

                        job_repo.mark_succeeded(job.id)
                        db.commit()
                        BACKGROUND_JOBS_FAILED.set(job_repo.count_failed_jobs())
                    except asyncio.CancelledError:
                        db.rollback()
                        raise
                    except Exception as exc:  # pragma: no cover - safety logging
                        db.rollback()
                        job_type = job.type or "unknown"
                        attempts = getattr(job, "attempts", 0)
                        logger.exception(
                            "Error processing background job",
                            extra={
                                "evt": "bgc_job_failed",
                                "job_id": job.id,
                                "type": job.type,
                                "attempts": attempts,
                            },
                        )
                        BACKGROUND_JOB_FAILURES_TOTAL.labels(type=job_type).inc()
                        terminal = job_repo.mark_failed(job.id, error=str(exc))
                        if terminal:
                            logger.error(
                                "Background job moved to dead-letter queue",
                                extra={
                                    "evt": "bgc_job_dead_letter",
                                    "job_id": job.id,
                                    "type": job_type,
                                    "attempts": getattr(job, "attempts", 0),
                                },
                            )
                        db.commit()
                        BACKGROUND_JOBS_FAILED.set(job_repo.count_failed_jobs())
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - safety logging
            logger.exception("Background job worker loop error: %s", str(exc))


def _ensure_expiry_job_scheduled() -> None:
    """Seed the background check expiry sweep job if missing."""

    if not getattr(settings, "bgc_expiry_enabled", False):
        logger.info("Skipping expiry job seed because bgc_expiry_enabled is False")
        return

    session = SessionLocal()
    try:
        job_repo = BackgroundJobRepository(session)
        existing = job_repo.get_next_scheduled("bgc.expiry_sweep")
        if existing is None:
            job_repo.enqueue(
                type="bgc.expiry_sweep",
                payload={"days": 30},
                available_at=_next_expiry_run(),
            )
            session.commit()
        else:
            session.commit()
    except Exception as exc:  # pragma: no cover - safety logging
        session.rollback()
        logger.warning("Unable to seed expiry sweep job: %s", str(exc))
    finally:
        session.close()


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


_BGC_ENV_LOGGED = False


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
        key_len = len(api_key_value or "")
        logger.info(
            "BGC config summary site_mode=%s cors_allow_origins=%s checkr_env=%s "
            "checkr_api_base=%s checkr_api_key_len=%s checkr_hosted_workflow=%s "
            "checkr_default_package=%s",
            getattr(settings, "site_mode", "local"),
            list(allow_origins),
            getattr(settings, "checkr_env", "sandbox"),
            getattr(settings, "checkr_api_base", ""),
            key_len,
            getattr(settings, "checkr_hosted_workflow", None),
            getattr(settings, "checkr_package", getattr(settings, "checkr_default_package", None)),
        )
        _BGC_ENV_LOGGED = True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Unable to log BGC config summary: %s", exc)


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
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
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


_DYN_ALLOWED_ORIGINS = _compute_allowed_origins()
assert (
    "*" not in _DYN_ALLOWED_ORIGINS
), "CORS allow_origins cannot include * when allow_credentials=True"
_log_bgc_config_summary(_DYN_ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DYN_ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,  # Support Vercel preview deployments
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
logger.info("CORS allow_origins=%s allow_credentials=%s", _DYN_ALLOWED_ORIGINS, True)

app.add_middleware(
    EnsureCorsOnErrorMiddleware,
    allowed_origins=_DYN_ALLOWED_ORIGINS,
    origin_regex=CORS_ORIGIN_REGEX,
)

# Keep MonitoringMiddleware (pure ASGI-style) below CORS
app.add_middleware(MonitoringMiddleware)

if perf_counters_enabled():
    app.add_middleware(PerfCounterMiddleware)

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
        path = scope.get("path", "")
        if scope["type"] == "http" and (
            path.startswith(SSE_PATH_PREFIX) or path == "/internal/metrics"
        ):
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


app.add_middleware(SSEAwareGZipMiddleware, minimum_size=500)

# Create API v1 router
api_v1 = APIRouter(prefix="/api/v1")

# Mount v1 routes
api_v1.include_router(instructors_v1.router, prefix="/instructors")  # type: ignore[attr-defined]
api_v1.include_router(bookings_v1.router, prefix="/bookings")  # type: ignore[attr-defined]
api_v1.include_router(instructor_bookings_v1.router, prefix="/instructor-bookings")  # type: ignore[attr-defined]

# Include routers
PUBLIC_OPEN_PATHS = {
    "/",
    "/health",
    "/ready",
    "/auth/login",
    "/auth/login-with-session",
    "/auth/register",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
    "/api/auth/2fa/verify-login",
    "/api/referrals/claim",
}

PUBLIC_OPEN_PREFIXES = (
    "/api/public",
    "/api/auth/password-reset/verify",
    "/api/config",
    "/r/",
    "/api/v1/instructors",  # v1 instructors endpoints are public (some require auth via dependency)
)

public_guard_dependency = public_guard(
    open_paths=sorted(PUBLIC_OPEN_PATHS),
    open_prefixes=sorted(PUBLIC_OPEN_PREFIXES),
)


# Mount API v1 first
app.include_router(api_v1)

app.include_router(auth.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(two_factor_auth.router, dependencies=[Depends(public_guard_dependency)])

# Legacy instructor routes - DEPRECATED, use /api/v1/instructors instead
# app.include_router(instructors.router)  # Was: /instructors
# app.include_router(instructors.api_router)  # Was: /api/instructors

app.include_router(instructor_background_checks.router)
app.include_router(instructor_bookings.router)
app.include_router(instructor_bookings.api_router)
app.include_router(account_management.router)
app.include_router(services.router)
app.include_router(availability_windows.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(password_reset.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(bookings.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(student_badges.router)
app.include_router(pricing_preview.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(pricing_config_public.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(favorites.router)
app.include_router(payments.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(messages.router)
app.include_router(metrics.router)
if os.getenv("AVAILABILITY_PERF_DEBUG", "0").lower() in {"1", "true", "yes"}:
    app.include_router(metrics.metrics_lite_router, include_in_schema=False)
app.include_router(monitoring.router)
app.include_router(alerts.router)
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(codebase_metrics.router)
app.include_router(public.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(referrals.public_router, dependencies=[Depends(public_guard_dependency)])
app.include_router(referrals.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(referrals.admin_router)
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(search_history.router, prefix="/api/search-history", tags=["search-history"])
app.include_router(addresses.router, dependencies=[Depends(public_guard_dependency)])
app.include_router(redis_monitor.router)
app.include_router(ready.router)
app.include_router(database_monitor.router)
app.include_router(admin_config.router)
app.include_router(admin_audit.router)
app.include_router(privacy.router, prefix="/api", tags=["privacy"])
app.include_router(stripe_webhooks.router)
app.include_router(webhooks_checkr.router)
app.include_router(prometheus.router)
app.include_router(uploads.router)
app.include_router(users_profile_picture.router)
app.include_router(beta.router)
app.include_router(reviews.router)
app.include_router(admin_badges.router)
app.include_router(gated.router)
app.include_router(internal.router)
app.include_router(admin_background_checks.router)
app.include_router(admin_instructors.router)


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


def _apply_health_headers(response: Response) -> None:
    import os as _os

    site_mode = _os.getenv("SITE_MODE", "").lower().strip() or "unset"
    response.headers["X-Site-Mode"] = site_mode
    response.headers["X-Phase"] = _os.getenv("BETA_PHASE", "beta")
    response.headers["X-Commit-Sha"] = _os.getenv("COMMIT_SHA", "dev")
    try:
        if site_mode == "local" and bool(getattr(settings, "is_testing", False)):
            response.headers["X-Testing"] = "1"
    except Exception:
        pass


def _health_payload() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service=f"{BRAND_NAME.lower()}-api",
        version=API_VERSION,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
def health_check(response: Response) -> HealthResponse:
    _apply_health_headers(response)
    return _health_payload()


@app.get("/api/health", response_model=HealthResponse)
def api_health(response: Response) -> HealthResponse:
    _apply_health_headers(response)
    return _health_payload()


@app.get("/health/lite", response_model=HealthLiteResponse)
def health_check_lite() -> HealthLiteResponse:
    """Lightweight health check that doesn't hit database"""
    return HealthLiteResponse(status="ok")


@metrics_router.get("/internal/metrics", include_in_schema=False)
def internal_metrics_endpoint(
    request: Request, _: None = Depends(_check_metrics_basic_auth)
) -> Response:
    from app.core.config import settings as metrics_settings

    allowlist = metrics_settings.metrics_ip_allowlist
    if allowlist:
        client_ip = _extract_metrics_client_ip(request)
        if not _ip_allowed(client_ip, allowlist):
            _metrics_auth_failure("forbidden")
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")

    global _metrics_cache
    now = monotonic()
    payload: Optional[bytes] = None

    with _metrics_cache_lock:
        if _metrics_cache is not None:
            cached_at, cached_payload = _metrics_cache
            if now - cached_at <= _METRICS_CACHE_TTL_SECONDS:
                payload = cached_payload

    if payload is None:
        fresh = cast(bytes, generate_latest(PROM_REGISTRY))
        if len(fresh) > metrics_settings.metrics_max_bytes:
            return Response(
                content=b"metrics payload exceeds configured limit",
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                media_type="text/plain; charset=utf-8",
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        with _metrics_cache_lock:
            _metrics_cache = (now, fresh)
        payload = fresh

    return Response(
        content=payload,
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@metrics_router.head("/internal/metrics", include_in_schema=False)
def internal_metrics_head() -> None:
    _metrics_method_not_allowed()


@metrics_router.post("/internal/metrics", include_in_schema=False)
def internal_metrics_post() -> None:
    _metrics_method_not_allowed()


@metrics_router.put("/internal/metrics", include_in_schema=False)
def internal_metrics_put() -> None:
    _metrics_method_not_allowed()


@metrics_router.patch("/internal/metrics", include_in_schema=False)
def internal_metrics_patch() -> None:
    _metrics_method_not_allowed()


@metrics_router.delete("/internal/metrics", include_in_schema=False)
def internal_metrics_delete() -> None:
    _metrics_method_not_allowed()


@metrics_router.options("/internal/metrics", include_in_schema=False)
def internal_metrics_options() -> None:
    _metrics_method_not_allowed()


@metrics_router.get("/metrics", include_in_schema=False)
def deprecated_metrics_endpoint() -> None:
    raise HTTPException(status_code=404)


@metrics_router.head("/metrics", include_in_schema=False)
def deprecated_metrics_head() -> None:
    raise HTTPException(status_code=404)


@metrics_router.api_route(
    "/metrics/{rest:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
def metrics_legacy_catch_all(rest: str) -> None:
    raise HTTPException(status_code=404)


app.include_router(metrics_router)


# Keep the original FastAPI app for tools/tests that need access to routes
fastapi_app = app


def _prewarm_metrics_cache() -> None:
    """Warm metrics cache so the first scrape is fast."""

    prometheus_metrics.prewarm()

    try:
        from .routes.prometheus import warm_prometheus_metrics_response_cache

        warm_prometheus_metrics_response_cache()
    except Exception:
        # Cache warmup should never block startup; swallow any issues.
        pass


# Wrap with ASGI middleware for production
wrapped_app: ASGIApp = TimingMiddlewareASGI(app)
wrapped_app = RateLimitMiddlewareASGI(wrapped_app)
app = wrapped_app

# Export what's needed
__all__ = ["app", "fastapi_app"]
