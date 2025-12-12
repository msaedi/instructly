from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core.constants import SSE_PATH_PREFIX
from ..database import SessionLocal
from ..monitoring.prometheus_metrics import PrometheusMetrics
from ..repositories.beta_repository import BetaSettingsRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# In-memory cache for beta settings to avoid DB query on every request
# Beta settings change ~3 times in platform lifetime (phase transitions)
# 24-hour TTL is a safety fallback; cache is invalidated explicitly on updates
BETA_SETTINGS_CACHE_TTL = 86400  # 24 hours (safety fallback)


@dataclass
class BetaSettingsCache:
    """In-memory cache for beta settings. Invalidated on admin updates."""

    phase_value: bytes = b"unknown"
    allow_signup_value: bytes = b"0"
    cached_at: float = 0.0

    def is_valid(self) -> bool:
        if self.cached_at == 0.0:
            return False  # Never loaded
        return (time.time() - self.cached_at) < BETA_SETTINGS_CACHE_TTL

    def invalidate(self) -> None:
        """Invalidate cache - forces refresh on next request."""
        self.cached_at = 0.0


_cache = BetaSettingsCache()


def invalidate_beta_settings_cache() -> None:
    """
    Invalidate the beta settings cache.
    Call this after updating beta settings via admin endpoint.
    """
    global _cache
    _cache.invalidate()
    logger.info("Beta settings cache invalidated")


def refresh_beta_settings_cache(db: "Session") -> None:
    """
    Eagerly refresh the beta settings cache.
    Call this on app startup to pre-populate the cache.
    """
    global _cache
    try:
        repo = BetaSettingsRepository(db)
        s = repo.get_singleton()
        if bool(s.beta_disabled):
            _cache.phase_value = b"disabled"
        else:
            _cache.phase_value = str(s.beta_phase).encode("utf-8")
        _cache.allow_signup_value = b"1" if bool(s.allow_signup_without_invite) else b"0"
        _cache.cached_at = time.time()
        logger.info(f"Beta settings cache loaded: phase={_cache.phase_value.decode()}")
    except Exception as e:
        logger.warning(f"Failed to pre-load beta settings cache: {e}")


class BetaPhaseHeaderMiddleware:
    """
    ASGI middleware that attaches the current beta phase to every HTTP response header.

    - Reads settings via repository pattern
    - Skips SSE endpoints
    - Sets header: x-beta-phase: disabled | instructor_only | open_beta
    - Sets header: x-beta-allow-signup: 1 | 0 (true when signup allowed without invite)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip Server-Sent Events endpoints
        path = scope.get("path", "")
        if path.startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        # Resolve beta phase - use cache to avoid DB query on every request
        global _cache
        phase_value = _cache.phase_value
        allow_signup_value = _cache.allow_signup_value

        # Only hit DB if cache is stale
        if not _cache.is_valid():
            try:
                db = SessionLocal()
                try:
                    repo = BetaSettingsRepository(db)
                    s = repo.get_singleton()
                    if bool(s.beta_disabled):
                        phase_value = b"disabled"
                    else:
                        # Ensure plain string
                        phase_value = str(s.beta_phase).encode("utf-8")
                    allow_signup_value = b"1" if bool(s.allow_signup_without_invite) else b"0"

                    # Update cache
                    _cache.phase_value = phase_value
                    _cache.allow_signup_value = allow_signup_value
                    _cache.cached_at = time.time()
                finally:
                    # async-blocking-ignore: Middleware cleanup <1ms
                    db.rollback()  # Clean up transaction before returning to pool  # async-blocking-ignore
                    db.close()
            except Exception as e:
                # Never break the response due to header resolution failures
                # Use cached values even if stale
                logger.debug(f"BetaPhaseHeaderMiddleware error: {e}")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-beta-phase", phase_value))
                headers.append((b"x-beta-allow-signup", allow_signup_value))
                message = {**message, "headers": headers}
                # Record header distribution
                try:
                    PrometheusMetrics.inc_beta_phase_header(phase_value.decode("utf-8"))
                except Exception:
                    pass
            await send(message)

        await self.app(scope, receive, send_wrapper)
