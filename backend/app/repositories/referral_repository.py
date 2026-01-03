"""Referral repositories supporting the referral domain services."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, cast
import uuid
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.referrals import (
    InstructorReferralPayout,
    ReferralAttribution,
    ReferralClick,
    ReferralCode,
    ReferralCodeStatus,
    ReferralLimit,
    ReferralReward,
    RewardSide,
    RewardStatus,
    WalletTransaction,
    WalletTransactionType,
)
from app.services import referral_utils

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ReferralCodeRepository(BaseRepository[ReferralCode]):
    """Data access for referral codes."""

    def __init__(self, db: Session):
        super().__init__(db, ReferralCode)

    def get_by_code(self, code: str) -> Optional[ReferralCode]:
        result = self.db.query(ReferralCode).filter(ReferralCode.code == code.upper()).first()
        return cast(Optional[ReferralCode], result)

    def get_by_slug(self, slug: str) -> Optional[ReferralCode]:
        result = self.db.query(ReferralCode).filter(ReferralCode.vanity_slug == slug).first()
        return cast(Optional[ReferralCode], result)

    def get_by_id(self, code_id: UUID, for_update: bool = False) -> Optional[ReferralCode]:
        query = self.db.query(ReferralCode).filter(ReferralCode.id == code_id)
        if for_update:
            query = query.with_for_update()
        return cast(Optional[ReferralCode], query.first())

    def _get_by_user_id(self, user_id: str) -> Optional[ReferralCode]:
        stmt = (
            sa.select(ReferralCode)
            .where(
                ReferralCode.referrer_user_id == user_id,
                ReferralCode.status == ReferralCodeStatus.ACTIVE,
            )
            .limit(1)
        )
        return cast(Optional[ReferralCode], self.db.execute(stmt).scalar_one_or_none())

    def get_active_for_user(self, user_id: str) -> Optional[ReferralCode]:
        """Return active referral code for the user if one exists."""

        return self._get_by_user_id(user_id)

    def get_or_create_for_user(self, user_id: str) -> ReferralCode:
        """Fetch existing active code or create a new unique code."""

        existing = self._get_by_user_id(user_id)
        if existing:
            return existing

        try:
            self.db.execute(sa.text("SET LOCAL lock_timeout = '1500ms'"))
            self.db.execute(sa.text("SET LOCAL statement_timeout = '3000ms'"))
        except SQLAlchemyError as exc:  # pragma: no cover - defensive guard
            raise RepositoryException("Failed to configure referral code timeouts") from exc

        max_attempts = 6
        attempts = 0
        while attempts < max_attempts:
            candidate = referral_utils.gen_code()

            insert_stmt = (
                pg_insert(ReferralCode)
                .values(
                    id=uuid.uuid4(),
                    referrer_user_id=user_id,
                    code=candidate,
                    status=ReferralCodeStatus.ACTIVE,
                )
                .on_conflict_do_nothing()
                .returning(ReferralCode.id)
            )

            try:
                inserted = self.db.execute(insert_stmt).first()
            except SQLAlchemyError as exc:
                raise RepositoryException("Unable to issue referral code") from exc

            if inserted:
                inserted_id = inserted[0]
                created_stmt = sa.select(ReferralCode).where(ReferralCode.id == inserted_id)
                created = cast(
                    Optional[ReferralCode],
                    self.db.execute(created_stmt).scalar_one_or_none(),
                )
                if created:
                    return created
                raise RepositoryException(
                    "Referral code insert succeeded but could not be reloaded"
                )

            existing = self.get_active_for_user(user_id)
            if existing:
                return existing

            attempts += 1

        raise RepositoryException("Unable to generate unique referral code after retries")


class ReferralClickRepository(BaseRepository[ReferralClick]):
    """Data access for referral click tracking."""

    def __init__(self, db: Session):
        super().__init__(db, ReferralClick)

    def create(  # type: ignore[override]
        self,
        *,
        code_id: UUID,
        device_fp_hash: Optional[str],
        ip_hash: Optional[str],
        ua_hash: Optional[str],
        channel: Optional[str],
        ts: datetime,
    ) -> ReferralClick:
        click = ReferralClick(
            id=uuid.uuid4(),
            code_id=code_id,
            device_fp_hash=device_fp_hash,
            ip_hash=ip_hash,
            ua_hash=ua_hash,
            channel=channel,
            ts=ts,
        )
        self.db.add(click)
        self.db.flush()
        return click

    def count_since(self, since: datetime) -> int:
        return int(
            self.db.query(func.count(ReferralClick.id)).filter(ReferralClick.ts >= since).scalar()
            or 0
        )

    def clicks_since(self, since: datetime) -> int:
        """Return click count since the provided timestamp."""

        return self.count_since(since)

    def get_fingerprint_snapshot(
        self, code_id: UUID, attribution_ts: datetime
    ) -> Dict[str, Optional[str]]:
        """Return click and signup fingerprint hashes for analysis."""

        clicks: List[ReferralClick] = (
            self.db.query(ReferralClick)
            .filter(ReferralClick.code_id == code_id)
            .order_by(ReferralClick.ts.desc())
            .all()
        )

        result: Dict[str, Optional[str]] = {
            "click_device": None,
            "click_ip": None,
            "signup_device": None,
            "signup_ip": None,
        }

        for click in clicks:
            if (
                click.channel != "signup"
                and click.ts <= attribution_ts
                and result["click_device"] is None
            ):
                result["click_device"] = click.device_fp_hash
                result["click_ip"] = click.ip_hash

            if (
                click.channel == "signup"
                and click.ts == attribution_ts
                and result["signup_device"] is None
            ):
                result["signup_device"] = click.device_fp_hash
                result["signup_ip"] = click.ip_hash

        return result


class ReferralAttributionRepository(BaseRepository[ReferralAttribution]):
    """Data access for referral attributions."""

    def __init__(self, db: Session):
        super().__init__(db, ReferralAttribution)

    def get_by_referred_user_id(
        self, user_id: str, for_update: bool = False
    ) -> Optional[ReferralAttribution]:
        query = self.db.query(ReferralAttribution).filter(
            ReferralAttribution.referred_user_id == user_id
        )
        if for_update:
            query = query.with_for_update()
        return cast(Optional[ReferralAttribution], query.first())

    def create_if_absent(
        self,
        *,
        code_id: UUID,
        referred_user_id: str,
        source: str,
        ts: datetime,
    ) -> bool:
        stmt = (
            pg_insert(ReferralAttribution)
            .values(
                id=uuid.uuid4(),
                code_id=code_id,
                referred_user_id=referred_user_id,
                source=source,
                ts=ts,
            )
            .on_conflict_do_nothing(
                index_elements=[ReferralAttribution.code_id, ReferralAttribution.referred_user_id]
            )
        )

        result = cast(CursorResult[Any], self.db.execute(stmt))
        rowcount = cast(int, getattr(result, "rowcount", 0))
        created = rowcount == 1
        if created:
            self.db.flush()
        return created

    def exists_for_user(self, referred_user_id: str) -> bool:
        return (
            self.db.query(ReferralAttribution)
            .filter(ReferralAttribution.referred_user_id == referred_user_id)
            .first()
            is not None
        )

    def velocity_counts(
        self, referrer_user_id: str, day_floor: datetime, week_floor: datetime
    ) -> Tuple[int, int]:
        base_query = (
            self.db.query(ReferralAttribution)
            .join(ReferralCode, ReferralCode.id == ReferralAttribution.code_id)
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
        )

        daily = (
            base_query.filter(ReferralAttribution.ts >= day_floor)
            .with_entities(func.count(ReferralAttribution.id))
            .scalar()
        )
        weekly = (
            base_query.filter(ReferralAttribution.ts >= week_floor)
            .with_entities(func.count(ReferralAttribution.id))
            .scalar()
        )

        return int(daily or 0), int(weekly or 0)

    def count_since(self, since: datetime) -> int:
        return int(
            self.db.query(func.count(ReferralAttribution.id))
            .filter(ReferralAttribution.ts >= since)
            .scalar()
            or 0
        )

    def attributions_since(self, since: datetime) -> int:
        """Return attribution count since the provided timestamp."""

        return self.count_since(since)


class ReferralRewardRepository(BaseRepository[ReferralReward]):
    """Data access for referral rewards."""

    def __init__(self, db: Session):
        super().__init__(db, ReferralReward)

    def count_student_rewards_for_cap(self, referrer_user_id: str) -> int:
        return int(
            self.db.query(func.count(ReferralReward.id))
            .filter(
                ReferralReward.referrer_user_id == referrer_user_id,
                ReferralReward.side == RewardSide.STUDENT,
                ReferralReward.status.in_(
                    [RewardStatus.PENDING, RewardStatus.UNLOCKED, RewardStatus.REDEEMED]
                ),
            )
            .scalar()
            or 0
        )

    def _get_or_create_reward(
        self,
        *,
        owner_id: str,
        counterpart_id: str,
        side: RewardSide,
        amount_cents: int,
        unlock_ts: datetime,
        expire_ts: datetime,
        rule_version: str,
    ) -> ReferralReward:
        existing_reward = cast(
            Optional[ReferralReward],
            self.db.query(ReferralReward)
            .filter(
                ReferralReward.referrer_user_id == owner_id,
                ReferralReward.referred_user_id == counterpart_id,
                ReferralReward.side == side,
            )
            .with_for_update()
            .first(),
        )
        if existing_reward is not None:
            return existing_reward

        reward = ReferralReward(
            id=uuid.uuid4(),
            referrer_user_id=owner_id,
            referred_user_id=counterpart_id,
            side=side,
            status=RewardStatus.PENDING,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version,
        )
        self.db.add(reward)
        self.db.flush()
        return reward

    def create_student_pair(
        self,
        *,
        student_user_id: str,
        inviter_user_id: str,
        amount_cents: int,
        unlock_ts: datetime,
        expire_ts: datetime,
        rule_version_student: str,
        rule_version_referrer: str,
    ) -> Tuple[ReferralReward, ReferralReward]:
        student_reward = self._get_or_create_reward(
            owner_id=student_user_id,
            counterpart_id=inviter_user_id,
            side=RewardSide.STUDENT,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version_student,
        )
        referrer_reward = self._get_or_create_reward(
            owner_id=inviter_user_id,
            counterpart_id=student_user_id,
            side=RewardSide.STUDENT,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version_referrer,
        )
        return student_reward, referrer_reward

    def create_instructor_referrer_reward(
        self,
        *,
        referrer_user_id: str,
        referred_user_id: str,
        amount_cents: int,
        unlock_ts: datetime,
        expire_ts: datetime,
        rule_version: str,
    ) -> ReferralReward:
        return self._get_or_create_reward(
            owner_id=referrer_user_id,
            counterpart_id=referred_user_id,
            side=RewardSide.INSTRUCTOR,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version,
        )

    def create_instructor_referral_payout(
        self,
        *,
        referrer_user_id: str,
        referred_instructor_id: str,
        triggering_booking_id: str,
        amount_cents: int,
        was_founding_bonus: bool,
        idempotency_key: str,
    ) -> Optional[InstructorReferralPayout]:
        """
        Create instructor referral payout record.

        Returns None if a payout already exists for the idempotency key or referred instructor.
        """
        existing = (
            self.db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return None

        existing_for_instructor = (
            self.db.query(InstructorReferralPayout)
            .filter(
                InstructorReferralPayout.referred_instructor_id == referred_instructor_id,
            )
            .first()
        )
        if existing_for_instructor:
            return None

        try:
            payout = InstructorReferralPayout(
                referrer_user_id=referrer_user_id,
                referred_instructor_id=referred_instructor_id,
                triggering_booking_id=triggering_booking_id,
                amount_cents=amount_cents,
                was_founding_bonus=was_founding_bonus,
                idempotency_key=idempotency_key,
                stripe_transfer_status="pending",
            )
            self.db.add(payout)
            self.db.flush()
            return payout
        except IntegrityError:
            self.db.rollback()
            logger.info(
                "Payout already exists for referred instructor %s "
                "(concurrent creation handled by DB constraint)",
                referred_instructor_id,
            )
            return None

    def get_instructor_referral_payout_by_id(
        self, payout_id: str
    ) -> Optional[InstructorReferralPayout]:
        """Get a payout record by ID."""
        result = (
            self.db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.id == payout_id)
            .first()
        )
        return cast(Optional[InstructorReferralPayout], result)

    def get_instructor_referral_payout_by_referred(
        self, referred_instructor_id: str
    ) -> Optional[InstructorReferralPayout]:
        """Get payout record for a specific referred instructor."""
        result = (
            self.db.query(InstructorReferralPayout)
            .filter(
                InstructorReferralPayout.referred_instructor_id == referred_instructor_id,
            )
            .first()
        )
        return cast(Optional[InstructorReferralPayout], result)

    def get_referrer_payouts(
        self,
        referrer_user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[InstructorReferralPayout]:
        """Get payouts for a referrer, optionally filtered by status."""
        query = self.db.query(InstructorReferralPayout).filter(
            InstructorReferralPayout.referrer_user_id == referrer_user_id
        )
        if status:
            query = query.filter(InstructorReferralPayout.stripe_transfer_status == status)
        return cast(
            List[InstructorReferralPayout],
            query.order_by(InstructorReferralPayout.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all(),
        )

    def count_referrer_payouts_by_status(self, referrer_user_id: str, status: str) -> int:
        """Count payouts for a referrer by status."""
        result = (
            self.db.query(func.count(InstructorReferralPayout.id))
            .filter(
                InstructorReferralPayout.referrer_user_id == referrer_user_id,
                InstructorReferralPayout.stripe_transfer_status == status,
            )
            .scalar()
        )
        return int(result or 0)

    def sum_referrer_completed_payouts(self, referrer_user_id: str) -> int:
        """Sum completed payout amounts for a referrer (in cents)."""
        result = (
            self.db.query(func.coalesce(func.sum(InstructorReferralPayout.amount_cents), 0))
            .filter(
                InstructorReferralPayout.referrer_user_id == referrer_user_id,
                InstructorReferralPayout.stripe_transfer_status == "completed",
            )
            .scalar()
        )
        return int(result or 0)

    def count_referred_instructors_by_referrer(self, referrer_user_id: str) -> int:
        """
        Count instructors who were referred by this user.

        Joins referral attributions with instructor profiles to count
        only referred users who became instructors.
        """
        from app.models.instructor import InstructorProfile

        result = (
            self.db.query(func.count(ReferralAttribution.id))
            .join(ReferralCode, ReferralAttribution.code_id == ReferralCode.id)
            .join(
                InstructorProfile,
                ReferralAttribution.referred_user_id == InstructorProfile.user_id,
            )
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
            .scalar()
        )
        return int(result or 0)

    def get_referred_instructors_with_payout_status(
        self,
        referrer_user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get instructors referred by this user with payout status context.

        Returns a list of dicts with:
        - user_id, first_name, last_name
        - referred_at (attribution timestamp)
        - is_live, went_live_at (onboarding completion timestamp)
        - first_lesson_completed_at (min completed booking timestamp)
        - stripe_transfer_status, payout_amount_cents
        """
        from app.models.booking import Booking, BookingStatus
        from app.models.instructor import InstructorProfile
        from app.models.user import User

        first_lesson_subq = (
            self.db.query(
                Booking.instructor_id.label("instructor_id"),
                func.min(Booking.completed_at).label("first_lesson_completed_at"),
            )
            .filter(Booking.status == BookingStatus.COMPLETED)
            .group_by(Booking.instructor_id)
            .subquery()
        )

        query = (
            self.db.query(
                User.id.label("user_id"),
                User.first_name,
                User.last_name,
                ReferralAttribution.ts.label("referred_at"),
                InstructorProfile.is_live,
                InstructorProfile.onboarding_completed_at.label("went_live_at"),
                first_lesson_subq.c.first_lesson_completed_at,
                InstructorReferralPayout.stripe_transfer_status,
                InstructorReferralPayout.amount_cents.label("payout_amount_cents"),
            )
            .select_from(ReferralAttribution)
            .join(ReferralCode, ReferralAttribution.code_id == ReferralCode.id)
            .join(User, ReferralAttribution.referred_user_id == User.id)
            .join(InstructorProfile, User.id == InstructorProfile.user_id)
            .outerjoin(
                first_lesson_subq,
                User.id == first_lesson_subq.c.instructor_id,
            )
            .outerjoin(
                InstructorReferralPayout,
                User.id == InstructorReferralPayout.referred_instructor_id,
            )
            .filter(ReferralCode.referrer_user_id == referrer_user_id)
            .order_by(ReferralAttribution.ts.desc())
            .offset(offset)
            .limit(limit)
        )

        results: List[Dict[str, Any]] = []
        for row in query.all():
            results.append(
                {
                    "user_id": row.user_id,
                    "first_name": row.first_name,
                    "last_name": row.last_name,
                    "referred_at": row.referred_at,
                    "is_live": bool(row.is_live),
                    "went_live_at": row.went_live_at,
                    "first_lesson_completed_at": row.first_lesson_completed_at,
                    "stripe_transfer_status": row.stripe_transfer_status,
                    "payout_amount_cents": row.payout_amount_cents,
                }
            )

        return results

    def find_pending_to_unlock(
        self, now: datetime, limit: int = 200, *, lock: bool = True
    ) -> List[ReferralReward]:
        query = (
            self.db.query(ReferralReward)
            .filter(
                ReferralReward.status == RewardStatus.PENDING,
                ReferralReward.unlock_ts.isnot(None),
                ReferralReward.unlock_ts <= now,
            )
            .order_by(ReferralReward.unlock_ts.asc())
        )
        if lock:
            query = query.with_for_update(skip_locked=True)
        return cast(List[ReferralReward], query.limit(limit).all())

    def mark_unlocked(self, reward_id: UUID) -> None:
        reward = (
            self.db.query(ReferralReward)
            .filter(ReferralReward.id == reward_id)
            .with_for_update()
            .first()
        )
        if not reward:
            raise RepositoryException(f"ReferralReward {reward_id} not found")
        typed_reward = cast(ReferralReward, reward)
        typed_reward.status = RewardStatus.UNLOCKED
        self.db.flush()

    def mark_void(self, reward_id: UUID) -> None:
        reward = (
            self.db.query(ReferralReward)
            .filter(ReferralReward.id == reward_id)
            .with_for_update()
            .first()
        )
        if reward:
            typed_reward = cast(ReferralReward, reward)
            typed_reward.status = RewardStatus.VOID
            self.db.flush()

    def void_rewards(self, reward_ids: List[UUID]) -> None:
        if not reward_ids:
            return
        (
            self.db.query(ReferralReward)
            .filter(ReferralReward.id.in_(reward_ids))
            .update({ReferralReward.status: RewardStatus.VOID}, synchronize_session=False)
        )
        self.db.flush()

    def pop_oldest_unlocked_student_reward(
        self, user_id: str, max_cents: int
    ) -> Optional[ReferralReward]:
        reward = (
            self.db.query(ReferralReward)
            .filter(
                ReferralReward.referrer_user_id == user_id,
                ReferralReward.side == RewardSide.STUDENT,
                ReferralReward.status == RewardStatus.UNLOCKED,
            )
            .order_by(ReferralReward.created_at.asc())
            .with_for_update()
            .first()
        )
        if reward and reward.amount_cents > 0 and max_cents > 0:
            return cast(ReferralReward, reward)
        return None

    def pop_oldest_unlocked_instructor_reward(self, user_id: str) -> Optional[ReferralReward]:
        reward = (
            self.db.query(ReferralReward)
            .filter(
                ReferralReward.referrer_user_id == user_id,
                ReferralReward.side == RewardSide.INSTRUCTOR,
                ReferralReward.status == RewardStatus.UNLOCKED,
            )
            .order_by(ReferralReward.created_at.asc())
            .with_for_update()
            .first()
        )
        return cast(Optional[ReferralReward], reward)

    def mark_redeemed(self, reward_id: UUID) -> None:
        reward = (
            self.db.query(ReferralReward)
            .filter(ReferralReward.id == reward_id)
            .with_for_update()
            .first()
        )
        if not reward:
            raise RepositoryException(f"ReferralReward {reward_id} not found")
        typed_reward = cast(ReferralReward, reward)
        typed_reward.status = RewardStatus.REDEEMED
        self.db.flush()

    def _expired_rewards(self, now: datetime, *, lock: bool) -> List[ReferralReward]:
        query = self.db.query(ReferralReward).filter(
            ReferralReward.status == RewardStatus.UNLOCKED,
            ReferralReward.expire_ts.isnot(None),
            ReferralReward.expire_ts < now,
        )
        if lock:
            query = query.with_for_update(skip_locked=True)
        return cast(List[ReferralReward], query.all())

    def void_expired(self, now: datetime) -> List[UUID]:
        rewards = self._expired_rewards(now, lock=True)
        voided_ids: List[UUID] = []
        for reward in rewards:
            reward.status = RewardStatus.VOID
            voided_ids.append(reward.id)
        if voided_ids:
            self.db.flush()
        return voided_ids

    def get_expired_reward_ids(self, now: datetime) -> List[UUID]:
        return [reward.id for reward in self._expired_rewards(now, lock=False)]

    def list_by_user_and_status(
        self, *, user_id: str, status: RewardStatus, limit: int = 50
    ) -> List[ReferralReward]:
        return cast(
            List[ReferralReward],
            (
                self.db.query(ReferralReward)
                .filter(
                    ReferralReward.referrer_user_id == user_id,
                    ReferralReward.status == status,
                )
                .order_by(
                    ReferralReward.created_at.desc(),
                    ReferralReward.id.desc(),
                )
                .limit(limit)
                .all()
            ),
        )

    def counts_by_status(self) -> Dict[str, int]:
        """Return reward counts grouped by status."""

        rows = (
            self.db.query(
                ReferralReward.status,
                func.count(ReferralReward.id).label("count"),
            )
            .group_by(ReferralReward.status)
            .all()
        )
        counts: Dict[str, int] = {status.value: 0 for status in RewardStatus}
        for status, count in rows:
            key = status.value if isinstance(status, RewardStatus) else str(status)
            counts[key] = int(count or 0)
        return {
            RewardStatus.PENDING.value: counts[RewardStatus.PENDING.value],
            RewardStatus.UNLOCKED.value: counts[RewardStatus.UNLOCKED.value],
            RewardStatus.REDEEMED.value: counts[RewardStatus.REDEEMED.value],
            RewardStatus.VOID.value: counts[RewardStatus.VOID.value],
        }

    def count_pending_due(self, now: datetime) -> int:
        """Return count of pending rewards whose unlock timestamp has passed."""

        result = (
            self.db.query(func.count(ReferralReward.id))
            .filter(
                ReferralReward.status == RewardStatus.PENDING,
                ReferralReward.unlock_ts.isnot(None),
                ReferralReward.unlock_ts <= now,
            )
            .scalar()
        )
        return int(result or 0)

    def total_student_rewards(self) -> int:
        """Return total number of student-side rewards (active lifecycle only)."""

        result = (
            self.db.query(func.count(ReferralReward.id))
            .filter(
                ReferralReward.side == RewardSide.STUDENT,
                ReferralReward.status.in_(
                    [RewardStatus.PENDING, RewardStatus.UNLOCKED, RewardStatus.REDEEMED]
                ),
            )
            .scalar()
        )
        return int(result or 0)

    def top_referrers(self, limit: int = 20) -> List[Tuple[str, int, Optional[str]]]:
        """Return top referrers ranked by unlocked and redeemed student rewards."""

        rows: List[Tuple[str, int]] = (
            self.db.query(
                ReferralReward.referrer_user_id,
                func.count(ReferralReward.id).label("reward_count"),
            )
            .filter(
                ReferralReward.side == RewardSide.STUDENT,
                ReferralReward.status.in_([RewardStatus.UNLOCKED, RewardStatus.REDEEMED]),
            )
            .group_by(ReferralReward.referrer_user_id)
            .order_by(func.count(ReferralReward.id).desc())
            .limit(limit)
            .all()
        )

        user_ids = [referrer_id for referrer_id, _ in rows]
        codes_by_user: Dict[str, Optional[str]] = {}
        if user_ids:
            code_rows = cast(
                List[Tuple[str, Optional[str]]],
                self.db.query(ReferralCode.referrer_user_id, ReferralCode.code)
                .filter(
                    ReferralCode.referrer_user_id.in_(user_ids),
                    ReferralCode.status == ReferralCodeStatus.ACTIVE,
                )
                .order_by(ReferralCode.referrer_user_id, ReferralCode.created_at.desc())
                .all(),
            )
            for referrer_id, code in code_rows:
                if referrer_id not in codes_by_user:
                    codes_by_user[referrer_id] = code

        return [
            (referrer_id, int(count or 0), codes_by_user.get(referrer_id))
            for referrer_id, count in rows
        ]


