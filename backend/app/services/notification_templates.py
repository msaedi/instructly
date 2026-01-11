from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .template_registry import TemplateRegistry


@dataclass(frozen=True)
class NotificationTemplate:
    category: str
    type: str
    title: str
    body_template: str
    url_template: Optional[str] = None
    email_template: TemplateRegistry | None = None
    email_subject_template: Optional[str] = None


# Instructor templates
INSTRUCTOR_BOOKING_CONFIRMED = NotificationTemplate(
    category="lesson_updates",
    type="booking_confirmed",
    title="New Booking!",
    body_template="{student_name} booked {service_name} for {date} at {time}",
    url_template="/instructor/dashboard?panel=bookings",
    email_template=TemplateRegistry.BOOKING_CONFIRMATION_INSTRUCTOR,
    email_subject_template="New booking: {service_name} with {student_name}",
)

INSTRUCTOR_BOOKING_CANCELLED = NotificationTemplate(
    category="lesson_updates",
    type="booking_cancelled",
    title="Booking Cancelled",
    body_template="{student_name} cancelled their {service_name} for {date}",
    url_template="/instructor/dashboard?panel=bookings",
    email_template=TemplateRegistry.BOOKING_CANCELLATION_INSTRUCTOR,
    email_subject_template="Booking cancelled: {service_name}",
)

INSTRUCTOR_REMINDER_24H = NotificationTemplate(
    category="lesson_updates",
    type="booking_reminder_24h",
    title="Lesson Tomorrow",
    body_template="Reminder: {service_name} with {student_name} tomorrow at {time}",
    url_template="/instructor/dashboard?panel=bookings",
    email_template=TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR,
    email_subject_template="Reminder: {service_name} tomorrow",
)

INSTRUCTOR_REMINDER_1H = NotificationTemplate(
    category="lesson_updates",
    type="booking_reminder_1h",
    title="Lesson in 1 Hour",
    body_template="Reminder: {service_name} with {student_name} in 1 hour",
    url_template="/instructor/dashboard?panel=bookings",
    email_template=TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR,
    email_subject_template="Reminder: {service_name} in 1 hour",
)

INSTRUCTOR_NEW_REVIEW = NotificationTemplate(
    category="lesson_updates",
    type="new_review",
    title="New Review!",
    body_template="{student_name} left a {rating}-star review",
    url_template="/instructor/dashboard?panel=reviews",
)

INSTRUCTOR_PAYOUT = NotificationTemplate(
    category="lesson_updates",
    type="payout_completed",
    title="Payout Sent",
    body_template="${amount} has been sent to your bank account",
    url_template="/instructor/dashboard?panel=earnings",
)

# Student templates
STUDENT_BOOKING_CONFIRMED = NotificationTemplate(
    category="lesson_updates",
    type="booking_confirmed",
    title="Booking Confirmed!",
    body_template="Your {service_name} with {instructor_name} is confirmed for {date}",
    url_template="/student/bookings",
    email_template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
    email_subject_template="Booking confirmed: {service_name} with {instructor_name}",
)

STUDENT_BOOKING_CANCELLED = NotificationTemplate(
    category="lesson_updates",
    type="booking_cancelled",
    title="Lesson Cancelled",
    body_template="{instructor_name} cancelled your {service_name} for {date}",
    url_template="/student/bookings",
    email_template=TemplateRegistry.BOOKING_CANCELLATION_STUDENT,
    email_subject_template="Lesson cancelled: {service_name}",
)

STUDENT_REMINDER_24H = NotificationTemplate(
    category="lesson_updates",
    type="booking_reminder_24h",
    title="Lesson Tomorrow",
    body_template="Reminder: {service_name} with {instructor_name} tomorrow at {time}",
    url_template="/student/bookings",
    email_template=TemplateRegistry.BOOKING_REMINDER_STUDENT,
    email_subject_template="Reminder: {service_name} tomorrow",
)

STUDENT_REMINDER_1H = NotificationTemplate(
    category="lesson_updates",
    type="booking_reminder_1h",
    title="Lesson in 1 Hour",
    body_template="Reminder: {service_name} with {instructor_name} in 1 hour",
    url_template="/student/bookings",
    email_template=TemplateRegistry.BOOKING_REMINDER_STUDENT,
    email_subject_template="Reminder: {service_name} in 1 hour",
)

STUDENT_REVIEW_RESPONSE = NotificationTemplate(
    category="lesson_updates",
    type="review_response",
    title="Review Response",
    body_template="{instructor_name} responded to your review",
    url_template="/student/bookings",
)


def render_notification(template: NotificationTemplate, **kwargs: Any) -> dict[str, Any]:
    """Render a notification template with provided values."""
    body = template.body_template.format(**kwargs)
    url = template.url_template.format(**kwargs) if template.url_template else None

    data: dict[str, Any] = dict(kwargs)
    if url:
        data["url"] = url

    return {
        "category": template.category,
        "type": template.type,
        "title": template.title,
        "body": body,
        "data": data if data else None,
    }


__all__ = [
    "NotificationTemplate",
    "INSTRUCTOR_BOOKING_CONFIRMED",
    "INSTRUCTOR_BOOKING_CANCELLED",
    "INSTRUCTOR_REMINDER_24H",
    "INSTRUCTOR_REMINDER_1H",
    "INSTRUCTOR_NEW_REVIEW",
    "INSTRUCTOR_PAYOUT",
    "STUDENT_BOOKING_CONFIRMED",
    "STUDENT_BOOKING_CANCELLED",
    "STUDENT_REMINDER_24H",
    "STUDENT_REMINDER_1H",
    "STUDENT_REVIEW_RESPONSE",
    "render_notification",
]
