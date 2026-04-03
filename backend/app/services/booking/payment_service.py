from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

from ...core.exceptions import NotFoundException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ..config_service import ConfigService
    from ..system_message_service import SystemMessageService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


def _is_mock_like(value: object) -> bool:
    return type(value).__module__.startswith("unittest.mock")


def _stripe_service_class() -> Any:
    booking_service_module = _booking_service_module()
    from .. import stripe_service as stripe_service_module

    facade_cls = booking_service_module.StripeService
    source_cls = stripe_service_module.StripeService
    if _is_mock_like(facade_cls):
        return facade_cls
    if _is_mock_like(source_cls):
        return source_cls
    return facade_cls


class BookingPaymentMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService
        system_message_service: SystemMessageService

        def transaction(self) -> ContextManager[None]:
            ...

        def log_operation(self, operation: str, **kwargs: Any) -> None:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

    def _determine_auth_timing(self, lesson_start_at: Any) -> Dict[str, Any]:
        """Determine authorization timing based on lesson start time."""
        booking_service_module = _booking_service_module()

        if lesson_start_at.tzinfo is None:
            lesson_start_at = lesson_start_at.replace(tzinfo=booking_service_module.timezone.utc)
        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        hours_until_lesson = (lesson_start_at - now).total_seconds() / 3600

        if hours_until_lesson >= 24:
            scheduled_for = lesson_start_at - booking_service_module.timedelta(hours=24)
            return {
                "immediate": False,
                "scheduled_for": scheduled_for,
                "initial_payment_status": PaymentStatus.SCHEDULED.value,
                "hours_until_lesson": hours_until_lesson,
            }

        return {
            "immediate": True,
            "scheduled_for": None,
            "initial_payment_status": PaymentStatus.SCHEDULED.value,
            "hours_until_lesson": hours_until_lesson,
        }

    @BaseService.measure_operation("confirm_booking_payment")
    def confirm_booking_payment(
        self,
        booking_id: str,
        student: User,
        payment_method_id: str,
        save_payment_method: bool = False,
    ) -> Booking:
        """Confirm payment method for a booking."""
        booking_service_module = _booking_service_module()

        self.log_operation("confirm_booking_payment", booking_id=booking_id, student_id=student.id)
        booking = self._load_confirm_payment_booking(booking_id, student)
        self._maybe_save_booking_payment_method(
            student_id=student.id,
            payment_method_id=payment_method_id,
            save_payment_method=save_payment_method,
            pricing_service=booking_service_module.PricingService(self.db),
        )
        schedule_ctx = self._schedule_booking_authorization(booking, payment_method_id)
        trigger_immediate_auth = schedule_ctx["trigger_immediate_auth"]
        immediate_auth_hours_until = schedule_ctx["immediate_auth_hours_until"]

        self.log_operation(
            "confirm_booking_payment_completed",
            booking_id=booking.id,
            payment_status=getattr(booking.payment_detail, "payment_status", None),
        )
        auth_result = self._execute_immediate_authorization_if_needed(
            booking_id=booking.id,
            trigger_immediate_auth=trigger_immediate_auth,
            immediate_auth_hours_until=immediate_auth_hours_until,
        )
        booking = self._reconcile_immediate_authorization_result(
            booking,
            trigger_immediate_auth=trigger_immediate_auth,
            auth_result=auth_result,
        )
        if booking.status != BookingStatus.CONFIRMED:
            return booking
        self._create_confirmation_system_message(booking)
        self._finalize_confirm_payment_side_effects(booking)
        return booking

    def _load_confirm_payment_booking(self, booking_id: str, student: User) -> Booking:
        booking = self.repository.get_booking_for_student(booking_id, student.id)
        if not booking:
            raise NotFoundException("Booking not found")
        if booking.status != BookingStatus.PENDING:
            raise NotFoundException("Booking not found")
        return booking

    def _maybe_save_booking_payment_method(
        self,
        *,
        student_id: str,
        payment_method_id: str,
        save_payment_method: bool,
        pricing_service: Any,
    ) -> None:
        if not save_payment_method:
            return
        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        stripe_service.save_payment_method(
            user_id=student_id,
            payment_method_id=payment_method_id,
            set_as_default=False,
        )

    def _resolve_reschedule_auth_context(self, booking: Booking) -> Dict[str, Any]:
        booking_service_module = _booking_service_module()
        is_gaming_reschedule = False
        hours_from_original: Optional[float] = None
        reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
        original_lesson_datetime = (
            reschedule_record.original_lesson_datetime if reschedule_record else None
        )
        if booking.rescheduled_from_booking_id and original_lesson_datetime:
            original_dt = original_lesson_datetime
            if original_dt.tzinfo is None:
                original_dt = original_dt.replace(tzinfo=booking_service_module.timezone.utc)
            reschedule_time = booking.created_at
            if reschedule_time is not None:
                if reschedule_time.tzinfo is None:
                    reschedule_time = reschedule_time.replace(
                        tzinfo=booking_service_module.timezone.utc
                    )
                hours_from_original = (original_dt - reschedule_time).total_seconds() / 3600
                is_gaming_reschedule = hours_from_original is not None and hours_from_original < 24
        return {
            "is_gaming_reschedule": is_gaming_reschedule,
            "hours_from_original": hours_from_original,
        }

    def _schedule_booking_authorization(
        self,
        booking: Booking,
        payment_method_id: str,
    ) -> Dict[str, Any]:
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()
        trigger_immediate_auth = False
        immediate_auth_hours_until: Optional[float] = None
        with self.transaction():
            bp = self.repository.ensure_payment(booking.id)
            bp.payment_method_id = payment_method_id
            bp.payment_status = PaymentStatus.SCHEDULED.value

            booking_start_utc = self._get_booking_start_utc(booking)
            auth_timing = self._determine_auth_timing(booking_start_utc)
            hours_until_lesson = auth_timing["hours_until_lesson"]
            reschedule_ctx = self._resolve_reschedule_auth_context(booking)
            payment_repo = PaymentRepository(self.db)

            if reschedule_ctx["is_gaming_reschedule"] or auth_timing["immediate"]:
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
                bp.auth_last_error = None
                bp.auth_failure_count = 0
                trigger_immediate_auth = True
                immediate_auth_hours_until = hours_until_lesson
                event_data = {
                    "payment_method_id": payment_method_id,
                    "hours_until_lesson": hours_until_lesson,
                    "scheduled_for": "immediate",
                }
                if reschedule_ctx["is_gaming_reschedule"]:
                    event_data["hours_from_original"] = reschedule_ctx["hours_from_original"]
                    event_data["reason"] = "gaming_reschedule"
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_immediate",
                    event_data=event_data,
                )
            else:
                auth_time = auth_timing["scheduled_for"]
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = auth_time
                bp.auth_last_error = None
                bp.auth_failure_count = 0
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_scheduled",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "scheduled_for": auth_time.isoformat() if auth_time else None,
                        "hours_until_lesson": hours_until_lesson,
                    },
                )

            if not trigger_immediate_auth:
                booking.mark_confirmed(
                    confirmed_at=booking_service_module.datetime.now(
                        booking_service_module.timezone.utc
                    )
                )
            else:
                booking.mark_pending(confirmed_at=None)
        return {
            "trigger_immediate_auth": trigger_immediate_auth,
            "immediate_auth_hours_until": immediate_auth_hours_until,
        }

    def _execute_immediate_authorization_if_needed(
        self,
        *,
        booking_id: str,
        trigger_immediate_auth: bool,
        immediate_auth_hours_until: Optional[float],
    ) -> Optional[Dict[str, Any]]:
        if not trigger_immediate_auth:
            return None
        try:
            from app.tasks.payment_tasks import _process_authorization_for_booking

            auth_result = _process_authorization_for_booking(
                booking_id, immediate_auth_hours_until or 0.0
            )
            if not auth_result or not auth_result.get("success"):
                logger.warning(
                    "Immediate auth failed for gaming reschedule booking %s: %s",
                    booking_id,
                    auth_result.get("error") if auth_result else "unknown error",
                )
            return cast(Optional[Dict[str, Any]], auth_result)
        except Exception as exc:
            logger.error(
                "Immediate auth error for gaming reschedule booking %s: %s",
                booking_id,
                exc,
            )
            return None

    def _reconcile_immediate_authorization_result(
        self,
        booking: Booking,
        *,
        trigger_immediate_auth: bool,
        auth_result: Optional[Dict[str, Any]],
    ) -> Booking:
        booking_service_module = _booking_service_module()
        if auth_result and auth_result.get("success"):
            try:
                with self.transaction():
                    refreshed = self.repository.get_by_id(booking.id)
                    if refreshed and refreshed.status == BookingStatus.PENDING:
                        refreshed.mark_confirmed(
                            confirmed_at=booking_service_module.datetime.now(
                                booking_service_module.timezone.utc
                            )
                        )
                        refreshed_bp = self.repository.ensure_payment(refreshed.id)
                        if refreshed_bp.payment_status == PaymentStatus.SCHEDULED.value:
                            refreshed_bp.payment_status = PaymentStatus.AUTHORIZED.value
                self.repository.refresh(booking)
            except Exception:
                logger.warning(
                    "Booking %s was updated after immediate authorization, but ORM refresh failed",
                    booking.id,
                    exc_info=True,
                )
        elif trigger_immediate_auth:
            try:
                self.repository.refresh(booking)
            except Exception:
                logger.warning(
                    "Failed to refresh booking %s after immediate authorization attempt",
                    booking.id,
                    exc_info=True,
                )
        return booking

    def _create_confirmation_system_message(self, booking: Booking) -> None:
        try:
            service_name = "Lesson"
            if booking.instructor_service and booking.instructor_service.name:
                service_name = booking.instructor_service.name
            if booking.rescheduled_from_booking_id:
                old_booking = self.repository.get_by_id(booking.rescheduled_from_booking_id)
                if old_booking:
                    self.system_message_service.create_booking_rescheduled_message(
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        booking_id=booking.id,
                        old_date=old_booking.booking_date,
                        old_time=old_booking.start_time,
                        new_date=booking.booking_date,
                        new_time=booking.start_time,
                    )
                    return
            self.system_message_service.create_booking_created_message(
                student_id=booking.student_id,
                instructor_id=booking.instructor_id,
                booking_id=booking.id,
                service_name=service_name,
                booking_date=booking.booking_date,
                start_time=booking.start_time,
            )
        except Exception as exc:
            logger.error(
                "Failed to create system message for booking %s: %s",
                booking.id,
                str(exc),
            )

    def _finalize_confirm_payment_side_effects(self, booking: Booking) -> None:
        try:
            self._invalidate_booking_caches(booking)
        except Exception:
            logger.debug(
                "Failed to invalidate booking caches after confirmation for booking %s",
                booking.id,
                exc_info=True,
            )