class WalletTransactionRepository(BaseRepository[WalletTransaction]):
    """Data access helper for wallet transactions related to referrals."""

    def __init__(self, db: Session):
        super().__init__(db, WalletTransaction)

    def create_referral_credit(
        self, *, user_id: str, reward_id: UUID, amount_cents: int
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            id=uuid.uuid4(),
            user_id=user_id,
            type=WalletTransactionType.REFERRAL_CREDIT,
            amount_cents=amount_cents,
            related_reward_id=reward_id,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def create_fee_rebate(
        self, *, user_id: str, reward_id: UUID, amount_cents: int
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            id=uuid.uuid4(),
            user_id=user_id,
            type=WalletTransactionType.FEE_REBATE,
            amount_cents=amount_cents,
            related_reward_id=reward_id,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction


class ReferralLimitRepository(BaseRepository[ReferralLimit]):
    """Data access for referral limit counters and trust metrics."""

    def __init__(self, db: Session):
        super().__init__(db, ReferralLimit)

    def get(self, user_id: str, *, for_update: bool = False) -> Optional[ReferralLimit]:
        query = self.db.query(ReferralLimit).filter(ReferralLimit.user_id == user_id)
        if for_update:
            query = query.with_for_update()
        return cast(Optional[ReferralLimit], query.first())

    def upsert(
        self,
        *,
        user_id: str,
        daily_ok: int,
        weekly_ok: int,
        month_cap: int,
        trust_score: int,
        last_reviewed_at: Optional[datetime] = None,
    ) -> ReferralLimit:
        record = self.get(user_id, for_update=True)
        reviewed_at = last_reviewed_at or datetime.now(timezone.utc)

        if record is None:
            record = ReferralLimit(
                user_id=user_id,
                daily_ok=daily_ok,
                weekly_ok=weekly_ok,
                month_cap=month_cap,
                trust_score=trust_score,
                last_reviewed_at=reviewed_at,
            )
            self.db.add(record)
        else:
            record.daily_ok = daily_ok
            record.weekly_ok = weekly_ok
            record.month_cap = month_cap
            record.trust_score = trust_score
            record.last_reviewed_at = reviewed_at

        self.db.flush()
        return record

    def increment_daily(self, user_id: str, *, increment: int = 1) -> ReferralLimit:
        record = self.get(user_id, for_update=True)
        reviewed_at = datetime.now(timezone.utc)

        if record is None:
            record = ReferralLimit(
                user_id=user_id,
                daily_ok=increment,
                weekly_ok=increment,
                month_cap=0,
                trust_score=0,
                last_reviewed_at=reviewed_at,
            )
            self.db.add(record)
        else:
            record.daily_ok += increment
            record.weekly_ok += increment
            record.last_reviewed_at = reviewed_at

        self.db.flush()
        return record
