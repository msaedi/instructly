"""SMS message templates for short notification content."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SMSTemplate:
    category: str
    template: str


BOOKING_CONFIRMED_INSTRUCTOR = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: New booking! {student_name} booked {service_name} on {date} at {time}.",
)

BOOKING_CONFIRMED_STUDENT = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: Booking confirmed! {service_name} with {instructor_name} on {date} at {time}.",
)

BOOKING_CANCELLED_INSTRUCTOR = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: {student_name} cancelled {service_name} on {date}.",
)

BOOKING_CANCELLED_STUDENT = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: Your {service_name} lesson on {date} was cancelled by the instructor.",
)

REMINDER_24H = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: Reminder - {service_name} tomorrow at {time} with {other_party_name}.",
)

REMINDER_1H = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: {service_name} starts in 1 hour with {other_party_name}!",
)

NEW_REVIEW = SMSTemplate(
    category="lesson_updates",
    template="InstaInstru: You received a new {rating}-star review from {student_name}!",
)

BOOKING_NEW_MESSAGE = SMSTemplate(
    category="messages",
    template="InstaInstru: New message from {sender_name} about {service_name}. {message_preview}",
)

SECURITY_NEW_DEVICE_LOGIN = SMSTemplate(
    category="system_updates",
    template=(
        "InstaInstru: New login detected. If this wasn't you, secure your account at "
        "{security_url}."
    ),
)

SECURITY_PASSWORD_CHANGED = SMSTemplate(
    category="system_updates",
    template=(
        "InstaInstru: Your password was just changed. If this wasn't you, reset it at "
        "{reset_url}."
    ),
)


def render_sms(template: SMSTemplate, **kwargs: str) -> str:
    """Render SMS template with provided values."""
    try:
        return template.template.format(**kwargs)
    except KeyError as exc:
        raise ValueError(f"Missing template variable: {exc}") from exc


__all__ = [
    "SMSTemplate",
    "BOOKING_CONFIRMED_INSTRUCTOR",
    "BOOKING_CONFIRMED_STUDENT",
    "BOOKING_CANCELLED_INSTRUCTOR",
    "BOOKING_CANCELLED_STUDENT",
    "REMINDER_24H",
    "REMINDER_1H",
    "NEW_REVIEW",
    "BOOKING_NEW_MESSAGE",
    "SECURITY_NEW_DEVICE_LOGIN",
    "SECURITY_PASSWORD_CHANGED",
    "render_sms",
]
