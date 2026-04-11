"""Shared typing surface for referral reward repository mixins."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, List

from sqlalchemy.orm import Session

from ...models.referrals import ReferralReward, RewardSide

if TYPE_CHECKING:

    class ReferralRewardRepositoryMixinBase:
        """Typed attribute/method surface supplied by the referral reward facade."""

        db: Session
        logger: logging.Logger
        model: type[ReferralReward]

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
            ...

        def _expired_rewards(self, now: datetime, *, lock: bool) -> List[ReferralReward]:
            ...

else:

    class ReferralRewardRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        model: type[ReferralReward]
