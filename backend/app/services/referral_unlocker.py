"""Referral reward unlocker job (cron/CLI entrypoint)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.events.referral_events import emit_reward_unlocked, emit_reward_voided
from app.repositories.factory import RepositoryFactory
from app.repositories.referral_repository import ReferralRewardRepository
from app.services.base import BaseService

logger = logging.getLogger(__name__)


@dataclass
class UnlockerResult:
    processed: int
    unlocked: int
    voided: int
    expired: int


class ReferralUnlocker(BaseService):
    """Iterate pending rewards and unlock or void them safely."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.referral_reward_repo: ReferralRewardRepository = (
            RepositoryFactory.create_referral_reward_repository(db)
        )
        self.payment_repository = RepositoryFactory.create_payment_repository(db)

    @BaseService.measure_operation("referrals.unlocker.run")
    def run(self, *, limit: int = 200, dry_run: bool = False) -> UnlockerResult:
        now = datetime.now(timezone.utc)
        processed = unlocked = voided = expired = 0

        if dry_run:
            rewards = self.referral_reward_repo.find_pending_to_unlock(now, limit, lock=False)
            processed = len(rewards)
            expired = len(self.referral_reward_repo.get_expired_reward_ids(now))
            return UnlockerResult(processed=processed, unlocked=0, voided=0, expired=expired)

        expired_ids: list[str] = []

        with self.transaction():
            rewards = self.referral_reward_repo.find_pending_to_unlock(now, limit)
            processed = len(rewards)

            for reward in rewards:
                booking_prefix = self._extract_booking_prefix(reward.rule_version)
                if booking_prefix and self._booking_refunded(booking_prefix):
                    self.referral_reward_repo.mark_void(reward.id)
                    voided += 1
                    emit_reward_voided(reward_id=str(reward.id), reason="refund")
                    continue

                self.referral_reward_repo.mark_unlocked(reward.id)
                unlocked += 1
                emit_reward_unlocked(reward_id=str(reward.id))

            expired_uuid_list = self.referral_reward_repo.void_expired(now)
            expired_ids = [str(reward_id) for reward_id in expired_uuid_list]

        for reward_id in expired_ids:
            emit_reward_voided(reward_id=reward_id, reason="expired")
        expired = len(expired_ids)

        return UnlockerResult(
            processed=processed, unlocked=unlocked, voided=voided, expired=expired
        )

    def _booking_refunded(self, booking_prefix: str) -> bool:
        payment = self.payment_repository.get_payment_by_booking_prefix(booking_prefix)
        if not payment or not payment.status:
            return False
        status = payment.status.lower()
        return status in {"refunded", "canceled", "cancelled"}

    @staticmethod
    def _extract_booking_prefix(rule_version: Optional[str]) -> Optional[str]:
        if not rule_version or "-" not in rule_version:
            return None
        prefix = rule_version.split("-", 1)[1]
        return prefix or None


def main() -> None:  # pragma: no cover - CLI entry point
    parser = argparse.ArgumentParser(description="Referral reward unlocker")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist changes")
    parser.add_argument("--limit", type=int, default=200, help="Maximum rewards to process")
    args = parser.parse_args()

    session = SessionLocal()
    unlocker = ReferralUnlocker(session)
    try:
        result = unlocker.run(limit=args.limit, dry_run=args.dry_run)
        logger.info(
            "Referral unlocker finished: processed=%s unlocked=%s voided=%s expired=%s dry_run=%s",
            result.processed,
            result.unlocked,
            result.voided,
            result.expired,
            args.dry_run,
        )
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
