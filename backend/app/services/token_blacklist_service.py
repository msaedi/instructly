"""Redis-backed blacklist for JWT revocation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from functools import partial
import logging
import time
from typing import Any, Callable, Coroutine, TypeVar, cast

from app.core.cache_redis import get_async_cache_redis_client
from app.monitoring.prometheus_metrics import prometheus_metrics

logger = logging.getLogger(__name__)

T = TypeVar("T")

_REDIS_ERROR_TYPES: tuple[type[BaseException], ...]
try:
    from redis.exceptions import RedisError as _RedisError

    _REDIS_ERROR_TYPES = (_RedisError,)
except ImportError:
    logger.warning(
        "[TOKEN-BL] redis package not installed — Redis error types unavailable for catch narrowing"
    )
    _REDIS_ERROR_TYPES = ()

_SYNC_BRIDGE_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
) + _REDIS_ERROR_TYPES

# Sync-bridge calls happen on cookie/session auth paths. Keep this bounded so
# sync callers can safely bridge to async Redis checks without unbounded thread growth.
_SYNC_BRIDGE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="token-blacklist")


class TokenBlacklistService:
    """Redis-backed JWT token blacklist for server-side revocation."""

    KEY_PREFIX = "auth:blacklist:jti:"
    _SYNC_WAIT_SECONDS = 5.0

    def __init__(self, redis_client: Any | None = None):
        self._redis_client = redis_client

    @classmethod
    def _key(cls, jti: str) -> str:
        return f"{cls.KEY_PREFIX}{jti}"

    async def _get_redis_client(self) -> Any:
        if self._redis_client is not None:
            return self._redis_client
        return await get_async_cache_redis_client()

    async def revoke_token(
        self,
        jti: str,
        exp: int,
        *,
        trigger: str = "logout",
        emit_metric: bool = True,
    ) -> bool:
        """Add token jti to blacklist with TTL equal to remaining token lifetime."""
        if not jti:
            return False

        try:
            exp_ts = int(exp)
        except (TypeError, ValueError):
            logger.warning("[TOKEN-BL] Invalid exp claim for revocation: %r", exp)
            return False

        ttl_seconds = exp_ts - int(time.time())
        if ttl_seconds <= 0:
            return False

        try:
            redis = await self._get_redis_client()
            if redis is None:
                logger.warning("[TOKEN-BL] Redis unavailable, revoke skipped for jti=%s", jti)
                return False
            await redis.setex(self._key(jti), ttl_seconds, "1")
            if emit_metric:
                try:
                    prometheus_metrics.record_token_revocation(trigger)
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
            return True
        except _SYNC_BRIDGE_FALLBACK_ERRORS as exc:
            logger.error("[TOKEN-BL] Failed to revoke token jti=%s: %s", jti, exc, exc_info=True)
            return False

    async def claim_and_revoke(self, jti: str, exp: int) -> bool:
        """Atomically claim a JTI for refresh rotation.

        Uses SET NX (set-if-not-exists) so exactly one concurrent caller wins.
        Returns True if this caller is the first to claim the JTI, False if
        already claimed or on Redis error (fail-closed).
        """
        if not jti:
            return False

        try:
            exp_ts = int(exp)
        except (TypeError, ValueError):
            logger.warning("[TOKEN-BL] Invalid exp claim for claim_and_revoke: %r", exp)
            return False

        ttl_seconds = exp_ts - int(time.time())
        if ttl_seconds <= 0:
            return False

        try:
            redis = await self._get_redis_client()
            if redis is None:
                logger.warning(
                    "[TOKEN-BL] Redis unavailable, claim_and_revoke fail-closed for jti=%s", jti
                )
                return False
            result = await redis.set(self._key(jti), "1", nx=True, ex=ttl_seconds)
            return bool(result)
        except _SYNC_BRIDGE_FALLBACK_ERRORS as exc:
            logger.error(
                "[TOKEN-BL] claim_and_revoke failed for jti=%s (fail-closed): %s",
                jti,
                exc,
                exc_info=True,
            )
            return False

    async def is_revoked(self, jti: str) -> bool:
        """Return True when jti is blacklisted (fail-closed on Redis errors)."""
        if not jti:
            return True

        try:
            redis = await self._get_redis_client()
            if redis is None:
                logger.warning("[TOKEN-BL] Redis unavailable during revoke check, fail-closed")
                return True
            exists = await redis.exists(self._key(jti))
            return bool(exists)
        except _SYNC_BRIDGE_FALLBACK_ERRORS as exc:
            logger.warning("[TOKEN-BL] Revoke check failed for jti=%s (fail-closed): %s", jti, exc)
            return True

    def _run_sync(
        self,
        async_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        default: T,
        **kwargs: Any,
    ) -> T:
        try:
            # No running loop in this thread: try worker-thread portal first.
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                import anyio

                runner = partial(async_fn, *args, **kwargs)
                return cast(T, anyio.from_thread.run(runner))
            except RuntimeError as exc:
                exc_text = str(exc).lower()
                if not any(
                    marker in exc_text
                    for marker in (
                        "no current event loop",
                        "no running",
                        "anyio worker thread",
                        "event loop token",
                    )
                ):
                    raise
                try:
                    return asyncio.run(async_fn(*args, **kwargs))
                except _SYNC_BRIDGE_FALLBACK_ERRORS as exc:
                    logger.warning("[TOKEN-BL] Sync bridge failed, using default: %s", exc)
                    return default

        # Running loop in this thread: bridge via bounded executor.
        def _runner() -> T:
            return asyncio.run(async_fn(*args, **kwargs))

        future = _SYNC_BRIDGE_EXECUTOR.submit(_runner)
        try:
            return future.result(timeout=self._SYNC_WAIT_SECONDS)
        except FuturesTimeoutError:
            future.cancel()
            logger.warning("[TOKEN-BL] Sync bridge timed out, using default")
            return default
        except _SYNC_BRIDGE_FALLBACK_ERRORS as exc:
            logger.warning("[TOKEN-BL] Sync bridge executor failed, using default: %s", exc)
            return default

    def revoke_token_sync(
        self,
        jti: str,
        exp: int,
        *,
        trigger: str = "logout",
        emit_metric: bool = True,
    ) -> bool:
        """Synchronous revocation bridge for sync contexts."""
        return self._run_sync(
            self.revoke_token,
            jti,
            exp,
            trigger=trigger,
            emit_metric=emit_metric,
            default=False,
        )

    def is_revoked_sync(self, jti: str) -> bool:
        """Synchronous revoke-check bridge for sync contexts (fail-closed)."""
        return self._run_sync(self.is_revoked, jti, default=True)
