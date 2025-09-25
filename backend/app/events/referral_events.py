"""Typed referral events and dispatcher helpers."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Callable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("app.events.referrals")


class ReferralEvent(BaseModel):
    """Base class for referral domain events."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ReferralEventListener = Callable[[ReferralEvent], None]


class ReferralEvents:
    """Registry for referral event listeners."""

    _listeners: List[ReferralEventListener] = []

    @classmethod
    def register(cls, listener: ReferralEventListener) -> None:
        cls._listeners.append(listener)

    @classmethod
    def unregister(cls, listener: ReferralEventListener) -> None:
        cls._listeners = [existing for existing in cls._listeners if existing is not listener]

    @classmethod
    def listeners(cls) -> Sequence[ReferralEventListener]:  # pragma: no cover - trivial accessor
        return tuple(cls._listeners)

    @classmethod
    def dispatch(cls, event: ReferralEvent) -> None:
        for listener in list(cls._listeners):
            try:
                listener(event)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Referral event listener error: %s", listener)
        logger.info("referral_event=%s payload=%s", event.__class__.__name__, event.model_dump())


class ReferralCodeIssued(ReferralEvent):
    user_id: str
    code: str
    channel: Optional[str] = None


class ReferralLinkClicked(ReferralEvent):
    code: str
    device_fp_hash: Optional[str] = None
    ip_hash: Optional[str] = None
    channel: Optional[str] = None
    ts: datetime


class ReferredSignup(ReferralEvent):
    referred_user_id: str
    code: str


class FirstBookingCompleted(ReferralEvent):
    booking_id: str
    user_id: str
    amount_cents: int


class RewardPending(ReferralEvent):
    reward_id: str
    side: str
    referrer_user_id: str
    referred_user_id: str
    amount_cents: int
    unlock_eta: datetime


class RewardUnlocked(ReferralEvent):
    reward_id: str


class RewardRedeemed(ReferralEvent):
    reward_id: str
    order_id: Optional[str] = None


class RewardVoided(ReferralEvent):
    reward_id: str
    reason: str


def register_listener(listener: ReferralEventListener) -> None:
    """Register an in-process listener for referral events."""

    ReferralEvents.register(listener)


def unregister_listener(listener: ReferralEventListener) -> None:
    """Remove a previously registered listener."""

    ReferralEvents.unregister(listener)


def emit_referral_code_issued(
    *, user_id: str, code: str, channel: Optional[str] = None
) -> ReferralCodeIssued:
    event = ReferralCodeIssued(user_id=user_id, code=code, channel=channel)
    ReferralEvents.dispatch(event)
    return event


def emit_referral_link_clicked(
    *,
    code: str,
    ts: datetime,
    device_fp_hash: Optional[str] = None,
    ip_hash: Optional[str] = None,
    channel: Optional[str] = None,
) -> ReferralLinkClicked:
    event = ReferralLinkClicked(
        code=code,
        ts=ts,
        device_fp_hash=device_fp_hash,
        ip_hash=ip_hash,
        channel=channel,
    )
    ReferralEvents.dispatch(event)
    return event


def emit_referred_signup(*, referred_user_id: str, code: str) -> ReferredSignup:
    event = ReferredSignup(referred_user_id=referred_user_id, code=code)
    ReferralEvents.dispatch(event)
    return event


def emit_first_booking_completed(
    *,
    booking_id: str,
    user_id: str,
    amount_cents: int,
) -> FirstBookingCompleted:
    event = FirstBookingCompleted(booking_id=booking_id, user_id=user_id, amount_cents=amount_cents)
    ReferralEvents.dispatch(event)
    return event


def emit_reward_pending(
    *,
    reward_id: str,
    side: str,
    referrer_user_id: str,
    referred_user_id: str,
    amount_cents: int,
    unlock_eta: datetime,
) -> RewardPending:
    event = RewardPending(
        reward_id=reward_id,
        side=side,
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        amount_cents=amount_cents,
        unlock_eta=unlock_eta,
    )
    ReferralEvents.dispatch(event)
    return event


def emit_reward_unlocked(*, reward_id: str) -> RewardUnlocked:
    event = RewardUnlocked(reward_id=reward_id)
    ReferralEvents.dispatch(event)
    return event


def emit_reward_redeemed(*, reward_id: str, order_id: Optional[str] = None) -> RewardRedeemed:
    event = RewardRedeemed(reward_id=reward_id, order_id=order_id)
    ReferralEvents.dispatch(event)
    return event


def emit_reward_voided(*, reward_id: str, reason: str) -> RewardVoided:
    event = RewardVoided(reward_id=reward_id, reason=reason)
    ReferralEvents.dispatch(event)
    return event


__all__ = [
    "ReferralEvent",
    "ReferralEventListener",
    "ReferralEvents",
    "ReferralCodeIssued",
    "ReferralLinkClicked",
    "ReferredSignup",
    "FirstBookingCompleted",
    "RewardPending",
    "RewardUnlocked",
    "RewardRedeemed",
    "RewardVoided",
    "register_listener",
    "unregister_listener",
    "emit_referral_code_issued",
    "emit_referral_link_clicked",
    "emit_referred_signup",
    "emit_first_booking_completed",
    "emit_reward_pending",
    "emit_reward_unlocked",
    "emit_reward_redeemed",
    "emit_reward_voided",
]
