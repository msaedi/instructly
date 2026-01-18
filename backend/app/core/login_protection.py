"""Login protection primitives (concurrency cap, per-account limits, CAPTCHA, lockouts)."""
from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from types import TracebackType
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
import httpx
from prometheus_client import Counter, Histogram
from redis.asyncio import Redis

from app.core.cache_redis import get_async_cache_redis_client
from app.core.config import is_running_tests, settings
from app.monitoring.prometheus_metrics import REGISTRY

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

login_attempts_total = Counter(
    "instainstru_login_attempts_total",
    "Total login attempts by result",
    [
        "result"
    ],  # success | invalid_credentials | rate_limited | locked_out | captcha_required | captcha_failed | deactivated | two_factor_challenge | error | queue_timeout
    registry=REGISTRY,
)

login_rate_limited_total = Counter(
    "instainstru_login_rate_limited_total",
    "Rate limited login attempts by reason",
    ["reason"],  # minute_limit | hour_limit | queue_timeout
    registry=REGISTRY,
)

login_lockouts_total = Counter(
    "instainstru_login_lockouts_total",
    "Account lockouts triggered (by threshold)",
    ["threshold"],
    registry=REGISTRY,
)

login_captcha_required_total = Counter(
    "instainstru_login_captcha_required_total",
    "CAPTCHA challenges issued or validated during login",
    ["result"],  # required | missing | failed | passed
    registry=REGISTRY,
)

login_slot_wait_seconds = Histogram(
    "instainstru_login_slot_wait_seconds",
    "Time spent waiting for login concurrency slot",
    registry=REGISTRY,
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def record_login_result(result: str) -> None:
    """Increment login attempt counter for the given result."""
    try:
        login_attempts_total.labels(result=result).inc()
    except Exception:
        # Metrics must never block auth path
        logger.debug("Non-fatal error ignored", exc_info=True)


def record_captcha_event(result: str) -> None:
    """Increment CAPTCHA-related metrics."""
    try:
        login_captcha_required_total.labels(result=result).inc()
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)


async def _get_redis_client(explicit: Optional[Redis] = None) -> Optional[Redis]:
    """Return async Redis client, allowing override for tests."""
    if explicit is not None:
        return explicit
    return await get_async_cache_redis_client()


# --------------------------------------------------------------------------- #
# Concurrency control
# --------------------------------------------------------------------------- #

_semaphore_limit = max(1, settings.login_concurrency_limit or 10)
LOGIN_SEMAPHORE = asyncio.Semaphore(_semaphore_limit)
_DEFAULT_SLOT_TIMEOUT = max(0.1, float(settings.login_concurrency_timeout_seconds or 5.0))


async def acquire_login_slot(timeout: float | None = None) -> float:
    """
    Acquire a login slot. Returns wait time (seconds) on success, raises 429 on timeout.

    Usage:
        async with login_slot():
            ...
    """
    wait_start = perf_counter()
    try:
        await asyncio.wait_for(LOGIN_SEMAPHORE.acquire(), timeout=timeout or _DEFAULT_SLOT_TIMEOUT)
        waited = perf_counter() - wait_start
        login_slot_wait_seconds.observe(waited)
        return waited
    except asyncio.TimeoutError:
        login_rate_limited_total.labels(reason="queue_timeout").inc()
        record_login_result("queue_timeout")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again shortly.",
            headers={"Retry-After": str(int(timeout or _DEFAULT_SLOT_TIMEOUT))},
        ) from None


