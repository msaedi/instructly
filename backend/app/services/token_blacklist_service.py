"""Redis-backed blacklist for JWT revocation."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Callable, Coroutine, TypeVar, cast

from app.core.cache_redis import get_async_cache_redis_client

logger = logging.getLogger(__name__)

T = TypeVar("T")


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

    async def revoke_token(self, jti: str, exp: int) -> None:
        """Add token jti to blacklist with TTL equal to remaining token lifetime."""
        if not jti:
            return

        try:
            exp_ts = int(exp)
        except (TypeError, ValueError):
            logger.warning("[TOKEN-BL] Invalid exp claim for revocation: %r", exp)
            return

        ttl_seconds = exp_ts - int(time.time())
        if ttl_seconds <= 0:
            return

        try:
            redis = await self._get_redis_client()
            if redis is None:
                logger.warning("[TOKEN-BL] Redis unavailable, revoke skipped for jti=%s", jti)
                return
            await redis.setex(self._key(jti), ttl_seconds, "1")
        except Exception as exc:
            logger.warning("[TOKEN-BL] Failed to revoke token jti=%s: %s", jti, exc)

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
        except Exception as exc:
            logger.warning("[TOKEN-BL] Revoke check failed for jti=%s (fail-closed): %s", jti, exc)
            return True

    def _run_sync(
        self,
        async_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        default: T,
    ) -> T:
        try:
            # No running loop in this thread: try worker-thread portal first.
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                import anyio

                return cast(T, anyio.from_thread.run(async_fn, *args))
            except Exception:
                try:
                    return asyncio.run(async_fn(*args))
                except Exception as exc:
                    logger.warning("[TOKEN-BL] Sync bridge failed, using default: %s", exc)
                    return default

        # Running loop in this thread: execute async function in a dedicated thread.
        result_box: dict[str, T] = {}

        def _runner() -> None:
            try:
                result_box["value"] = asyncio.run(async_fn(*args))
            except Exception as exc:
                logger.warning("[TOKEN-BL] Sync bridge thread failed: %s", exc)

        thread = threading.Thread(
            target=_runner,
            name="token-blacklist-sync",
            daemon=True,
        )
        thread.start()
        thread.join(timeout=self._SYNC_WAIT_SECONDS)
        if thread.is_alive():
            logger.warning("[TOKEN-BL] Sync bridge timed out, using default")
            return default
        return result_box.get("value", default)

    def revoke_token_sync(self, jti: str, exp: int) -> None:
        """Synchronous revocation bridge for sync contexts."""
        self._run_sync(self.revoke_token, jti, exp, default=None)

    def is_revoked_sync(self, jti: str) -> bool:
        """Synchronous revoke-check bridge for sync contexts (fail-closed)."""
        return self._run_sync(self.is_revoked, jti, default=True)
