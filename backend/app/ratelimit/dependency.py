from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import os
import time
from typing import Any

from fastapi import Request, Response

from ..core import config as core_config
from ..core.config import secret_or_plain
from .config import BUCKETS, is_shadow_mode, settings
from .gcra import Decision
from .headers import set_policy_headers, set_rate_headers
from .metrics import rl_decisions, rl_eval_duration, rl_eval_errors, rl_retry_after
from .redis_backend import GCRA_LUA, get_redis

logger = logging.getLogger(__name__)


def _compute_interval_ms(rate_per_min: int) -> int:
    if rate_per_min <= 0:
        return 0
    return int(60000 / rate_per_min)


def _namespaced_key(bucket: str, identity: str) -> str:
    return f"{settings.namespace}:{bucket}:{identity}"


def _is_testing_env() -> bool:
    try:
        if getattr(settings, "is_testing", False):
            return True
    except Exception:
        logger.debug("Non-fatal error ignored", exc_info=True)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    flag = os.getenv("IS_TESTING", "").strip().lower()
    return flag in {"1", "true", "yes"}


def _rate_limit_bypass_token() -> str:
    return secret_or_plain(getattr(core_config.settings, "rate_limit_bypass_token", None)).strip()


def _should_bypass_request(request: Request) -> bool:
    bypass_token = _rate_limit_bypass_token()
    return bool(bypass_token and request.headers.get("X-Rate-Limit-Bypass") == bypass_token)


def _set_testing_headers(bucket: str, response: Response) -> None:
    now_s = time.time()
    set_rate_headers(
        response,
        remaining=1000,
        limit=1000,
        reset_epoch_s=int(now_s + 60),
        retry_after_s=None,
    )
    set_policy_headers(response, bucket=bucket, shadow=is_shadow_mode(bucket))


def _resolve_identity(request: Request) -> str:
    identity = None
    try:
        identity = getattr(request.state, "rate_identity", None)
    except Exception:
        identity = None
    if not identity:
        client = getattr(request, "client", None)
        identity = getattr(client, "host", None) if client else None
    if not identity:
        identity = request.headers.get("x-forwarded-for", "unknown")
    return str(identity)


def _policy_for_bucket(bucket: str) -> dict[str, Any] | None:
    return BUCKETS.get(bucket) or BUCKETS.get(settings.default_policy)


async def _get_redis_client() -> Any:
    try:
        return await get_redis()
    except Exception:
        return None


def _fallback_decision(interval_ms: int, burst: int) -> Decision:
    return Decision(
        allowed=True,
        retry_after_s=0.0,
        remaining=max(0, burst),
        limit=burst + 1,
        reset_epoch_s=time.time() + (burst * (interval_ms / 1000.0)),
    )


async def _evaluate_decision(bucket: str, key: str, rate_per_min: int, burst: int) -> Decision:
    r = await _get_redis_client()
    now_ms = int(time.time() * 1000)
    interval_ms = _compute_interval_ms(rate_per_min)
    if interval_ms <= 0:
        return Decision(
            False, retry_after_s=float("inf"), remaining=0, limit=0, reset_epoch_s=time.time()
        )

    start_eval = time.perf_counter()
    try:
        if r is None:
            raise RuntimeError("Redis unavailable")
        res = await r.eval(GCRA_LUA, 1, key, now_ms, interval_ms, burst)
        return Decision(
            bool(int(res[0])),
            float(res[1]) / 1000.0,
            int(res[2]),
            int(res[3]),
            float(res[4]),
        )
    except Exception:
        try:
            rl_eval_errors.labels(bucket=bucket).inc()
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
        return _fallback_decision(interval_ms, burst)
    finally:
        try:
            rl_eval_duration.labels(bucket=bucket).observe(
                max(time.perf_counter() - start_eval, 0.0)
            )
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)


def _apply_headers_and_metrics(bucket: str, response: Response, decision: Decision) -> bool:
    set_rate_headers(
        response,
        decision.remaining,
        decision.limit,
        decision.reset_epoch_s,
        decision.retry_after_s if not decision.allowed else None,
    )
    shadow_flag = is_shadow_mode(bucket)
    set_policy_headers(response, bucket=bucket, shadow=shadow_flag)
    rl_retry_after.labels(bucket=bucket, shadow=str(shadow_flag)).observe(
        max(decision.retry_after_s, 0.0)
    )
    return shadow_flag


def _raise_or_record_block(bucket: str, decision: Decision, shadow_flag: bool) -> None:
    if decision.allowed:
        rl_decisions.labels(bucket=bucket, action="allow", shadow=str(shadow_flag)).inc()
        return

    rl_decisions.labels(
        bucket=bucket,
        action="block" if not shadow_flag else "shadow_block",
        shadow=str(shadow_flag),
    ).inc()
    if shadow_flag:
        return

    from fastapi import HTTPException

    raise HTTPException(status_code=429, detail="Rate limit exceeded")


async def _apply_rate_limit(bucket: str, request: Request, response: Response) -> None:
    if _should_bypass_request(request):
        return
    if _is_testing_env():
        _set_testing_headers(bucket, response)
        return
    if not settings.enabled:
        return

    policy = _policy_for_bucket(bucket)
    if not policy:
        return

    rate_per_min = int(policy.get("rate_per_min", 60))
    burst = int(policy.get("burst", 0))
    identity = _resolve_identity(request)
    key = _namespaced_key(bucket, identity)
    decision = await _evaluate_decision(bucket, key, rate_per_min, burst)
    shadow_flag = _apply_headers_and_metrics(bucket, response, decision)
    _raise_or_record_block(bucket, decision, shadow_flag)


def rate_limit(bucket: str) -> Callable[[Request, Response], Awaitable[None]]:
    async def dep(request: Request, response: Response) -> None:
        await _apply_rate_limit(bucket, request, response)

    return dep
