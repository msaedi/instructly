"""
Admin Auth Blocks API - Manage login protection states.

Provides visibility into accounts that are locked out, rate limited, or
require CAPTCHA, with tools to clear these blocks for support operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from app.core.config import settings
from app.core.enums import PermissionName
from app.core.redis import get_async_redis_client
from app.dependencies.permissions import require_permission
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["admin-auth"],
    responses={404: {"description": "Not found"}},
)


# --------------------------------------------------------------------------- #
# Response Schemas
# --------------------------------------------------------------------------- #


class LockoutState(BaseModel):
    """Lockout block state."""

    model_config = ConfigDict(extra="ignore")

    active: bool
    ttl_seconds: int = 0
    level: str = ""


class RateLimitState(BaseModel):
    """Rate limit block state."""

    model_config = ConfigDict(extra="ignore")

    active: bool
    count: int = 0
    limit: int
    ttl_seconds: int = 0


class CaptchaState(BaseModel):
    """CAPTCHA requirement state."""

    model_config = ConfigDict(extra="ignore")

    active: bool


class BlocksState(BaseModel):
    """All block states for an account."""

    model_config = ConfigDict(extra="ignore")

    lockout: Optional[LockoutState] = None
    rate_limit_minute: Optional[RateLimitState] = None
    rate_limit_hour: Optional[RateLimitState] = None
    captcha_required: Optional[CaptchaState] = None


class BlockedAccount(BaseModel):
    """Blocked account information."""

    model_config = ConfigDict(extra="ignore")

    email: str
    blocks: BlocksState
    failure_count: int = 0


class ListAuthIssuesResponse(BaseModel):
    """Response for listing accounts with auth issues."""

    model_config = ConfigDict(extra="ignore")

    accounts: list[BlockedAccount]
    total: int
    scanned_at: str


class ClearBlocksRequest(BaseModel):
    """Request to clear auth blocks."""

    model_config = ConfigDict(extra="ignore")

    types: Optional[list[str]] = Field(
        default=None,
        description="Block types to clear: lockout, rate_limit, captcha, failures. If not specified, clears all.",
    )
    reason: Optional[str] = Field(
        default=None, description="Reason for clearing blocks (for audit)"
    )


class ClearBlocksResponse(BaseModel):
    """Response after clearing blocks."""

    model_config = ConfigDict(extra="ignore")

    email: str
    cleared: list[str]
    cleared_by: str
    cleared_at: str
    reason: Optional[str] = None


class SummaryStats(BaseModel):
    """Summary statistics for auth blocks."""

    model_config = ConfigDict(extra="ignore")

    total_blocked: int = 0
    locked_out: int = 0
    rate_limited: int = 0
    captcha_required: int = 0


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #


def _get_lockout_level(failures: int) -> str:
    """Determine lockout level based on failure count."""
    if failures >= 20:
        return "1hr"
    elif failures >= 15:
        return "30min"
    elif failures >= 10:
        return "5min"
    else:
        return "30sec"


async def _get_account_state(redis: Redis, email: str) -> BlockedAccount:
    """Build complete auth state for an account."""
    email_lower = email.lower()

    # Get all relevant TTLs and values
    lockout_ttl = await redis.ttl(f"login:lockout:{email_lower}")
    rate_min_ttl = await redis.ttl(f"login:minute:{email_lower}")
    rate_hour_ttl = await redis.ttl(f"login:hour:{email_lower}")

    failures_raw = await redis.get(f"login:failures:{email_lower}")
    failures = int(failures_raw) if failures_raw else 0

    rate_min_raw = await redis.get(f"login:minute:{email_lower}")
    rate_min_count = int(rate_min_raw) if rate_min_raw else 0

    rate_hour_raw = await redis.get(f"login:hour:{email_lower}")
    rate_hour_count = int(rate_hour_raw) if rate_hour_raw else 0

    # Build blocks state
    blocks = BlocksState(
        lockout=(
            LockoutState(
                active=True,
                ttl_seconds=max(0, lockout_ttl),
                level=_get_lockout_level(failures),
            )
            if lockout_ttl > 0
            else None
        ),
        rate_limit_minute=(
            RateLimitState(
                active=rate_min_count >= settings.login_attempts_per_minute,
                count=rate_min_count,
                limit=settings.login_attempts_per_minute,
                ttl_seconds=max(0, rate_min_ttl),
            )
            if rate_min_count > 0
            else None
        ),
        rate_limit_hour=(
            RateLimitState(
                active=rate_hour_count >= settings.login_attempts_per_hour,
                count=rate_hour_count,
                limit=settings.login_attempts_per_hour,
                ttl_seconds=max(0, rate_hour_ttl),
            )
            if rate_hour_count > 0
            else None
        ),
        captcha_required=(
            CaptchaState(active=True)
            if failures >= (settings.captcha_failure_threshold or 3)
            else None
        ),
    )

    return BlockedAccount(email=email_lower, blocks=blocks, failure_count=failures)


def _has_active_blocks(account: BlockedAccount, filter_type: Optional[str] = None) -> bool:
    """Check if account has active blocks matching the filter."""
    if filter_type is None:
        # Any active block counts
        return (
            (account.blocks.lockout is not None and account.blocks.lockout.active)
            or (
                account.blocks.rate_limit_minute is not None
                and account.blocks.rate_limit_minute.active
            )
            or (
                account.blocks.rate_limit_hour is not None and account.blocks.rate_limit_hour.active
            )
            or (
                account.blocks.captcha_required is not None
                and account.blocks.captcha_required.active
            )
            or account.failure_count >= 3  # Approaching lockout
        )

    if filter_type == "lockout":
        return account.blocks.lockout is not None and account.blocks.lockout.active
    if filter_type == "rate_limit":
        return (
            account.blocks.rate_limit_minute is not None and account.blocks.rate_limit_minute.active
        ) or (account.blocks.rate_limit_hour is not None and account.blocks.rate_limit_hour.active)
    if filter_type == "captcha":
        return (
            account.blocks.captcha_required is not None and account.blocks.captcha_required.active
        )

    return False


# --------------------------------------------------------------------------- #
# API Endpoints
# --------------------------------------------------------------------------- #


@router.get("", response_model=ListAuthIssuesResponse)
async def list_auth_issues(
    type: Optional[str] = Query(
        None, description="Filter by block type: lockout, rate_limit, captcha"
    ),
    email: Optional[str] = Query(None, description="Search by email (partial match)"),
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> ListAuthIssuesResponse:
    """
    List accounts with auth issues (blocked or approaching lockout).

    Requires ACCESS_MONITORING permission.

    Returns accounts that are:
    - Locked out (after 5+ failed attempts)
    - Rate limited (minute or hour)
    - Require CAPTCHA (after 3+ failures)
    - Approaching lockout (3+ failures)
    """
    redis = await get_async_redis_client()
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )

    blocked: list[BlockedAccount] = []
    seen_emails: set[str] = set()

    try:
        # Scan for lockout keys
        async for key in redis.scan_iter("login:lockout:*"):
            key_str = key if isinstance(key, str) else key.decode()
            account_email = key_str.split(":")[-1]

            if email and email.lower() not in account_email.lower():
                continue

            if account_email not in seen_emails:
                account_state = await _get_account_state(redis, account_email)
                if _has_active_blocks(account_state, type):
                    blocked.append(account_state)
                    seen_emails.add(account_email)

        # Also check for accounts with high failure counts but no lockout yet
        async for key in redis.scan_iter("login:failures:*"):
            key_str = key if isinstance(key, str) else key.decode()
            account_email = key_str.split(":")[-1]

            if email and email.lower() not in account_email.lower():
                continue

            if account_email not in seen_emails:
                failures_raw = await redis.get(key_str)
                failures = int(failures_raw) if failures_raw else 0
                if failures >= 3:  # Show accounts approaching lockout
                    account_state = await _get_account_state(redis, account_email)
                    if _has_active_blocks(account_state, type):
                        blocked.append(account_state)
                        seen_emails.add(account_email)

        # Sort by failure count descending
        blocked.sort(key=lambda x: x.failure_count, reverse=True)

    except Exception as e:
        logger.error(f"Failed to list blocked accounts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blocked accounts",
        ) from e

    return ListAuthIssuesResponse(
        accounts=blocked,
        total=len(blocked),
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/summary", response_model=SummaryStats)
async def get_summary_stats(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> SummaryStats:
    """
    Get summary statistics for auth blocks.

    Requires ACCESS_MONITORING permission.
    """
    redis = await get_async_redis_client()
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )

    stats = SummaryStats()
    seen_emails: set[str] = set()

    try:
        # Count lockouts
        async for key in redis.scan_iter("login:lockout:*"):
            key_str = key if isinstance(key, str) else key.decode()
            account_email = key_str.split(":")[-1]
            seen_emails.add(account_email)
            stats.locked_out += 1

        # Count failures (for CAPTCHA requirement)
        async for key in redis.scan_iter("login:failures:*"):
            key_str = key if isinstance(key, str) else key.decode()
            account_email = key_str.split(":")[-1]
            failures_raw = await redis.get(key_str)
            failures = int(failures_raw) if failures_raw else 0
            if failures >= (settings.captcha_failure_threshold or 3):
                stats.captcha_required += 1
                seen_emails.add(account_email)

        # Count rate limited (minute)
        async for key in redis.scan_iter("login:minute:*"):
            key_str = key if isinstance(key, str) else key.decode()
            account_email = key_str.split(":")[-1]
            count_raw = await redis.get(key_str)
            count = int(count_raw) if count_raw else 0
            if count >= settings.login_attempts_per_minute:
                stats.rate_limited += 1
                seen_emails.add(account_email)

        stats.total_blocked = len(seen_emails)

    except Exception as e:
        logger.error(f"Failed to get summary stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve summary stats",
        ) from e

    return stats


@router.get("/{email}", response_model=BlockedAccount)
async def get_account_state(
    email: str,
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING)),
) -> BlockedAccount:
    """
    Get detailed auth state for a specific account.

    Requires ACCESS_MONITORING permission.
    """
    redis = await get_async_redis_client()
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )

    try:
        state = await _get_account_state(redis, email)

        # Check if there's any state to show
        if (
            state.blocks.lockout is None
            and state.blocks.rate_limit_minute is None
            and state.blocks.rate_limit_hour is None
            and state.blocks.captcha_required is None
            and state.failure_count == 0
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No auth state found for this email",
            )

        return state

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get account state: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve account state",
        ) from e


@router.delete("/{email}", response_model=ClearBlocksResponse)
async def clear_account_blocks(
    email: str,
    request: Optional[ClearBlocksRequest] = None,
    current_user: User = Depends(require_permission(PermissionName.MANAGE_USERS)),
) -> ClearBlocksResponse:
    """
    Clear auth blocks for an account.

    Requires MANAGE_USERS permission.

    If no types specified, clears ALL blocks for the account.
    """
    redis = await get_async_redis_client()
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )

    email_lower = email.lower()
    types_to_clear = (
        request.types
        if request and request.types
        else ["lockout", "rate_limit", "captcha", "failures"]
    )
    reason = request.reason if request else None
    cleared: list[str] = []

    try:
        if "lockout" in types_to_clear:
            result = await redis.delete(f"login:lockout:{email_lower}")
            if result:
                cleared.append("lockout")

        if "rate_limit" in types_to_clear:
            result = await redis.delete(f"login:minute:{email_lower}")
            if result:
                cleared.append("rate_limit_minute")
            result = await redis.delete(f"login:hour:{email_lower}")
            if result:
                cleared.append("rate_limit_hour")

        if "captcha" in types_to_clear:
            # CAPTCHA state is derived from failure count, no separate key
            pass

        if "failures" in types_to_clear:
            result = await redis.delete(f"login:failures:{email_lower}")
            if result:
                cleared.append("failures")

        # Log the action
        logger.info(
            f"Auth blocks cleared: email={email_lower}, cleared={cleared}, "
            f"by={current_user.email}, reason={reason}"
        )

    except Exception as e:
        logger.error(f"Failed to clear blocks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear blocks",
        ) from e

    return ClearBlocksResponse(
        email=email_lower,
        cleared=cleared,
        cleared_by=current_user.email,
        cleared_at=datetime.now(timezone.utc).isoformat(),
        reason=reason,
    )
