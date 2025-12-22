# backend/app/routes/v1/referrals.py
"""
Referrals routes - API v1

Versioned referral endpoints under /api/v1/referrals.
All business logic delegated to ReferralService and ReferralCheckoutService.

Public endpoints (require beta access):
    GET /r/{slug}                        → Resolve referral slug (redirect)

Protected endpoints:
    POST /claim                          → Claim referral code
    GET /me                              → Get user's referral ledger
    POST /checkout/apply-referral        → Apply referral credit

Admin endpoints:
    GET /admin/config                    → Get referral config
    GET /admin/summary                   → Get referral summary
    GET /admin/health                    → Get referral health
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import List, Optional, cast
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from ...api.dependencies.auth import (
    get_current_active_user,
    get_current_active_user_optional,
)
from ...api.dependencies.services import (
    get_referral_checkout_service,
    get_referral_service,
)
from ...core.config import resolve_referrals_step, settings
from ...core.exceptions import ServiceException
from ...models.referrals import ReferralReward, RewardStatus
from ...models.user import User
from ...schemas.referrals import (
    AdminReferralsConfigOut,
    AdminReferralsHealthOut,
    AdminReferralsSummaryOut,
    CheckoutApplyRequest,
    CheckoutApplyResponse,
    ReferralClaimRequest,
    ReferralClaimResponse,
    ReferralErrorResponse,
    ReferralLedgerResponse,
    ReferralResolveResponse,
    RewardOut,
)
from ...services.referral_checkout_service import (
    ReferralCheckoutError,
    ReferralCheckoutService,
)
from ...services.referral_service import ReferralService

logger = logging.getLogger("referral.api.v1")

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["referrals-v1"])

# Admin router - separate for admin endpoints
admin_router = APIRouter(tags=["admin", "referrals-v1"])

# Public router for the slug redirect (no prefix)
public_router = APIRouter(tags=["referrals-v1"])

COOKIE_NAME = "instainstru_ref"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days
EXPIRY_NOTICE_DAYS = [14, 3]
REFERRALS_REASON_HEADER = "X-Referrals-Reason"


def _hash_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _set_referral_cookie(response: Response, code: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        code,
        max_age=COOKIE_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _accepts_json(accept_header: Optional[str]) -> bool:
    if not accept_header:
        return False
    accept = accept_header.lower()
    if "application/json" not in accept:
        return False
    if "text/html" in accept and accept.index("text/html") < accept.index("application/json"):
        return False
    return True


def _normalize_referral_landing_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return "/referral"

    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")

    if path.endswith("/referrals"):
        path = path[:-1]

    if not path.endswith("/referral"):
        path = f"{path}/referral" if path else "/referral"

    if not path.startswith("/"):
        path = f"/{path}"

    normalized = parsed._replace(path=path or "/referral")
    return urlunparse(normalized)


# --- Public Router: Slug Resolution ---


@public_router.get("/{slug}", response_model=ReferralResolveResponse)
async def resolve_referral_slug(
    slug: str,
    request: Request,
    response: Response,
    referral_service: ReferralService = Depends(get_referral_service),
) -> Response:
    """Resolve referral slug and redirect to landing page."""
    code_obj = await run_in_threadpool(referral_service.resolve_code, slug)
    if not code_obj:
        return HTMLResponse(
            "<html><body><h1>Invalid referral link</h1><p>Please check with your friend for an updated link.</p></body></html>",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    code_value = code_obj.code

    client_ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if not client_ip and request.client:
        client_ip = request.client.host or ""
    user_agent = request.headers.get("user-agent", "")
    device_fp = request.headers.get("x-device-fingerprint")
    channel = (
        request.query_params.get("utm_medium")
        or request.query_params.get("utm_source")
        or "unknown"
    )

    await run_in_threadpool(
        referral_service.record_click,
        code=code_value,
        device_fp_hash=_hash_value(device_fp),
        ip_hash=_hash_value(client_ip),
        ua_hash=_hash_value(user_agent),
        channel=channel,
        ts=datetime.now(timezone.utc),
    )

    landing_url = _normalize_referral_landing_url(settings.frontend_referral_landing_url)

    if _accepts_json(request.headers.get("accept")):
        _set_referral_cookie(response, code_value)
        return ReferralResolveResponse(ok=True, code=code_value, redirect=landing_url)

    redirect = RedirectResponse(landing_url, status_code=status.HTTP_302_FOUND)
    _set_referral_cookie(redirect, code_value)
    return redirect


# --- Protected Router: User Referral Operations ---


@router.post(
    "/claim",
    response_model=ReferralClaimResponse | ReferralErrorResponse,
)
async def claim_referral_code(
    response: Response,
    payload: ReferralClaimRequest = Body(...),
    current_user: Optional[User] = Depends(get_current_active_user_optional),
    referral_service: ReferralService = Depends(get_referral_service),
) -> Response:
    """Claim a referral code."""
    code_obj = await run_in_threadpool(referral_service.resolve_code, payload.code)
    if not code_obj:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ReferralErrorResponse(reason="not_found")

    code_value = code_obj.code
    _set_referral_cookie(response, code_value)

    if current_user is None:
        logger.info("referral.api.v1.claim.anonymous", extra={"code": code_value})
        return ReferralClaimResponse(attributed=False, reason="anonymous")

    if await run_in_threadpool(referral_service.has_attribution, current_user.id):
        response.status_code = status.HTTP_409_CONFLICT
        return ReferralErrorResponse(reason="already_attributed")

    attributed = await run_in_threadpool(
        referral_service.attribute_signup,
        referred_user_id=current_user.id,
        code=code_value,
        source="manual_claim",
        ts=datetime.now(timezone.utc),
    )
    if not attributed:
        response.status_code = status.HTTP_409_CONFLICT
        return ReferralErrorResponse(reason="already_attributed")

    logger.info(
        "referral.api.v1.claim.attributed",
        extra={"user_id": current_user.id, "code": code_value},
    )
    return ReferralClaimResponse(attributed=True, reason=None)


@router.get("/me", response_model=ReferralLedgerResponse)
async def get_my_referral_ledger(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    referral_service: ReferralService = Depends(get_referral_service),
) -> ReferralLedgerResponse:
    """Get current user's referral ledger with code, rewards, and share URL."""
    request_id = str(uuid4())
    issuance_step = resolve_referrals_step()
    logger.info(
        "referral.api.v1.ledger.start",
        extra={
            "request_id": request_id,
            "user_id": current_user.id,
            "referrals_step": issuance_step,
            "path": request.url.path,
        },
    )

    try:
        try:
            code_obj = await run_in_threadpool(
                referral_service.ensure_code_for_user, current_user.id
            )
        except ServiceException as exc:
            if exc.code == "REFERRAL_CODE_ISSUANCE_TIMEOUT":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "message": "Referral code issuance is temporarily unavailable",
                        "code": exc.code,
                    },
                    headers={REFERRALS_REASON_HEADER: "db_timeout(lock_timeout/statement_timeout)"},
                ) from exc
            raise exc.to_http_exception()

        if code_obj is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Referral codes are not available yet",
                    "code": "REFERRAL_CODES_DISABLED",
                },
                headers={REFERRALS_REASON_HEADER: f"issuance_disabled(step={issuance_step})"},
            )

        try:
            rewards_by_status = await run_in_threadpool(
                referral_service.get_rewards_by_status, user_id=current_user.id
            )
        except ServiceException as exc:
            raise exc.to_http_exception()

        def _to_reward_out(rewards: List[ReferralReward]) -> List[RewardOut]:
            return [
                RewardOut(
                    id=reward.id,
                    side=reward.side,
                    status=reward.status,
                    amount_cents=reward.amount_cents,
                    unlock_ts=reward.unlock_ts,
                    expire_ts=reward.expire_ts,
                    created_at=reward.created_at,
                )
                for reward in rewards
            ]

        slug = code_obj.vanity_slug or code_obj.code
        share_base = settings.frontend_url.rstrip("/")
        share_url = f"{share_base}/r/{slug}"

        return ReferralLedgerResponse(
            code=code_obj.code,
            share_url=share_url,
            pending=_to_reward_out(rewards_by_status[RewardStatus.PENDING]),
            unlocked=_to_reward_out(rewards_by_status[RewardStatus.UNLOCKED]),
            redeemed=_to_reward_out(rewards_by_status[RewardStatus.REDEEMED]),
            expiry_notice_days=EXPIRY_NOTICE_DAYS,
        )
    except HTTPException as http_exc:
        if http_exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            headers = dict(http_exc.headers or {})
            if REFERRALS_REASON_HEADER not in headers:
                headers[REFERRALS_REASON_HEADER] = "unexpected"
                raise HTTPException(
                    status_code=http_exc.status_code,
                    detail=http_exc.detail,
                    headers=headers,
                ) from http_exc
        raise


