"""Referral reward issuance helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple, cast

from sqlalchemy import func

from ...core.ulid_helper import generate_ulid
from ...models.referrals import ReferralReward, RewardSide, RewardStatus
from .mixin_base import ReferralRewardRepositoryMixinBase


class RewardIssuanceMixin(ReferralRewardRepositoryMixinBase):
    """Reward creation and issuance helpers."""

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
            id=generate_ulid(),
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
        student_reward = self.create_student_reward_for_referred_user(
            student_user_id=student_user_id,
            inviter_user_id=inviter_user_id,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version_student,
        )
        referrer_reward = self.create_student_reward_for_referrer(
            referrer_user_id=inviter_user_id,
            referred_user_id=student_user_id,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version_referrer,
        )
        return student_reward, referrer_reward

    def create_student_reward_for_referred_user(
        self,
        *,
        student_user_id: str,
        inviter_user_id: str,
        amount_cents: int,
        unlock_ts: datetime,
        expire_ts: datetime,
        rule_version: str,
    ) -> ReferralReward:
        return self._get_or_create_reward(
            owner_id=student_user_id,
            counterpart_id=inviter_user_id,
            side=RewardSide.STUDENT,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version,
        )

    def create_student_reward_for_referrer(
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
            side=RewardSide.STUDENT,
            amount_cents=amount_cents,
            unlock_ts=unlock_ts,
            expire_ts=expire_ts,
            rule_version=rule_version,
        )

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
