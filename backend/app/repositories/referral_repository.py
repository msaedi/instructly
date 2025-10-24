"""Referral repositories supporting the referral domain services."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple, cast
import uuid
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.referrals import (
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
                created = self.db.execute(created_stmt).scalar_one_or_none()
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

        result = self.db.execute(stmt)
        created = result.rowcount == 1 if result is not None else False
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
        reward = (
            self.db.query(ReferralReward)
            .filter(
                ReferralReward.referrer_user_id == owner_id,
                ReferralReward.referred_user_id == counterpart_id,
                ReferralReward.side == side,
            )
            .with_for_update()
            .first()
        )
        if reward:
            return cast(ReferralReward, reward)

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
