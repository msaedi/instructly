"""Instructor referral program API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_active_user
from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.core.config import settings
from app.core.exceptions import ServiceException
from app.database import get_db
from app.models.referrals import ReferralCode
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.repositories.referral_repository import ReferralRewardRepository
from app.services.config_service import ConfigService
from app.services.referral_service import ReferralService
from app.services.referrals_config_service import get_effective_config
from app.utils.privacy import format_last_initial
from app.utils.url_validation import is_allowed_origin, origin_from_header

router = APIRouter(tags=["instructor-referrals-v1"])


class ReferralStatsResponse(BaseModel):
    """Stats for instructor's referral activity."""

    model_config = ConfigDict(from_attributes=True)

    referral_code: str
    referral_link: str
    total_referred: int
    pending_payouts: int
    completed_payouts: int
    total_earned_cents: int
    is_founding_phase: bool
    founding_spots_remaining: int
    current_bonus_cents: int


class ReferredInstructorInfo(BaseModel):
    """Info about an instructor this user referred."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_initial: str
    referred_at: datetime
    is_live: bool
    went_live_at: Optional[datetime] = None
    first_lesson_completed_at: Optional[datetime] = None
    payout_status: str
    payout_amount_cents: Optional[int] = None


class ReferredInstructorsResponse(BaseModel):
    """List of instructors referred by current user."""

    model_config = ConfigDict(from_attributes=True)

    instructors: list[ReferredInstructorInfo]
    total_count: int


class PopupDataResponse(BaseModel):
    """Data for the one-time referral popup after go-live."""

    model_config = ConfigDict(from_attributes=True)

    is_founding_phase: bool
    bonus_amount_cents: int
    founding_spots_remaining: int
    referral_code: str
    referral_link: str


class FoundingStatusResponse(BaseModel):
    """Public founding phase status."""

    model_config = ConfigDict(from_attributes=True)

    is_founding_phase: bool
    total_founding_spots: int
    spots_filled: int
    spots_remaining: int


class ReferralDashboardRewardItem(BaseModel):
    """Normalized reward row for the instructor referrals dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    referral_type: Literal["student", "instructor"]
    referee_first_name: str
    referee_last_initial: str
    amount_cents: int
    date: datetime
    payout_status: Optional[str] = None
    failure_reason: Optional[str] = None


class ReferralDashboardRewardsResponse(BaseModel):
    """Reward groups for instructor referrals dashboard tabs."""

    model_config = ConfigDict(from_attributes=True)

    pending: list[ReferralDashboardRewardItem]
    unlocked: list[ReferralDashboardRewardItem]
    redeemed: list[ReferralDashboardRewardItem]


class ReferralDashboardResponse(BaseModel):
    """Page-ready instructor referrals dashboard payload."""

    model_config = ConfigDict(from_attributes=True)

    referral_code: str
    referral_link: str
    instructor_amount_cents: int
    student_amount_cents: int
    total_referred: int
    pending_payouts: int
    total_earned_cents: int
    rewards: ReferralDashboardRewardsResponse


def _resolve_referral_base(request: Request | None = None) -> str:
    """Resolve referral link base origin.

    In local-like modes, prefer request-derived frontend origins so localhost and
    beta-local both produce matching links for the current browser origin.
    """

    configured_frontend = (settings.frontend_url or "").strip()
    local_beta_base = (settings.local_beta_frontend_origin or "").strip()
    mode = (settings.site_mode or "").strip().lower()

    # Hosted-like modes always use configured frontend origin.
    if mode not in {"local", "beta-local"}:
        return configured_frontend or local_beta_base

    candidates: list[str] = []

    if request is not None:
        request_origin = origin_from_header(request.headers.get("origin")) or origin_from_header(
            request.headers.get("referer")
        )
        if request_origin and is_allowed_origin(request_origin):
            candidates.append(request_origin)

    if local_beta_base and is_allowed_origin(local_beta_base):
        candidates.append(local_beta_base.rstrip("/"))
    if configured_frontend and is_allowed_origin(configured_frontend):
        candidates.append(configured_frontend.rstrip("/"))

    # Last-resort non-empty fallback for local dev.
    if local_beta_base:
        candidates.append(local_beta_base.rstrip("/"))
    if configured_frontend:
        candidates.append(configured_frontend.rstrip("/"))

    return candidates[0] if candidates else ""


