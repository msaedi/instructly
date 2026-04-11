"""Referral repositories supporting the referral domain services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models.referrals import (
    ReferralAttribution,
    ReferralClick,
    ReferralCode,
    ReferralCodeStatus,
    ReferralLimit,
    ReferralReward,
    WalletTransaction,
    WalletTransactionType,
)
from app.services import referral_utils

from .base_repository import BaseRepository
from .referral_reward.instructor_payout_mixin import InstructorPayoutMixin
from .referral_reward.referrer_reporting_mixin import ReferrerReportingMixin
from .referral_reward.reward_analytics_mixin import RewardAnalyticsMixin
from .referral_reward.reward_issuance_mixin import RewardIssuanceMixin
from .referral_reward.reward_lifecycle_mixin import RewardLifecycleMixin


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

    def get_by_id(self, code_id: str, for_update: bool = False) -> Optional[ReferralCode]:
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
                    id=generate_ulid(),
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
        code_id: str,
        device_fp_hash: Optional[str],
        ip_hash: Optional[str],
        ua_hash: Optional[str],
        channel: Optional[str],
        ts: datetime,
    ) -> ReferralClick:
        click = ReferralClick(
            id=generate_ulid(),
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
        self, code_id: str, attribution_ts: datetime
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
        code_id: str,
        referred_user_id: str,
        source: str,
        ts: datetime,
    ) -> bool:
        stmt = (
            pg_insert(ReferralAttribution)
            .values(
                id=generate_ulid(),
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


class ReferralRewardRepository(
    RewardIssuanceMixin,
    InstructorPayoutMixin,
    ReferrerReportingMixin,
    RewardLifecycleMixin,
    RewardAnalyticsMixin,
    BaseRepository[ReferralReward],
):
    """Data access for referral rewards."""

    def __init__(self, db: Session):
        super().__init__(db, ReferralReward)


class WalletTransactionRepository(BaseRepository[WalletTransaction]):
    """Data access helper for wallet transactions related to referrals."""

    def __init__(self, db: Session):
        super().__init__(db, WalletTransaction)

    def create_referral_credit(
        self, *, user_id: str, reward_id: str, amount_cents: int
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            id=generate_ulid(),
            user_id=user_id,
            type=WalletTransactionType.REFERRAL_CREDIT,
            amount_cents=amount_cents,
            related_reward_id=reward_id,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def create_fee_rebate(
        self, *, user_id: str, reward_id: str, amount_cents: int
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            id=generate_ulid(),
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
