"""Event primitives for server-side analytics streams."""

from app.events.booking_events import (
    BookingCancelled,
    BookingCompleted,
    BookingCreated,
    BookingReminder,
)
from app.events.publisher import EventPublisher

from .referral_events import (
    FirstBookingCompleted,
    ReferralCodeIssued,
    ReferralEvent,
    ReferralEventListener,
    ReferralEvents,
    ReferralLinkClicked,
    ReferredSignup,
    RewardPending,
    RewardRedeemed,
    RewardUnlocked,
    RewardVoided,
    emit_first_booking_completed,
    emit_referral_code_issued,
    emit_referral_link_clicked,
    emit_referred_signup,
    emit_reward_pending,
    emit_reward_redeemed,
    emit_reward_unlocked,
    emit_reward_voided,
    register_listener,
    unregister_listener,
)

__all__ = [
    # Booking domain events
    "BookingCreated",
    "BookingCancelled",
    "BookingReminder",
    "BookingCompleted",
    "EventPublisher",
    # Referral events (existing)
    "ReferralEvents",
    "ReferralEvent",
    "ReferralCodeIssued",
    "ReferralLinkClicked",
    "ReferredSignup",
    "FirstBookingCompleted",
    "RewardPending",
    "RewardUnlocked",
    "RewardRedeemed",
    "RewardVoided",
    "ReferralEventListener",
    "emit_referral_code_issued",
    "emit_referral_link_clicked",
    "emit_referred_signup",
    "emit_first_booking_completed",
    "emit_reward_pending",
    "emit_reward_unlocked",
    "emit_reward_redeemed",
    "emit_reward_voided",
    "register_listener",
    "unregister_listener",
]