def _get_referral_link(
    code: str,
    vanity_slug: Optional[str] = None,
    *,
    request: Request | None = None,
) -> str:
    slug = vanity_slug or code
    base = _resolve_referral_base(request)
    return f"{base.rstrip('/')}/r/{slug}" if base else f"/r/{slug}"


def _determine_payout_status(
    is_live: bool,
    first_lesson_completed_at: Optional[datetime],
    payout_status: Optional[str],
) -> str:
    if not is_live:
        return "pending_live"
    if not first_lesson_completed_at:
        return "pending_lesson"
    if payout_status == "completed":
        return "paid"
    if payout_status == "failed":
        return "failed"
    return "pending_transfer"


def _get_standard_instructor_bonus_cents(config: dict[str, object]) -> int:
    raw_value = config.get(
        "instructor_standard_bonus_cents", config.get("instructor_amount_cents", 5000)
    )
    return _coerce_int(raw_value, default=5000)


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _build_dashboard_reward_item(
    *,
    reward_id: str,
    referral_type: Literal["student", "instructor"],
    first_name: str,
    last_name: str,
    amount_cents: int,
    date: datetime,
    payout_status: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> ReferralDashboardRewardItem:
    return ReferralDashboardRewardItem(
        id=reward_id,
        referral_type=referral_type,
        referee_first_name=first_name,
        referee_last_initial=format_last_initial(last_name, with_period=True),
        amount_cents=amount_cents,
        date=date,
        payout_status=payout_status,
        failure_reason=failure_reason,
    )


def _resolve_founding_info(db: Session) -> tuple[int, int, bool]:
    instructor_repo = InstructorProfileRepository(db)
    config_service = ConfigService(db)

    pricing_config, _ = config_service.get_pricing_config()
    cap_default = PRICING_DEFAULTS["founding_instructor_cap"]
    cap_raw = pricing_config.get("founding_instructor_cap", cap_default)
    try:
        cap = int(cap_raw)
    except (TypeError, ValueError):
        cap = int(cap_default)

    founding_count = instructor_repo.count_founding_instructors()
    is_founding = founding_count < cap
    return cap, founding_count, is_founding


async def _require_referral_code(referral_service: ReferralService, user_id: str) -> ReferralCode:
    try:
        code = cast(
            Optional[ReferralCode],
            await run_in_threadpool(referral_service.ensure_code_for_user, user_id),
        )
    except ServiceException as exc:
        if exc.code == "REFERRAL_CODE_ISSUANCE_TIMEOUT":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Referral code issuance is temporarily unavailable",
                    "code": exc.code,
                },
            ) from exc
        raise exc.to_http_exception() from exc

    if code is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Referral codes are not available yet",
                "code": "REFERRAL_CODES_DISABLED",
            },
        )
    return code


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReferralStatsResponse:
    """Get current instructor's referral stats."""

    instructor_repo = InstructorProfileRepository(db)
    instructor_profile = await run_in_threadpool(instructor_repo.get_by_user_id, current_user.id)
    if not instructor_profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access referral stats",
        )

    referral_service = ReferralService(db)
    referral_repo = ReferralRewardRepository(db)
    config = await run_in_threadpool(get_effective_config, db)

    code = await _require_referral_code(referral_service, current_user.id)

    pending_payouts = await run_in_threadpool(
        referral_repo.count_referrer_payouts_by_status,
        current_user.id,
        status="pending",
    )
    completed_payouts = await run_in_threadpool(
        referral_repo.count_referrer_payouts_by_status,
        current_user.id,
        status="completed",
    )
    total_earned = await run_in_threadpool(
        referral_repo.sum_referrer_completed_payouts, current_user.id
    )
    total_referred = await run_in_threadpool(
        referral_repo.count_referred_instructors_by_referrer, current_user.id
    )

    cap, founding_count, is_founding = await run_in_threadpool(_resolve_founding_info, db)
    current_bonus = (
        _coerce_int(config.get("instructor_founding_bonus_cents", 7500), default=7500)
        if is_founding
        else _get_standard_instructor_bonus_cents(config)
    )

    return ReferralStatsResponse(
        referral_code=code.code,
        referral_link=_get_referral_link(code.code, code.vanity_slug, request=request),
        total_referred=total_referred,
        pending_payouts=pending_payouts,
        completed_payouts=completed_payouts,
        total_earned_cents=total_earned,
        is_founding_phase=is_founding,
        founding_spots_remaining=max(0, cap - founding_count),
        current_bonus_cents=current_bonus,
    )


