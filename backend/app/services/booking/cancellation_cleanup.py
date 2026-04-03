from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, cast

from ...models.booking import Booking, BookingStatus, PaymentStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...events import EventPublisher
    from ...integrations.hundredms_client import HundredMsClient
    from ..system_message_service import SystemMessageService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingCancellationCleanupMixin:
    if TYPE_CHECKING:
        db: Session
        event_publisher: EventPublisher
        system_message_service: SystemMessageService

        def _send_cancellation_notifications(
            self,
            booking: Booking,
            cancelled_by_role: str,
        ) -> None:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

    def _mark_video_session_terminal_on_cancellation(self, booking: Booking) -> None:
        """Mark booking video session state as terminal on cancellation."""
        booking_service_module = _booking_service_module()

        video_session = getattr(booking, "video_session", None)
        if video_session is None:
            return

        ended_at = booking.cancelled_at or booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        if video_session.session_ended_at is None:
            video_session.session_ended_at = ended_at

        if (
            video_session.session_duration_seconds is None
            and isinstance(video_session.session_started_at, booking_service_module.datetime)
            and isinstance(video_session.session_ended_at, booking_service_module.datetime)
        ):
            duration_seconds = int(
                (video_session.session_ended_at - video_session.session_started_at).total_seconds()
            )
            video_session.session_duration_seconds = max(duration_seconds, 0)

    def _build_hundredms_client_for_cleanup(self) -> HundredMsClient | None:
        """Create a 100ms client for post-cancellation cleanup, when configured."""
        booking_service_module = _booking_service_module()
        config = booking_service_module.settings

        if not config.hundredms_enabled:
            return None

        access_key = (config.hundredms_access_key or "").strip()
        raw_secret = config.hundredms_app_secret
        if raw_secret is None:
            if config.site_mode == "prod":
                raise RuntimeError("HUNDREDMS_APP_SECRET is required in production")
            app_secret = str()
        elif hasattr(raw_secret, "get_secret_value"):
            app_secret = str(raw_secret.get_secret_value()).strip()
        else:
            app_secret = str(raw_secret).strip()

        if not access_key or not app_secret:
            logger.warning(
                "Skipping 100ms room disable for cancellation cleanup due to missing credentials"
            )
            return None

        client = booking_service_module.HundredMsClient(
            access_key=access_key,
            app_secret=app_secret,
            base_url=config.hundredms_base_url,
            template_id=(config.hundredms_template_id or "").strip() or None,
        )
        return cast("HundredMsClient", client)

    def _disable_video_room_after_cancellation(self, booking: Booking) -> None:
        """Best-effort 100ms room disable after cancellation commit."""
        booking_service_module = _booking_service_module()

        video_session = getattr(booking, "video_session", None)
        room_id = getattr(video_session, "room_id", None)
        if not room_id:
            return

        client = self._build_hundredms_client_for_cleanup()
        if client is None:
            return

        try:
            client.disable_room(room_id)
        except booking_service_module.HundredMsError as exc:
            logger.warning(
                "Best-effort 100ms room disable failed for booking %s room %s: %s",
                booking.id,
                room_id,
                exc.message,
                extra={"status_code": exc.status_code},
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error during 100ms room disable for booking %s room %s: %s",
                booking.id,
                room_id,
                exc,
            )

    def _was_ever_confirmed(self, booking: Booking) -> bool:
        """Return whether the booking ever reached a confirmed state."""
        return booking.confirmed_at is not None

    def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
        """Post-transaction actions for cancellation."""
        booking_service_module = _booking_service_module()

        if booking.status == BookingStatus.PAYMENT_FAILED:
            logger.info(
                "Skipping cancellation side effects for payment-failed booking %s",
                booking.id,
            )
        else:
            try:
                self.event_publisher.publish(
                    booking_service_module.BookingCancelled(
                        booking_id=booking.id,
                        cancelled_by=cancelled_by_role,
                        cancelled_at=booking.cancelled_at
                        or booking_service_module.datetime.now(booking_service_module.timezone.utc),
                        refund_amount=None,
                    )
                )
            except Exception as e:
                logger.error("Failed to send cancellation notification event: %s", str(e))

            if self._was_ever_confirmed(booking):
                try:
                    self.system_message_service.create_booking_cancelled_message(
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        booking_id=booking.id,
                        booking_date=booking.booking_date,
                        start_time=booking.start_time,
                        cancelled_by=cancelled_by_role,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to create cancellation system message for booking %s: %s",
                        booking.id,
                        str(e),
                    )

                self._send_cancellation_notifications(booking, cancelled_by_role)
            else:
                logger.info(
                    "Skipping user-facing cancellation notifications for never-confirmed booking %s",
                    booking.id,
                )
        self._invalidate_booking_caches(booking)

        refund_hook_outcomes = {
            "student_cancel_gt24_no_charge",
            "instructor_cancel_full_refund",
            "instructor_no_show_full_refund",
            "student_wins_dispute_full_refund",
            "admin_refund",
        }
        pd = booking.payment_detail
        if (pd is not None and pd.payment_status == PaymentStatus.SETTLED.value) and (
            pd is not None and pd.settlement_outcome in refund_hook_outcomes
        ):
            try:
                credit_service = booking_service_module.StudentCreditService(self.db)
                credit_service.process_refund_hooks(booking=booking)
            except Exception as exc:
                logger.error(
                    "Failed to adjust student credits for cancelled booking %s: %s",
                    booking.id,
                    exc,
                )

        self._disable_video_room_after_cancellation(booking)
