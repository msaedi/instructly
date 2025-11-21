"""
Template registry for strongly-typed access to Jinja templates.

Use with TemplateService to avoid stringly-typed paths.
"""

from enum import Enum
from typing import Final


class TemplateRegistry(str, Enum):
    # Auth / Account
    AUTH_PASSWORD_RESET = "email/auth/password_reset.html"
    AUTH_PASSWORD_RESET_CONFIRMATION = "email/auth/password_reset_confirmation.html"
    AUTH_WELCOME = "email/auth/welcome.html"

    # Referrals
    REFERRALS_INVITE = "email/referrals/invite.html"
    REFERRALS_INVITE_STANDALONE = "email/referrals/invite_standalone.html"

    # Beta invites
    BETA_INVITE = "email/beta/invite.html"

    # Booking notifications
    BOOKING_CONFIRMATION_INSTRUCTOR = "email/booking/confirmation_instructor.html"
    BOOKING_CONFIRMATION_STUDENT = "email/booking/confirmation_student.html"
    BOOKING_CANCELLATION_INSTRUCTOR = "email/booking/cancellation_instructor.html"
    BOOKING_CANCELLATION_STUDENT = "email/booking/cancellation_student.html"
    BOOKING_CANCELLATION_CONFIRMATION_INSTRUCTOR = (
        "email/booking/cancellation_confirmation_instructor.html"
    )
    BOOKING_CANCELLATION_CONFIRMATION_STUDENT = (
        "email/booking/cancellation_confirmation_student.html"
    )
    BOOKING_NEW_MESSAGE = "email/booking/new_message.html"
    BOOKING_REMINDER_INSTRUCTOR = "email/booking/reminder_instructor.html"
    BOOKING_REMINDER_STUDENT = "email/booking/reminder_student.html"

    # Background checks
    BGC_REVIEW_STATUS = "email/bgc/review_status.jinja"
    BGC_FINAL_ADVERSE = "email/bgc/final_adverse.jinja"
    BGC_EXPIRY_RECHECK = "email/bgc/expiry_recheck.jinja"


_TEMPLATE_DEFAULT_SENDERS: Final[dict[TemplateRegistry, str]] = {
    TemplateRegistry.AUTH_PASSWORD_RESET: "account",
    TemplateRegistry.AUTH_PASSWORD_RESET_CONFIRMATION: "account",
    TemplateRegistry.AUTH_WELCOME: "account",
    TemplateRegistry.BETA_INVITE: "account",
    TemplateRegistry.REFERRALS_INVITE: "referrals",
    TemplateRegistry.REFERRALS_INVITE_STANDALONE: "referrals",
    TemplateRegistry.BOOKING_CONFIRMATION_INSTRUCTOR: "bookings",
    TemplateRegistry.BOOKING_CONFIRMATION_STUDENT: "bookings",
    TemplateRegistry.BOOKING_CANCELLATION_INSTRUCTOR: "bookings",
    TemplateRegistry.BOOKING_CANCELLATION_STUDENT: "bookings",
    TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_INSTRUCTOR: "bookings",
    TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_STUDENT: "bookings",
    TemplateRegistry.BOOKING_NEW_MESSAGE: "bookings",
    TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR: "bookings",
    TemplateRegistry.BOOKING_REMINDER_STUDENT: "bookings",
    TemplateRegistry.BGC_REVIEW_STATUS: "trust",
    TemplateRegistry.BGC_FINAL_ADVERSE: "trust",
    TemplateRegistry.BGC_EXPIRY_RECHECK: "trust",
}


def get_default_sender_key(template: TemplateRegistry) -> str | None:
    """Return the configured default sender key for a template, if any."""

    return _TEMPLATE_DEFAULT_SENDERS.get(template)
