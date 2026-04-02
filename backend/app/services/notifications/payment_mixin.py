from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...core.constants import BRAND_NAME
from ...models.booking import Booking
from ...repositories.user_repository import UserRepository
from ..base import BaseService
from ..email import EmailService
from ..sms_service import SMSService
from ..sms_templates import PAYMENT_FAILED
from ..template_registry import TemplateRegistry
from ..template_service import TemplateService
from .mixin_base import NotificationMixinBase


class NotificationPaymentMixin(NotificationMixinBase):
    """Payment failure, warning, cancellation, and payout emails."""

    if TYPE_CHECKING:
        logger: logging.Logger
        email_service: EmailService
        sms_service: SMSService | None
        template_service: TemplateService
        user_repository: UserRepository
        frontend_url: str

    def _resolve_payment_failure_recipients(self, booking: Booking) -> tuple[bool, bool]:
        student_id = getattr(booking, "student_id", None)
        instructor_id = getattr(booking, "instructor_id", None)
        send_student = True
        send_instructor = True

        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_cancelled_payment_failed_student"
        ):
            send_student = False
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_cancelled_payment_failed_instructor"
        ):
            send_instructor = False
        return send_student, send_instructor

    def _render_payment_cancelled_templates(
        self, booking: Booking, context: dict[str, object]
    ) -> tuple[str, str]:
        html_student = None
        html_instructor = None

        try:
            if self.template_service.template_exists(
                "email/booking/cancelled_payment_failed_student.html"
            ):
                html_student = self.template_service.render_template(
                    "email/booking/cancelled_payment_failed_student.html", context
                )
        except Exception:
            html_student = None

        try:
            if self.template_service.template_exists(
                "email/booking/cancelled_payment_failed_instructor.html"
            ):
                html_instructor = self.template_service.render_template(
                    "email/booking/cancelled_payment_failed_instructor.html", context
                )
        except Exception:
            html_instructor = None

        if not html_student:
            fallback_student = (
                "<p>Your upcoming lesson was cancelled because we couldn't authorize the payment after multiple attempts.</p>"
                "<p>Please update your payment method to avoid future cancellations.</p>"
                f"<p><a href='{self.frontend_url}/student/payments'>Update payment method</a></p>"
            )
            html_student = self.template_service.render_string(fallback_student, context)

        if not html_instructor:
            fallback_instructor = "<p>The upcoming lesson was cancelled because the student's payment could not be authorized after multiple attempts.</p>"
            html_instructor = self.template_service.render_string(fallback_instructor, context)

        return html_student, html_instructor

    def _send_payment_cancelled_emails(
        self,
        booking: Booking,
        *,
        subject: str,
        send_student: bool,
        send_instructor: bool,
        html_student: str,
        html_instructor: str,
    ) -> None:
        if (
            send_student
            and getattr(booking, "student", None)
            and getattr(booking.student, "email", None)
        ):
            self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_student,
            )

        if (
            send_instructor
            and getattr(booking, "instructor", None)
            and getattr(booking.instructor, "email", None)
        ):
            self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_instructor,
            )

    @BaseService.measure_operation("send_booking_cancelled_payment_failed")
    def send_booking_cancelled_payment_failed(self, booking: Booking) -> bool:
        """
        Notify student and instructor that a booking was cancelled due to repeated payment authorization failures.
        """
        try:
            send_student, send_instructor = self._resolve_payment_failure_recipients(booking)
            if not send_student and not send_instructor:
                return True

            subject = "Booking Cancelled: Payment Authorization Failed"
            context = {
                "booking": booking,
                "subject": subject,
                "update_payment_url": f"{self.frontend_url}/student/payments",
            }
            html_student, html_instructor = self._render_payment_cancelled_templates(
                booking, context
            )
            self._send_payment_cancelled_emails(
                booking,
                subject=subject,
                send_student=send_student,
                send_instructor=send_instructor,
                html_student=html_student,
                html_instructor=html_instructor,
            )
            self.logger.info(
                "Sent payment-failure cancellation notifications for booking %s",
                getattr(booking, "id", "unknown"),
            )
            return True
        except Exception as exc:
            self.logger.error(
                "Failed to send payment-failure cancellation notifications for booking %s: %s",
                getattr(booking, "id", "unknown"),
                exc,
            )
            return False

    @BaseService.measure_operation("send_payment_failed_notification")
    def send_payment_failed_notification(self, booking: Booking) -> bool:
        """Always-on payment failure notice to the student (email + optional SMS)."""
        student_id = getattr(booking, "student_id", None)
        if not student_id:
            return False

        student = self.user_repository.get_by_id(student_id)
        if not student or not getattr(student, "email", None):
            self.logger.warning(
                "Payment failed notification skipped: student not found (%s)", student_id
            )
            return False

        instructor_name = "your instructor"
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id:
            instructor = self.user_repository.get_by_id(instructor_id)
            if instructor:
                instructor_name = instructor.first_name or instructor.email or instructor_name

        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")
        payment_url = f"{self.frontend_url}/student/payments"
        context = {
            "user_name": student.first_name or student.email,
            "service_name": booking.service_name or "your lesson",
            "instructor_name": instructor_name,
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "payment_url": payment_url,
        }

        email_sent = False
        try:
            html_content = self.template_service.render_template(
                TemplateRegistry.PAYMENT_FAILED, context
            )
            self.email_service.send_email(
                to_email=student.email,
                subject="Payment failed for your upcoming lesson",
                html_content=html_content,
                template=TemplateRegistry.PAYMENT_FAILED,
            )
            email_sent = True
            self.logger.info("Payment failed email sent to %s", student.email)
        except Exception as exc:
            self.logger.error("Failed to send payment failed email to %s: %s", student.email, exc)

        sms_sent = False
        sms_service = self.sms_service
        if sms_service and getattr(student, "phone_verified", False):
            try:
                sms_message = self._render_sms_template(
                    PAYMENT_FAILED,
                    service_name=booking.service_name or "your lesson",
                    instructor_name=instructor_name,
                    date=formatted_date,
                    payment_url=payment_url,
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to render payment failed SMS for %s: %s", student_id, exc
                )
            else:

                async def _send_sms() -> None:
                    await sms_service.send_to_user(
                        user_id=student_id,
                        message=sms_message,
                        user_repository=self.user_repository,
                    )

                self._run_async_task(_send_sms, f"sending payment failed SMS to {student_id}")
                sms_sent = True

        return email_sent or sms_sent

    @BaseService.measure_operation("send_final_payment_warning")
    def send_final_payment_warning(self, booking: Booking, hours_until_lesson: float) -> bool:
        """
        Send an urgent T-24 authorization failure email asking the student to update their card.
        """
        try:
            student_id = getattr(booking, "student_id", None)
            if student_id and not self._should_send_email(
                student_id, "lesson_updates", "final_payment_warning"
            ):
                return True

            subject = "Action required: Update your payment method for your upcoming lesson"
            template_name = "email/payment/t24_update_card.html"
            context = {
                "booking": booking,
                "hours_until_lesson": round(hours_until_lesson, 1),
                "update_payment_url": f"{self.frontend_url}/student/payments",
            }

            html_content = None
            try:
                if self.template_service.template_exists(template_name):
                    html_content = self.template_service.render_template(template_name, context)
            except Exception:
                html_content = None

            if not html_content:
                local_dt = self._get_booking_local_datetime(booking)
                formatted_date = local_dt.strftime("%B %d, %Y")
                formatted_time = local_dt.strftime("%-I:%M %p")
                fallback = (
                    "<p>We couldn't authorize your payment for your upcoming lesson. "
                    "Please update your card on file to avoid cancellation.</p>"
                    f"<p>Lesson: {booking.service_name} on {formatted_date} at {formatted_time}</p>"
                    f"<p><a href='{self.frontend_url}/student/payments'>Update payment method</a></p>"
                )
                html_content = self.template_service.render_string(fallback, context)

            self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content,
            )
            self.logger.info("Sent T-24 payment warning to student for booking %s", booking.id)
            return True
        except Exception as exc:
            self.logger.error(
                "Failed to send T-24 payment warning for booking %s: %s", booking.id, exc
            )
            return False

    @BaseService.measure_operation("send_payout_notification")
    def send_payout_notification(
        self,
        instructor_id: str,
        amount_cents: int,
        payout_date: object,
    ) -> bool:
        """Send a payout confirmation email to an instructor (always-on)."""
        user = self.user_repository.get_by_id(instructor_id)
        if not user or not getattr(user, "email", None):
            self.logger.warning("Payout notification skipped: user not found (%s)", instructor_id)
            return False

        amount_usd = amount_cents / 100.0
        context = {
            "user_name": user.first_name or user.email,
            "amount": f"${amount_usd:,.2f}",
            "amount_cents": amount_cents,
            "payout_date": payout_date,
        }
        try:
            html_content = self.template_service.render_template(
                TemplateRegistry.PAYOUT_SENT, context
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=f"Your {BRAND_NAME} payout is on the way!",
                html_content=html_content,
                template=TemplateRegistry.PAYOUT_SENT,
            )
            self.logger.info(
                "Payout notification sent to %s (amount_cents=%s)",
                user.email,
                amount_cents,
            )
            return True
        except Exception as exc:
            self.logger.error("Failed to send payout notification to %s: %s", user.email, exc)
            return False
