"""
OpenTelemetry configuration for InstaInstru.

This module initializes distributed tracing with Axiom as the backend.
Enable/disable via ENABLE_OTEL environment variable.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
import os
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import unquote

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)

# Lazy imports to avoid loading OTel when disabled
_tracer_provider: Optional["TracerProvider"] = None
_otel_initialized = False
_sqlalchemy_engine: Optional[Any] = None
_sqlalchemy_instrumented = False


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def is_otel_enabled() -> bool:
    """Check if OpenTelemetry is enabled."""
    return _is_truthy_env(os.getenv("ENABLE_OTEL"))


def _parse_otlp_headers(raw: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if not raw:
        return headers

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            logger.warning(
                "Malformed OTLP header entry (missing '='): %r",
                entry,
            )
            continue

        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            logger.warning(
                "Malformed OTLP header entry (empty key): %r",
                entry,
            )
            continue

        headers[key] = unquote(value)
    return headers


def _safe_int(env_var: str, default: int) -> int:
    """Safely parse integer env var with fallback to default."""
    try:
        value = os.getenv(env_var)
        return int(value) if value else default
    except (TypeError, ValueError):
        logger.warning(
            "Invalid integer value for %s, using default %d",
            env_var,
            default,
        )
        return default


def init_otel(service_name: Optional[str] = None) -> bool:
    """
    Initialize OpenTelemetry tracing for the application.

    Args:
        service_name: Override service name (defaults to OTEL_SERVICE_NAME env var)

    Returns:
        True if initialization succeeded, False if disabled or failed
    """
    global _tracer_provider, _otel_initialized

    if _otel_initialized:
        logger.debug("OTel already initialized, skipping")
        return True

    if not is_otel_enabled():
        logger.info("OpenTelemetry disabled (ENABLE_OTEL=%r)", os.getenv("ENABLE_OTEL"))
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        svc_name = service_name or os.getenv("OTEL_SERVICE_NAME", "instainstru-api")
        svc_version = os.getenv("GIT_SHA", "unknown")
        environment = os.getenv("ENVIRONMENT", "development")

        resource = Resource.create(
            {
                SERVICE_NAME: svc_name,
                SERVICE_VERSION: svc_version,
                "deployment.environment": environment,
            }
        )

        # Sampling is configured via standard OTel environment variables:
        # - OTEL_TRACES_SAMPLER (e.g., "parentbased_traceidratio")
        # - OTEL_TRACES_SAMPLER_ARG (e.g., "0.5" for 50% sampling)
        # If not set, defaults to AlwaysOn (100% sampling).
        _tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(_tracer_provider)

        raw_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
        exporter_headers: dict[str, str] | None = None
        if raw_headers:
            exporter_headers = _parse_otlp_headers(raw_headers)
        else:
            axiom_token = os.getenv("AXIOM_API_TOKEN")
            axiom_dataset = os.getenv("AXIOM_TRACES_DATASET", "instainstru-traces")
            if axiom_token:
                exporter_headers = {
                    "Authorization": f"Bearer {axiom_token}",
                    "X-Axiom-Dataset": axiom_dataset,
                }

        # Canonical OTLP endpoint strategy:
        # Treat OTEL_EXPORTER_OTLP_ENDPOINT as the base URL and append /v1/traces here.
        # This avoids ambiguity between base vs. explicit trace endpoint settings.
        base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.axiom.co").rstrip("/")
        if base_endpoint.endswith("/v1/traces"):
            otlp_endpoint = base_endpoint
        else:
            otlp_endpoint = f"{base_endpoint}/v1/traces"

        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers=exporter_headers or None,
        )

        # BatchSpanProcessor settings can be tuned via env vars:
        # OTEL_BSP_MAX_QUEUE_SIZE, OTEL_BSP_MAX_EXPORT_BATCH_SIZE, OTEL_BSP_SCHEDULE_DELAY_MILLIS
        span_processor = BatchSpanProcessor(
            exporter,
            max_queue_size=_safe_int("OTEL_BSP_MAX_QUEUE_SIZE", 2048),
            max_export_batch_size=_safe_int("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", 512),
            schedule_delay_millis=_safe_int("OTEL_BSP_SCHEDULE_DELAY_MILLIS", 5000),
        )
        _tracer_provider.add_span_processor(span_processor)

        # Enable log correlation (inject trace_id into log records)
        # IMPORTANT: set_logging_format=False to avoid conflicting with existing JSON logging
        LoggingInstrumentor().instrument(set_logging_format=False)

        try:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor

            CeleryInstrumentor().instrument()
            logger.debug("Celery instrumented")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Failed to instrument Celery: %s", exc)

        if _sqlalchemy_engine is not None:
            _instrument_sqlalchemy(_sqlalchemy_engine)

        _otel_initialized = True
        logger.info(
            "OpenTelemetry initialized: service=%s environment=%s endpoint=%s",
            svc_name,
            environment,
            otlp_endpoint,
        )
        return True

    except Exception as exc:
        logger.error("Failed to initialize OpenTelemetry: %s", exc, exc_info=True)
        return False


def instrument_fastapi(app: Any) -> bool:
    """
    Instrument a FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance

    Returns:
        True if instrumentation succeeded
    """
    if not is_otel_enabled():
        return False

    if getattr(app, "_otel_instrumented", False):
        return True

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from app.core.constants import SSE_PATH_PREFIX

        excluded_urls = ",".join(
            [
                "health",
                "ready",
                "metrics",
                "api/v1/health",
                "api/v1/ready",
                "api/v1/metrics",
                SSE_PATH_PREFIX.lstrip("/"),
            ]
        )

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=excluded_urls,
        )

        setattr(app, "_otel_instrumented", True)
        logger.info("FastAPI instrumented with OTel (excluded: %s)", excluded_urls)
        return True

    except Exception as exc:
        logger.error("Failed to instrument FastAPI: %s", exc, exc_info=True)
        return False


def _instrument_sqlalchemy(engine: Any) -> None:
    global _sqlalchemy_instrumented

    if _sqlalchemy_instrumented:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
        _sqlalchemy_instrumented = True
        logger.debug("SQLAlchemy instrumented with engine")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to instrument SQLAlchemy: %s", exc)


def instrument_database(engine: Any) -> None:
    """
    Register and instrument the SQLAlchemy engine for OTel spans.

    This should be called after the engine is created. If OTel is not yet
    initialized, the engine is stored and instrumented when init_otel() runs.
    """
    global _sqlalchemy_engine

    _sqlalchemy_engine = engine
    if not is_otel_enabled() or not _otel_initialized:
        return

    _instrument_sqlalchemy(engine)


def instrument_additional_libraries() -> None:
    """
    Instrument additional libraries used by the application.
    Call after init_otel().
    """
    if not is_otel_enabled():
        return

    if _sqlalchemy_engine is not None:
        _instrument_sqlalchemy(_sqlalchemy_engine)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.debug("HTTPX instrumented")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to instrument HTTPX: %s", exc)

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.debug("Redis instrumented")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to instrument Redis: %s", exc)


def shutdown_otel() -> None:
    """Gracefully shutdown OpenTelemetry (flush pending spans)."""
    global _tracer_provider, _otel_initialized, _sqlalchemy_instrumented

    if not _otel_initialized:
        return

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry shutdown complete")
        except Exception as exc:
            logger.error("Error during OTel shutdown: %s", exc)

    _otel_initialized = False
    _sqlalchemy_instrumented = False
    _tracer_provider = None


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID as a hex string.
    Useful for adding to Sentry tags or response headers.

    Returns:
        32-character hex trace ID, or None if no active span
    """
    if not is_otel_enabled():
        return None

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return None

        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return None

        return format(ctx.trace_id, "032x")

    except Exception:
        return None


def get_current_span_id() -> Optional[str]:
    """
    Get the current span ID as a hex string.

    Returns:
        16-character hex span ID, or None if no active span
    """
    if not is_otel_enabled():
        return None

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return None

        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return None

        return format(ctx.span_id, "016x")

    except Exception:
        return None


@contextmanager
def create_span(name: str, attributes: Optional[dict[str, Any]] = None) -> Iterator[Optional[Any]]:
    """
    Create a custom span for manual instrumentation.

    Usage:
        with create_span("process_payment", {"payment.amount": 100}):
            # ... do work ...
    """
    # WARNING: Do not add high-cardinality attributes as span names.
    # User emails, phone numbers, payment IDs should be attributes only,
    # not span names. Scrub PII where appropriate.
    if not is_otel_enabled():
        yield None
        return

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span

    except Exception as exc:
        logger.warning("Failed to create span '%s': %s", name, exc)
        yield None
