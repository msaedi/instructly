"""Referral reward lifecycle helpers."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, cast

from ...core.exceptions import RepositoryException
from ...models.referrals import ReferralReward, RewardSide, RewardStatus
from .mixin_base import ReferralRewardRepositoryMixinBase


class RewardLifecycleMixin(ReferralRewardRepositoryMixinBase):
    """Reward unlocking, redemption, and expiry helpers."""

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

    def mark_unlocked(self, reward_id: str) -> None:
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

    def mark_void(self, reward_id: str) -> None:
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

    def void_rewards(self, reward_ids: List[str]) -> None:
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

    def mark_redeemed(self, reward_id: str) -> None:
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

    def void_expired(self, now: datetime) -> List[str]:
        rewards = self._expired_rewards(now, lock=True)
        voided_ids: List[str] = []
        for reward in rewards:
            reward.status = RewardStatus.VOID
            voided_ids.append(reward.id)
        if voided_ids:
            self.db.flush()
        return voided_ids

    def get_expired_reward_ids(self, now: datetime) -> List[str]:
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

    def list_active_rewards_for_user(self, *, user_id: str, limit: int) -> List[ReferralReward]:
        """Return non-void rewards for a user ordered newest-first."""
        return cast(
            List[ReferralReward],
            (
                self.db.query(ReferralReward)
                .filter(
                    ReferralReward.referrer_user_id == user_id,
                    ReferralReward.status.in_(
                        [
                            RewardStatus.PENDING,
                            RewardStatus.UNLOCKED,
                            RewardStatus.REDEEMED,
                        ]
                    ),
                )
                .order_by(
                    ReferralReward.created_at.desc(),
                    ReferralReward.id.desc(),
                )
                .limit(limit * 3)
                .all()
            ),
        )
