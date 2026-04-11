"""Referral reward analytics queries."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple, cast

from sqlalchemy import func

from ...models.referrals import (
    ReferralCode,
    ReferralCodeStatus,
    ReferralReward,
    RewardSide,
    RewardStatus,
)
from .mixin_base import ReferralRewardRepositoryMixinBase


class RewardAnalyticsMixin(ReferralRewardRepositoryMixinBase):
    """Aggregate reward metrics and rankings."""

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