@router.post(
    "/checkout/apply-referral",
    response_model=CheckoutApplyResponse | ReferralErrorResponse,
)
async def apply_referral_credit(
    response: Response,
    payload: CheckoutApplyRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    checkout_service: ReferralCheckoutService = Depends(get_referral_checkout_service),
) -> Response:
    """Apply referral credit to a checkout order."""
    try:
        applied = await run_in_threadpool(
            checkout_service.apply_student_credit,
            user_id=current_user.id,
            order_id=str(payload.order_id),
        )
    except ReferralCheckoutError as exc:
        response.status_code = exc.status_code
        return ReferralErrorResponse(reason=exc.reason)

    return CheckoutApplyResponse(applied_cents=applied)


# --- Admin Router: Admin Operations ---


@admin_router.get("/config", response_model=AdminReferralsConfigOut)
async def get_referral_config(
    current_user: User = Depends(get_current_active_user),
    referral_service: ReferralService = Depends(get_referral_service),
) -> AdminReferralsConfigOut:
    """Get referral configuration (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return cast(AdminReferralsConfigOut, await run_in_threadpool(referral_service.get_admin_config))


@admin_router.get("/summary", response_model=AdminReferralsSummaryOut)
async def get_referral_summary(
    current_user: User = Depends(get_current_active_user),
    referral_service: ReferralService = Depends(get_referral_service),
) -> AdminReferralsSummaryOut:
    """Get referral summary statistics (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return cast(
        AdminReferralsSummaryOut, await run_in_threadpool(referral_service.get_admin_summary)
    )


@admin_router.get("/health", response_model=AdminReferralsHealthOut)
async def get_referral_health(
    current_user: User = Depends(get_current_active_user),
    referral_service: ReferralService = Depends(get_referral_service),
) -> AdminReferralsHealthOut:
    """Get referral system health (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return cast(AdminReferralsHealthOut, await run_in_threadpool(referral_service.get_admin_health))


__all__ = ["router", "admin_router", "public_router"]
