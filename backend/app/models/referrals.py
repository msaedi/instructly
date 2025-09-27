"""Referral program models for Theta Park Slope beta.

This module defines the SQLAlchemy ORM models for the referral program,
including codes, click tracking, attribution records, rewards, wallet
transactions, and program limits. All identifiers use UUID primary keys
generated in application code via ``uuid.uuid4``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReferralCodeStatus(str, Enum):
    """Lifecycle status for referral codes."""

    ACTIVE = "active"
    DISABLED = "disabled"


class RewardSide(str, Enum):
    """Which party receives the reward."""

    STUDENT = "student"
    INSTRUCTOR = "instructor"


class RewardStatus(str, Enum):
    """Lifecycle of a reward."""

    PENDING = "pending"
    UNLOCKED = "unlocked"
    REDEEMED = "redeemed"
    VOID = "void"


class WalletTransactionType(str, Enum):
    """Types of wallet ledger entries."""

    REFERRAL_CREDIT = "referral_credit"
    FEE_REBATE = "fee_rebate"


class ReferralCode(Base):
    """Referral code assigned to a referrer."""

    __tablename__ = "referral_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    vanity_slug: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    referrer_user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ReferralCodeStatus] = mapped_column(
        SAEnum(
            ReferralCodeStatus,
            name="referral_code_status",
            native_enum=True,
            create_type=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ReferralCodeStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    referrer: Mapped["User"] = relationship(
        "User", back_populates="referral_codes", passive_deletes=True
    )
    clicks: Mapped[List["ReferralClick"]] = relationship(
        "ReferralClick", back_populates="code", cascade="all, delete-orphan", passive_deletes=True
    )
    attributions: Mapped[List["ReferralAttribution"]] = relationship(
        "ReferralAttribution",
        back_populates="code",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("idx_referral_codes_referrer_user_id", "referrer_user_id"),)

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return (
            f"<ReferralCode code={self.code} referrer={self.referrer_user_id} status={self.status}>"
        )


class ReferralClick(Base):
    """Click tracking for referral links."""

    __tablename__ = "referral_clicks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("referral_codes.id", ondelete="CASCADE"), nullable=False
    )
    device_fp_hash: Mapped[Optional[str]] = mapped_column(String(64))
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64))
    ua_hash: Mapped[Optional[str]] = mapped_column(String(64))
    channel: Mapped[Optional[str]] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    code: Mapped[ReferralCode] = relationship(
        "ReferralCode", back_populates="clicks", passive_deletes=True
    )

    __table_args__ = (
        Index(
            "idx_referral_clicks_code_ts",
            "code_id",
            "ts",
            postgresql_using="btree",
            postgresql_ops={"ts": "DESC"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return f"<ReferralClick code_id={self.code_id} channel={self.channel}>"


class ReferralAttribution(Base):
    """Association between a referral code and a newly referred user."""

    __tablename__ = "referral_attributions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("referral_codes.id", ondelete="CASCADE"), nullable=False
    )
    referred_user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    code: Mapped[ReferralCode] = relationship(
        "ReferralCode", back_populates="attributions", passive_deletes=True
    )
    referred_user: Mapped["User"] = relationship(
        "User", back_populates="referral_attributions_received", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("code_id", "referred_user_id", name="uq_referral_attribution_pair"),
    )

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return f"<ReferralAttribution code_id={self.code_id} referred_user={self.referred_user_id}>"


class ReferralReward(Base):
    """Reward entries created for referral activity."""

    __tablename__ = "referral_rewards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referred_user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[RewardSide] = mapped_column(
        SAEnum(
            RewardSide,
            name="reward_side",
            native_enum=True,
            create_type=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[RewardStatus] = mapped_column(
        SAEnum(
            RewardStatus,
            name="reward_status",
            native_enum=True,
            create_type=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RewardStatus.PENDING,
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    unlock_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expire_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rule_version: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    referrer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referrer_user_id],
        back_populates="referral_rewards_earned",
        passive_deletes=True,
    )
    referred_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referred_user_id],
        back_populates="referral_rewards_received",
        passive_deletes=True,
    )
    wallet_transactions: Mapped[List["WalletTransaction"]] = relationship(
        "WalletTransaction",
        back_populates="related_reward",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_referral_rewards_amount_non_negative"),
        Index("idx_referral_rewards_referrer_status", "referrer_user_id", "status"),
        Index("idx_referral_rewards_referred_side", "referred_user_id", "side"),
    )

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return (
            "<ReferralReward referrer={referrer} referred={referred} side={side} status={status}>"
        ).format(
            referrer=self.referrer_user_id,
            referred=self.referred_user_id,
            side=self.side,
            status=self.status,
        )


class WalletTransaction(Base):
    """Wallet ledger entries related to referral rewards."""

    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[WalletTransactionType] = mapped_column(
        SAEnum(
            WalletTransactionType,
            name="wallet_txn_type",
            native_enum=True,
            create_type=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    related_reward_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("referral_rewards.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="wallet_transactions", passive_deletes=True
    )
    related_reward: Mapped[Optional[ReferralReward]] = relationship(
        "ReferralReward", back_populates="wallet_transactions", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_wallet_transactions_amount_non_negative"),
        Index(
            "idx_wallet_transactions_user_created_at",
            "user_id",
            "created_at",
            postgresql_using="btree",
            postgresql_ops={"created_at": "DESC"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return (
            f"<WalletTransaction user={self.user_id} type={self.type} amount={self.amount_cents}>"
        )


class ReferralLimit(Base):
    """Soft limits and trust metrics for a referrer."""

    __tablename__ = "referral_limits"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    daily_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weekly_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    month_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trust_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(
        "User", back_populates="referral_limit", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return (
            "<ReferralLimit user={user} daily_ok={daily} weekly_ok={weekly} month_cap={cap}>"
        ).format(user=self.user_id, daily=self.daily_ok, weekly=self.weekly_ok, cap=self.month_cap)