class login_slot:
    """Async context manager for login concurrency control."""

    def __init__(self, *, timeout: float | None = None) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "login_slot":
        await acquire_login_slot(self.timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        LOGIN_SEMAPHORE.release()
        return False


# --------------------------------------------------------------------------- #
# Per-account rate limiting
# --------------------------------------------------------------------------- #


class AccountRateLimiter:
    """Rate limit login attempts per email address."""

    def __init__(self, redis: Optional[Redis] = None) -> None:
        self.redis = redis
        self._explicit_redis = redis is not None
        self.attempts_per_minute = max(1, settings.login_attempts_per_minute or 5)
        self.attempts_per_hour = max(1, settings.login_attempts_per_hour or 20)

    async def check(self, email: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if login attempt is allowed (without incrementing counters).

        Returns:
            (allowed: bool, info: dict with remaining attempts and reset time)
        """
        if is_running_tests() and not self._explicit_redis:
            return True, {"remaining_minute": None, "remaining_hour": None}

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rate limiter redis unavailable: %s", exc)
            return True, {"remaining_minute": None, "remaining_hour": None}
        if redis is None:
            return True, {"remaining_minute": None, "remaining_hour": None}

        email_lower = email.lower()
        minute_key = f"login:minute:{email_lower}"
        hour_key = f"login:hour:{email_lower}"

        try:
            pipe = redis.pipeline()
            pipe.get(minute_key)
            pipe.get(hour_key)
            results = await pipe.execute()

            minute_count = int(results[0] or 0)
            hour_count = int(results[1] or 0)

            if minute_count >= self.attempts_per_minute:
                ttl = await redis.ttl(minute_key)
                retry_after = max(int(ttl or 0), 1)
                login_rate_limited_total.labels(reason="minute_limit").inc()
                return False, {
                    "reason": "minute_limit",
                    "retry_after": retry_after,
                    "message": f"Too many attempts. Try again in {retry_after} seconds.",
                }

            if hour_count >= self.attempts_per_hour:
                ttl = await redis.ttl(hour_key)
                retry_after = max(int(ttl or 0), 1)
                login_rate_limited_total.labels(reason="hour_limit").inc()
                return False, {
                    "reason": "hour_limit",
                    "retry_after": retry_after,
                    "message": f"Too many attempts. Try again in {max(retry_after // 60, 1)} minutes.",
                }

            return True, {
                "remaining_minute": self.attempts_per_minute - minute_count,
                "remaining_hour": self.attempts_per_hour - hour_count,
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rate limiter check failed; allowing login attempt: %s", exc)
            return True, {"remaining_minute": None, "remaining_hour": None}

    async def record_attempt(self, email: str) -> None:
        """Increment rate limit counters after a failed login attempt."""
        if is_running_tests() and not self._explicit_redis:
            return

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rate limiter redis unavailable: %s", exc)
            return
        if redis is None:
            return

        email_lower = email.lower()
        minute_key = f"login:minute:{email_lower}"
        hour_key = f"login:hour:{email_lower}"

        try:
            pipe = redis.pipeline()
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)
            await pipe.execute()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rate limiter increment failed: %s", exc)

    async def check_and_increment(self, email: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if login attempt is allowed and increment counters.

        DEPRECATED: Use check() + record_attempt() for better UX.
        This method is kept for backward compatibility.

        Returns:
            (allowed: bool, info: dict with remaining attempts and reset time)
        """
        allowed, info = await self.check(email)
        if allowed:
            await self.record_attempt(email)
            # Adjust remaining counts since we just incremented
            if info.get("remaining_minute") is not None:
                info["remaining_minute"] = max(0, info["remaining_minute"] - 1)
            if info.get("remaining_hour") is not None:
                info["remaining_hour"] = max(0, info["remaining_hour"] - 1)
        return allowed, info

    async def reset(self, email: str) -> None:
        """Reset counters on successful login."""
        if is_running_tests() and not self._explicit_redis:
            return

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rate limiter reset skipped (redis unavailable): %s", exc)
            return
        if redis is None:
            return

        email_lower = email.lower()
        await redis.delete(f"login:minute:{email_lower}", f"login:hour:{email_lower}")


# --------------------------------------------------------------------------- #
# Progressive lockout
# --------------------------------------------------------------------------- #


class AccountLockout:
    """Progressive account lockout after failed attempts."""

    LOCKOUT_THRESHOLDS = [
        (5, 30),  # After 5 failures: 30 second lockout
        (10, 300),  # After 10 failures: 5 minute lockout
        (15, 1800),  # After 15 failures: 30 minute lockout
        (20, 3600),  # After 20 failures: 1 hour lockout
    ]

    def __init__(self, redis: Optional[Redis] = None) -> None:
        self.redis = redis
        self._explicit_redis = redis is not None

    async def check_lockout(self, email: str) -> Tuple[bool, Dict[str, Any]]:
        """Check if account is currently locked out."""
        if is_running_tests() and not self._explicit_redis:
            return False, {"locked": False}

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Lockout redis unavailable: %s", exc)
            return False, {"locked": False}
        if redis is None:
            return False, {"locked": False}

        email_lower = email.lower()
        lockout_key = f"login:lockout:{email_lower}"

        try:
            lockout_until = await redis.get(lockout_key)
            if lockout_until:
                ttl = await redis.ttl(lockout_key)
                retry_after = max(int(ttl or 0), 1)
                return True, {
                    "locked": True,
                    "retry_after": retry_after,
                    "message": f"Account temporarily locked. Try again in {self._format_time(retry_after)}.",
                }

            return False, {"locked": False}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Lockout check failed; treating as unlocked: %s", exc)
            return False, {"locked": False}

    async def record_failure(self, email: str) -> Dict[str, Any]:
        """
        Record a failed login attempt and apply lockout if threshold reached.

        Returns:
            dict with failure count and any lockout applied
        """
        if is_running_tests() and not self._explicit_redis:
            return {"failures": None, "lockout_applied": False}

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Lockout redis unavailable; skipping failure tracking: %s", exc)
            return {"failures": None, "lockout_applied": False}
        if redis is None:
            return {"failures": None, "lockout_applied": False}

        email_lower = email.lower()
        failures_key = f"login:failures:{email_lower}"
        lockout_key = f"login:lockout:{email_lower}"

        try:
            failures = await redis.incr(failures_key)
            await redis.expire(failures_key, 3600)

            for threshold, lockout_seconds in self.LOCKOUT_THRESHOLDS:
                if failures == threshold:
                    await redis.setex(lockout_key, lockout_seconds, "1")
                    login_lockouts_total.labels(threshold=str(threshold)).inc()
                    return {
                        "failures": failures,
                        "lockout_applied": True,
                        "lockout_seconds": lockout_seconds,
                        "message": f"Too many failed attempts. Account locked for {self._format_time(lockout_seconds)}.",
                    }

            return {"failures": failures, "lockout_applied": False}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Lockout failure tracking failed; continuing without lockout: %s", exc)
            return {"failures": None, "lockout_applied": False}

    async def reset(self, email: str) -> None:
        """Reset failure counters on successful login."""
        if is_running_tests() and not self._explicit_redis:
            return

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Lockout reset skipped (redis unavailable): %s", exc)
            return
        if redis is None:
            return

        email_lower = email.lower()
        await redis.delete(
            f"login:failures:{email_lower}",
            f"login:lockout:{email_lower}",
        )

    def _format_time(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds} seconds"
        if seconds < 3600:
            return f"{seconds // 60} minutes"
        return f"{seconds // 3600} hours"


# --------------------------------------------------------------------------- #
# CAPTCHA verification (Cloudflare Turnstile)
# --------------------------------------------------------------------------- #


class CaptchaVerifier:
    """Verify Cloudflare Turnstile CAPTCHA tokens."""

    VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    def __init__(self, *, secret_key: Optional[str] = None, redis: Optional[Redis] = None) -> None:
        self._explicit_secret = secret_key is not None
        self.secret_key = secret_key or settings.turnstile_secret_key
        self.redis = redis
        self.failure_threshold = max(1, settings.captcha_failure_threshold or 3)

    async def is_captcha_required(self, email: str) -> bool:
        """Check if CAPTCHA is required for this email based on failure count."""
        if is_running_tests() and not self._explicit_secret:
            return False

        if not self.secret_key:
            return False

        try:
            redis = await _get_redis_client(self.redis)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("CAPTCHA redis unavailable: %s", exc)
            return False
        if redis is None:
            return False

        email_lower = email.lower()
        failures_key = f"login:failures:{email_lower}"
        try:
            failures_raw = await redis.get(failures_key)
            failures = int(failures_raw or 0)
            return failures >= self.failure_threshold
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("CAPTCHA failure count lookup failed; skipping captcha: %s", exc)
            return False

    async def verify(self, token: Optional[str], remote_ip: Optional[str] = None) -> bool:
        """Verify a Turnstile CAPTCHA token."""
        if is_running_tests() and not self._explicit_secret:
            return True

        if not self.secret_key:
            return True

        if not token:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.VERIFY_URL,
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": remote_ip,
                    },
                    timeout=8.0,
                )
                result = response.json()
                return bool(result.get("success", False))
        except Exception as exc:
            logger.warning("CAPTCHA verification failed: %s", exc)
            return False


# Global instances (can be overridden in tests)
account_rate_limiter = AccountRateLimiter()
account_lockout = AccountLockout()
captcha_verifier = CaptchaVerifier()

__all__ = [
    "LOGIN_SEMAPHORE",
    "AccountLockout",
    "AccountRateLimiter",
    "CaptchaVerifier",
    "account_lockout",
    "account_rate_limiter",
    "captcha_verifier",
    "acquire_login_slot",
    "login_slot",
    "record_login_result",
    "record_captcha_event",
]