@router.get("/dashboard", response_model=ReferralDashboardResponse)
async def get_referral_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReferralDashboardResponse:
    """Get a page-ready dashboard payload for instructor referrals."""

    instructor_repo = InstructorProfileRepository(db)
    instructor_profile = await run_in_threadpool(instructor_repo.get_by_user_id, current_user.id)
    if not instructor_profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access referral data",
        )

    referral_service = ReferralService(db)
    referral_repo = ReferralRewardRepository(db)
    config = await run_in_threadpool(get_effective_config, db)
    code = await _require_referral_code(referral_service, current_user.id)

    instructor_amount_cents = _get_standard_instructor_bonus_cents(config)
    student_amount_cents = _coerce_int(config.get("student_amount_cents", 2000), default=2000)
    dashboard_rows = await run_in_threadpool(
        referral_repo.list_referrer_dashboard_rows,
        current_user.id,
    )

    pending_items: list[ReferralDashboardRewardItem] = []
    unlocked_items: list[ReferralDashboardRewardItem] = []
    redeemed_items: list[ReferralDashboardRewardItem] = []
    total_earned_cents = 0

    for row in dashboard_rows:
        referral_type = cast(Literal["student", "instructor"], row["referral_type"])
        amount_cents = int(
            row.get("payout_amount_cents")
            or (instructor_amount_cents if referral_type == "instructor" else student_amount_cents)
        )
        payout_status = cast(Optional[str], row.get("stripe_transfer_status"))
        first_lesson_completed_at = cast(Optional[datetime], row.get("first_lesson_completed_at"))
        referred_at = cast(datetime, row["referred_at"])
        payout_created_at = cast(Optional[datetime], row.get("payout_created_at"))
        transferred_at = cast(Optional[datetime], row.get("transferred_at"))
        failure_reason = cast(Optional[str], row.get("failure_reason"))
        reward_id = cast(str, row.get("payout_id") or row["attribution_id"])
        first_name = cast(str, row["first_name"])
        last_name = cast(str, row.get("last_name") or "")

        if payout_status == "completed":
            redeemed_items.append(
                _build_dashboard_reward_item(
                    reward_id=reward_id,
                    referral_type=referral_type,
                    first_name=first_name,
                    last_name=last_name,
                    amount_cents=amount_cents,
                    date=transferred_at
                    or payout_created_at
                    or first_lesson_completed_at
                    or referred_at,
                    payout_status="completed",
                )
            )
            total_earned_cents += amount_cents
            continue

        if first_lesson_completed_at is not None or payout_status in {"pending", "failed"}:
            unlocked_items.append(
                _build_dashboard_reward_item(
                    reward_id=reward_id,
                    referral_type=referral_type,
                    first_name=first_name,
                    last_name=last_name,
                    amount_cents=amount_cents,
                    date=payout_created_at or first_lesson_completed_at or referred_at,
                    payout_status=payout_status or "pending",
                    failure_reason=failure_reason,
                )
            )
            continue

        pending_items.append(
            _build_dashboard_reward_item(
                reward_id=reward_id,
                referral_type=referral_type,
                first_name=first_name,
                last_name=last_name,
                amount_cents=amount_cents,
                date=referred_at,
            )
        )

    return ReferralDashboardResponse(
        referral_code=code.code,
        referral_link=_get_referral_link(code.code, code.vanity_slug, request=request),
        instructor_amount_cents=instructor_amount_cents,
        student_amount_cents=student_amount_cents,
        total_referred=len(dashboard_rows),
        pending_payouts=len(pending_items) + len(unlocked_items),
        total_earned_cents=total_earned_cents,
        rewards=ReferralDashboardRewardsResponse(
            pending=pending_items,
            unlocked=unlocked_items,
            redeemed=redeemed_items,
        ),
    )


