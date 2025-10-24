"""Referral domain services for Instainstru Park Slope beta."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Dict, Iterable, List, Optional, cast
from uuid import UUID

from sqlalchemy.orm import Session
import ulid

from app.core.exceptions import RepositoryException, ServiceException
from app.events.referral_events import (
    emit_first_booking_completed,
    emit_referral_code_issued,
    emit_referral_link_clicked,
    emit_referred_signup,
    emit_reward_pending,
    emit_reward_voided,
)
from app.models.referrals import ReferralCode, ReferralReward, RewardStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.repositories.referral_repository import (
    ReferralAttributionRepository,
    ReferralClickRepository,
    ReferralCodeRepository,
    ReferralRewardRepository,
)
from app.schemas.referrals import (
    AdminReferralsConfigOut,
    AdminReferralsHealthOut,
    AdminReferralsSummaryOut,
    TopReferrerOut,
)
from app.services import referral_fraud
from app.services.base import BaseService
from app.services.referral_unlocker import get_last_success_timestamp
from app.services.referrals_config_service import ReferralsEffectiveConfig, get_effective_config
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

UserID = str | UUID


class ReferralService(BaseService):
    """High-level referral operations with idempotent semantics."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.referral_code_repo: ReferralCodeRepository = (
            RepositoryFactory.create_referral_code_repository(db)
        )
        self.referral_click_repo: ReferralClickRepository = (
            RepositoryFactory.create_referral_click_repository(db)
        )
        self.referral_attribution_repo: ReferralAttributionRepository = (
            RepositoryFactory.create_referral_attribution_repository(db)
        )
        self.referral_reward_repo: ReferralRewardRepository = (
            RepositoryFactory.create_referral_reward_repository(db)
        )
        self.booking_repo: BookingRepository = RepositoryFactory.create_booking_repository(db)
        self.referral_limit_repo = RepositoryFactory.create_referral_limit_repository(db)

    @staticmethod
    def _normalize_user_id(user_id: UserID) -> str:
        return str(user_id)

    @staticmethod
    def _ensure_timezone(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _coerce_user_uuid(user_id: str) -> UUID:
        """Best-effort conversion of ULID/UUID strings to UUID objects."""

        try:
            ulid_uuid = ulid.ULID.from_str(user_id).to_uuid()
            return cast(UUID, ulid_uuid)
        except ValueError:
            return UUID(user_id)

    @BaseService.measure_operation("referrals.issue_code")
    def issue_code(
        self, *, referrer_user_id: UserID, channel: str | None = "self_service"
    ) -> ReferralCode:
        """Return an existing active code or create a new one for the referrer."""

        self._assert_enabled()
        owner_id = self._normalize_user_id(referrer_user_id)

        with self.transaction():
            code = self.referral_code_repo.get_or_create_for_user(owner_id)

        emit_referral_code_issued(user_id=owner_id, code=code.code, channel=channel)
        return code

    @BaseService.measure_operation("referrals.resolve_code")
    def resolve_code(self, identifier: str) -> Optional[ReferralCode]:
        code = self.referral_code_repo.get_by_slug(identifier)
        if code:
            return code
        return self.referral_code_repo.get_by_code(identifier)

    @BaseService.measure_operation("referrals.ensure_code_for_user")
    def ensure_code_for_user(self, user_id: str) -> Optional[ReferralCode]:
        step = int(os.getenv("REFERRALS_UNSAFE_STEP", "0") or 0)

        existing = self.referral_code_repo.get_active_for_user(user_id)
        if existing:
            return existing

        if step < 2:
            return None

        try:
            with self.transaction():
                code = self.referral_code_repo.get_or_create_for_user(user_id)
            return code
        except RepositoryException as exc:
            raise ServiceException(
                "Referral code issuance is temporarily unavailable",
                code="REFERRAL_CODE_ISSUANCE_TIMEOUT",
            ) from exc

    @BaseService.measure_operation("referrals.has_attribution")
    def has_attribution(self, user_id: str) -> bool:
        return self.referral_attribution_repo.exists_for_user(user_id)

    @BaseService.measure_operation("referrals.record_click")
    def record_click(
        self,
        *,
        code: str,
        device_fp_hash: str | None = None,
        ip_hash: str | None = None,
        ua_hash: str | None = None,
        channel: str | None = None,
        ts: datetime | None = None,
    ) -> None:
        """Record a referral link click."""

        code_row = self.referral_code_repo.get_by_code(code)
        if not code_row:
            logger.warning("Referral click ignored: code %s not active", code)
            return

        click_ts = self._ensure_timezone(ts or datetime.now(timezone.utc))
        with self.transaction():
            self.referral_click_repo.create(
                code_id=code_row.id,
                device_fp_hash=device_fp_hash,
                ip_hash=ip_hash,
                ua_hash=ua_hash,
                channel=channel,
                ts=click_ts,
            )

        emit_referral_link_clicked(
            code=code_row.code,
            ts=click_ts,
            device_fp_hash=device_fp_hash,
            ip_hash=ip_hash,
            channel=channel,
        )

    @BaseService.measure_operation("referrals.attribute_signup")
    def attribute_signup(
        self,
        *,
        referred_user_id: UserID,
        code: str,
        source: str,
        ts: datetime,
        device_fp_hash: str | None = None,
        ip_hash: str | None = None,
        ua_hash: str | None = None,
    ) -> bool:
        """Attribute a new signup to a referral code."""

        self._assert_enabled()
        user_id = self._normalize_user_id(referred_user_id)
        attribution_ts = self._ensure_timezone(ts)

        with self.transaction():
            if self.referral_attribution_repo.exists_for_user(user_id):
                return False

            code_row = self.referral_code_repo.get_by_code(code)
            if not code_row:
                logger.warning("Signup attribution failed: code %s not active", code)
                return False

            created = self.referral_attribution_repo.create_if_absent(
                code_id=code_row.id,
                referred_user_id=user_id,
                source=source,
                ts=attribution_ts,
            )
            if not created:
                return False

            if device_fp_hash or ip_hash or ua_hash:
                self.referral_click_repo.create(
                    code_id=code_row.id,
                    device_fp_hash=device_fp_hash,
                    ip_hash=ip_hash,
                    ua_hash=ua_hash,
                    channel="signup",
                    ts=attribution_ts,
                )

        emit_referred_signup(referred_user_id=user_id, code=code_row.code)
        return True

    @BaseService.measure_operation("referrals.on_first_booking_completed")
    def on_first_booking_completed(
        self,
        *,
        user_id: UserID,
        booking_id: UserID,
        amount_cents: int,
        completed_at: datetime,
    ) -> None:
        """Handle first booking completion for a referred student."""

        config = self._assert_enabled()
        student_id = self._normalize_user_id(user_id)
        booking_id_str = self._normalize_user_id(booking_id)
        completed_ts = self._ensure_timezone(completed_at)

        emit_first_booking_completed(
            booking_id=booking_id_str,
            user_id=student_id,
            amount_cents=amount_cents,
        )

        with self.transaction():
            attribution = self.referral_attribution_repo.get_by_referred_user_id(
                student_id, for_update=True
            )
            if not attribution:
                logger.info("No referral attribution found for user %s", student_id)
                return

            code_row = self.referral_code_repo.get_by_id(attribution.code_id, for_update=True)
            if not code_row:
                logger.warning("Dangling referral attribution %s without code", attribution.id)
                return

            inviter_id = code_row.referrer_user_id

            if self._beyond_student_cap(inviter_id, config):
                logger.warning("Referrer %s reached student reward cap", inviter_id)
                return

            fingerprints = self.referral_click_repo.get_fingerprint_snapshot(
                code_row.id, attribution.ts
            )

            self_referral = referral_fraud.is_self_referral(
                click_device_fp_hash=fingerprints.get("click_device"),
                click_ip_hash=fingerprints.get("click_ip"),
                signup_device_fp_hash=fingerprints.get("signup_device"),
                signup_ip_hash=fingerprints.get("signup_ip"),
            )

            unlock_ts = completed_ts + timedelta(days=config["hold_days"])
            expire_ts = self._add_months(unlock_ts, config["expiry_months"])
            booking_prefix = booking_id_str.replace("-", "")[:12]

            student_reward, referrer_reward = self.referral_reward_repo.create_student_pair(
                student_user_id=student_id,
                inviter_user_id=inviter_id,
                amount_cents=config["student_amount_cents"],
                unlock_ts=unlock_ts,
                expire_ts=expire_ts,
                rule_version_student=f"S1-{booking_prefix}",
                rule_version_referrer=f"S2-{booking_prefix}",
            )

            pending_rewards = [student_reward, referrer_reward]
            for reward in pending_rewards:
                if reward.status == RewardStatus.PENDING:
                    emit_reward_pending(
                        reward_id=str(reward.id),
                        side=reward.side.value,
                        referrer_user_id=reward.referrer_user_id,
                        referred_user_id=reward.referred_user_id,
                        amount_cents=reward.amount_cents,
                        unlock_eta=reward.unlock_ts or unlock_ts,
                    )

            if self_referral:
                self._void_rewards((student_reward, referrer_reward), reason="self_referral")
                return

            if self._is_velocity_abuse(inviter_id):
                self._void_rewards((student_reward, referrer_reward), reason="velocity")

    @BaseService.measure_operation("referrals.on_instructor_lesson_completed")
    def on_instructor_lesson_completed(
        self,
        *,
        instructor_user_id: UserID,
        lesson_id: UserID,
        completed_at: datetime,
    ) -> None:
        """Gate instructor-side rewards on rolling lesson completions."""

        config = self._assert_enabled()
        instructor_id = self._normalize_user_id(instructor_user_id)
        completed_ts = self._ensure_timezone(completed_at)

        with self.transaction():
            attribution = self.referral_attribution_repo.get_by_referred_user_id(
                instructor_id, for_update=True
            )
            if not attribution:
                return

            code_row = self.referral_code_repo.get_by_id(attribution.code_id, for_update=True)
            if not code_row:
                return

            inviter_id = code_row.referrer_user_id
            window_start = completed_ts - referral_fraud.referral_window()
            lesson_count = self.booking_repo.count_completed_lessons(
                instructor_user_id=instructor_id,
                window_start=window_start,
                window_end=completed_ts,
            )
            if lesson_count < 3:
                return

            unlock_ts = completed_ts + timedelta(days=config["hold_days"])
            expire_ts = self._add_months(unlock_ts, config["expiry_months"])
            lesson_prefix = self._normalize_user_id(lesson_id).replace("-", "")[:12]

            reward = self.referral_reward_repo.create_instructor_referrer_reward(
                referrer_user_id=inviter_id,
                referred_user_id=instructor_id,
                amount_cents=config["instructor_amount_cents"],
                unlock_ts=unlock_ts,
                expire_ts=expire_ts,
                rule_version=f"I1-{lesson_prefix}",
            )

            if reward.status == RewardStatus.PENDING:
                emit_reward_pending(
                    reward_id=str(reward.id),
                    side=reward.side.value,
                    referrer_user_id=reward.referrer_user_id,
                    referred_user_id=reward.referred_user_id,
                    amount_cents=reward.amount_cents,
                    unlock_eta=unlock_ts,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @BaseService.measure_operation("referrals.get_rewards_by_status")
    def get_rewards_by_status(
        self, *, user_id: str, limit: int = 50
    ) -> Dict[RewardStatus, List[ReferralReward]]:
        return {
            RewardStatus.PENDING: self.referral_reward_repo.list_by_user_and_status(
                user_id=user_id, status=RewardStatus.PENDING, limit=limit
            ),
            RewardStatus.UNLOCKED: self.referral_reward_repo.list_by_user_and_status(
                user_id=user_id, status=RewardStatus.UNLOCKED, limit=limit
            ),
            RewardStatus.REDEEMED: self.referral_reward_repo.list_by_user_and_status(
                user_id=user_id, status=RewardStatus.REDEEMED, limit=limit
            ),
        }

    @BaseService.measure_operation("referrals.admin.config")
    def get_admin_config(self) -> AdminReferralsConfigOut:
        """Return program configuration for admin dashboards."""

        config = self._get_config()
        return AdminReferralsConfigOut(
            student_amount_cents=config["student_amount_cents"],
            instructor_amount_cents=config["instructor_amount_cents"],
            min_basket_cents=config["min_basket_cents"],
            hold_days=config["hold_days"],
            expiry_months=config["expiry_months"],
            global_cap=config["student_global_cap"],
            version=config["version"],
            source=config["source"],
            flags={"enabled": bool(config["enabled"])},
        )

    @BaseService.measure_operation("referrals.admin.summary")
    def get_admin_summary(self) -> AdminReferralsSummaryOut:
        """Return aggregated referral metrics for admins."""

        counts = self.referral_reward_repo.counts_by_status()
        config = self._get_config()
        cap = config["student_global_cap"]
        total_student_rewards = self.referral_reward_repo.total_student_rewards()
        cap_utilization_percent = 0.0
        if cap:
            capped_total = min(total_student_rewards, cap)
            cap_utilization_percent = round((capped_total / cap) * 100, 2)

        top_referrer_rows = self.referral_reward_repo.top_referrers(limit=20)
        top_referrers: List[TopReferrerOut] = []
        for referrer_id, count, code in top_referrer_rows:
            try:
                user_uuid = self._coerce_user_uuid(referrer_id)
            except ValueError:
                logger.warning("Unable to coerce referrer id %s to UUID", referrer_id)
                continue
            top_referrers.append(TopReferrerOut(user_id=user_uuid, count=count, code=code))

        window_start = datetime.now(timezone.utc) - timedelta(hours=24)
        clicks_24h = self.referral_click_repo.clicks_since(window_start)
        attributions_24h = self.referral_attribution_repo.attributions_since(window_start)

        return AdminReferralsSummaryOut(
            counts_by_status=counts,
            cap_utilization_percent=cap_utilization_percent,
            top_referrers=top_referrers,
            clicks_24h=clicks_24h,
            attributions_24h=attributions_24h,
        )

    @BaseService.measure_operation("referrals.admin.health")
    def get_admin_health(self) -> AdminReferralsHealthOut:
        """Return unlocker worker health and reward backlog metrics."""

        now = datetime.now(timezone.utc)
        counts = self.referral_reward_repo.counts_by_status()
        backlog_pending_due = self.referral_reward_repo.count_pending_due(now)

        last_run_ts = get_last_success_timestamp()
        last_run_age_s: int | None = None
        if last_run_ts is not None:
            last_run_age_s = max(0, int((now - last_run_ts).total_seconds()))
            if last_run_age_s > 1800:
                logger.warning("unlocker.warn.no_recent_runs", extra={"age_s": last_run_age_s})

        pending_total = counts.get(RewardStatus.PENDING.value, 0)
        unlocked_total = counts.get(RewardStatus.UNLOCKED.value, 0)
        void_total = counts.get(RewardStatus.VOID.value, 0)

        workers: List[str] = []
        workers_alive = 0
        try:
            responses = celery_app.control.ping(timeout=1) or []
            worker_names: List[str] = []
            for response in responses:
                if isinstance(response, dict):
                    worker_names.extend(response.keys())
            workers = sorted(set(worker_names))
            workers_alive = len(workers)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Celery ping failed during referrals admin health check", exc_info=exc)

        return AdminReferralsHealthOut(
            workers_alive=workers_alive,
            workers=workers,
            backlog_pending_due=backlog_pending_due,
            pending_total=pending_total,
            unlocked_total=unlocked_total,
            void_total=void_total,
            last_run_age_s=last_run_age_s,
        )

    def _assert_enabled(self) -> ReferralsEffectiveConfig:
        config = get_effective_config(self.db)
        if not config["enabled"]:
            raise RuntimeError("Referral program currently disabled")
        return config

    def _get_config(self) -> ReferralsEffectiveConfig:
        return get_effective_config(self.db)

    def _add_months(self, base: datetime, months: int) -> datetime:
        year = base.year + (base.month - 1 + months) // 12
        month = (base.month - 1 + months) % 12 + 1
        day = min(base.day, self._days_in_month(year, month))
        return base.replace(year=year, month=month, day=day)

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        return calendar.monthrange(year, month)[1]

    def _beyond_student_cap(
        self,
        referrer_user_id: str,
        config: ReferralsEffectiveConfig | None = None,
    ) -> bool:
        total: int = self.referral_reward_repo.count_student_rewards_for_cap(referrer_user_id)
        cfg = config or self._get_config()
        cap = cfg["student_global_cap"]
        return total >= cap

    def _is_velocity_abuse(self, referrer_user_id: str) -> bool:
        now = datetime.now(timezone.utc)
        day_floor = now - timedelta(days=1)
        week_floor = now - timedelta(days=7)
        daily, weekly = self.referral_attribution_repo.velocity_counts(
            referrer_user_id, day_floor, week_floor
        )
        flagged = bool(referral_fraud.is_velocity_abuse(daily_count=daily, weekly_count=weekly))
        config = self._get_config()
        trust_score = -1 if flagged else 0
        self.referral_limit_repo.upsert(
            user_id=referrer_user_id,
            daily_ok=daily,
            weekly_ok=weekly,
            month_cap=config["student_global_cap"],
            trust_score=trust_score,
            last_reviewed_at=now,
        )
        return flagged

    def _void_rewards(self, rewards: Iterable[ReferralReward], *, reason: str) -> None:
        reward_ids = [reward.id for reward in rewards]
        self.referral_reward_repo.void_rewards(reward_ids)
        for reward_id in reward_ids:
            emit_reward_voided(reward_id=str(reward_id), reason=reason)
