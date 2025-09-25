"""Wallet hooks for referral rewards."""

from __future__ import annotations

import logging
from typing import Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session

from app.events.referral_events import emit_reward_redeemed
from app.models.referrals import WalletTransaction
from app.repositories.factory import RepositoryFactory
from app.repositories.referral_repository import (
    ReferralRewardRepository,
    WalletTransactionRepository,
)
from app.services.base import BaseService

logger = logging.getLogger(__name__)

UserID = Union[str, UUID]


class WalletService(BaseService):
    """Integrate referral rewards with wallet ledger mutations."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.referral_reward_repo: ReferralRewardRepository = (
            RepositoryFactory.create_referral_reward_repository(db)
        )
        self.wallet_transaction_repo: WalletTransactionRepository = (
            RepositoryFactory.create_wallet_transaction_repository(db)
        )

    @BaseService.measure_operation("wallet.apply_fee_rebate_on_payout")
    def apply_fee_rebate_on_payout(
        self,
        *,
        user_id: UserID,
        payout_id: str,
        platform_fee_cents: Optional[int] = None,
    ) -> Optional[WalletTransaction]:
        """Redeem an instructor reward against a Stripe payout."""

        owner_id = str(user_id)
        with self.transaction():
            reward = self.referral_reward_repo.pop_oldest_unlocked_instructor_reward(owner_id)
            if not reward:
                return None

            amount = reward.amount_cents
            if platform_fee_cents is not None:
                amount = min(amount, platform_fee_cents)
            if amount <= 0:
                logger.info("Fee rebate skipped: non-positive amount for reward %s", reward.id)
                return None

            txn = self.wallet_transaction_repo.create_fee_rebate(
                user_id=owner_id,
                reward_id=reward.id,
                amount_cents=amount,
            )
            self.referral_reward_repo.mark_redeemed(reward.id)

        emit_reward_redeemed(reward_id=str(reward.id), order_id=payout_id)
        return txn

    @BaseService.measure_operation("wallet.consume_student_credit")
    def consume_student_credit(
        self,
        *,
        user_id: UserID,
        order_id: str,
        amount_cents: int,
    ) -> Optional[WalletTransaction]:
        """Consume an unlocked student reward for checkout credits."""

        if amount_cents <= 0:
            logger.info("Student credit consumption skipped: non-positive amount requested")
            return None

        owner_id = str(user_id)
        with self.transaction():
            reward = self.referral_reward_repo.pop_oldest_unlocked_student_reward(
                owner_id, amount_cents
            )
            if not reward:
                return None

            redeem_amount = min(amount_cents, reward.amount_cents)
            if redeem_amount <= 0:
                return None

            txn = self.wallet_transaction_repo.create_referral_credit(
                user_id=owner_id,
                reward_id=reward.id,
                amount_cents=redeem_amount,
            )
            self.referral_reward_repo.mark_redeemed(reward.id)

        emit_reward_redeemed(reward_id=str(reward.id), order_id=order_id)
        return txn


__all__ = ["WalletService"]