@router.get("/referred", response_model=ReferredInstructorsResponse)
async def get_referred_instructors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReferredInstructorsResponse:
    """Get list of instructors referred by the current user."""

    instructor_repo = InstructorProfileRepository(db)
    instructor_profile = await run_in_threadpool(instructor_repo.get_by_user_id, current_user.id)
    if not instructor_profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access referral data",
        )

    referral_repo = ReferralRewardRepository(db)

    referred_data = await run_in_threadpool(
        referral_repo.get_referred_instructors_with_payout_status,
        referrer_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    total_count = await run_in_threadpool(
        referral_repo.count_referred_instructors_by_referrer, current_user.id
    )

    instructors: list[ReferredInstructorInfo] = []
    for data in referred_data:
        payout_status = _determine_payout_status(
            is_live=data.get("is_live", False),
            first_lesson_completed_at=data.get("first_lesson_completed_at"),
            payout_status=data.get("stripe_transfer_status"),
        )

        last_name = data.get("last_name") or ""
        instructors.append(
            ReferredInstructorInfo(
                id=data["user_id"],
                first_name=data["first_name"],
                last_initial=format_last_initial(last_name, with_period=True),
                referred_at=data["referred_at"],
                is_live=bool(data.get("is_live", False)),
                went_live_at=data.get("went_live_at"),
                first_lesson_completed_at=data.get("first_lesson_completed_at"),
                payout_status=payout_status,
                payout_amount_cents=data.get("payout_amount_cents"),
            )
        )

    return ReferredInstructorsResponse(instructors=instructors, total_count=total_count)


@router.get("/popup-data", response_model=PopupDataResponse)
async def get_popup_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PopupDataResponse:
    """Get data for the referral popup shown after go-live."""

    instructor_repo = InstructorProfileRepository(db)
    instructor_profile = await run_in_threadpool(instructor_repo.get_by_user_id, current_user.id)
    if not instructor_profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access referral data",
        )

    referral_service = ReferralService(db)
    config = await run_in_threadpool(get_effective_config, db)

    code = await _require_referral_code(referral_service, current_user.id)

    cap, founding_count, is_founding = await run_in_threadpool(_resolve_founding_info, db)
    current_bonus = (
        _coerce_int(config.get("instructor_founding_bonus_cents", 7500), default=7500)
        if is_founding
        else _coerce_int(config.get("instructor_standard_bonus_cents", 5000), default=5000)
    )

    return PopupDataResponse(
        is_founding_phase=is_founding,
        bonus_amount_cents=current_bonus,
        founding_spots_remaining=max(0, cap - founding_count),
        referral_code=code.code,
        referral_link=_get_referral_link(code.code, code.vanity_slug, request=request),
    )


@router.get("/founding-status", response_model=FoundingStatusResponse)
async def get_founding_status(db: Session = Depends(get_db)) -> FoundingStatusResponse:
    """Public endpoint to check founding phase status."""

    cap, founding_count, is_founding = await run_in_threadpool(_resolve_founding_info, db)
    return FoundingStatusResponse(
        is_founding_phase=is_founding,
        total_founding_spots=cap,
        spots_filled=founding_count,
        spots_remaining=max(0, cap - founding_count),
    )
