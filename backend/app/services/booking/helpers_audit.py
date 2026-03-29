from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, Optional

from ...models.audit_log import AuditLog
from ...models.booking import Booking, BookingStatus
from ...models.user import User
from ..audit_redaction import redact
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...models.booking_transfer import BookingTransfer
    from ...repositories.audit_repository import AuditRepository
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.event_outbox_repository import EventOutboxRepository
    from ..cache_service import CacheServiceSyncAdapter
    from ..pricing_service import PricingService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingAuditCacheMixin:
    if TYPE_CHECKING:
        db: Session
        pricing_service: PricingService
        repository: BookingRepository
        event_outbox_repository: EventOutboxRepository
        audit_repository: AuditRepository
        cache_service: Optional[CacheServiceSyncAdapter]

        def _resolve_actor_payload(
            self,
            actor: Any | None,
            default_role: str = "system",
        ) -> dict[str, Any]:
            ...

    def _maybe_refresh_instructor_tier(self, instructor_user_id: str, booking_id: str) -> None:
        if not instructor_user_id:
            return

        try:
            self.pricing_service.evaluate_and_persist_instructor_tier(
                instructor_user_id=str(instructor_user_id)
            )
        except Exception as exc:
            logger.error(
                "Failed refreshing instructor tier after booking completion %s: %s",
                booking_id,
                exc,
                exc_info=True,
            )

    def _get_transfer_record(self, booking_id: str) -> BookingTransfer | None:
        """Return booking transfer satellite row when present."""
        return self.repository.get_transfer_by_booking_id(booking_id)

    def _ensure_transfer_record(self, booking_id: str) -> BookingTransfer:
        """Get or create booking transfer satellite row."""
        return self.repository.ensure_transfer(booking_id)

    def _booking_event_identity(self, booking: Booking, event_type: str) -> tuple[str, str]:
        """Return idempotency key and version for a booking domain event."""
        booking_service_module = _booking_service_module()
        timestamp = booking.created_at or booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        if event_type == "booking.cancelled" and booking.cancelled_at:
            timestamp = booking.cancelled_at
        elif event_type == "booking.completed" and booking.completed_at:
            timestamp = booking.completed_at
        elif booking.updated_at:
            timestamp = booking.updated_at

        ts = timestamp.astimezone(booking_service_module.timezone.utc)
        version = ts.isoformat()
        key = f"booking:{booking.id}:{event_type}:{version}"
        return key, version

    def _serialize_booking_event_payload(
        self, booking: Booking, event_type: str, version: str
    ) -> dict[str, Any]:
        """Build JSON-safe payload for outbox events."""
        return {
            "booking_id": booking.id,
            "event_type": event_type,
            "version": version,
            "status": booking.status.value
            if isinstance(booking.status, BookingStatus)
            else str(booking.status),
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "booking_date": booking.booking_date.isoformat() if booking.booking_date else None,
            "start_time": booking.start_time.isoformat() if booking.start_time else None,
            "end_time": booking.end_time.isoformat() if booking.end_time else None,
            "total_price": str(booking.total_price),
            "created_at": booking.created_at.isoformat() if booking.created_at else None,
            "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
            "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
            "completed_at": booking.completed_at.isoformat() if booking.completed_at else None,
        }

    def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
        """Persist an outbox entry for the given booking event inside the current transaction."""
        self.repository.flush()  # Ensure timestamps are populated before computing identity
        idempotency_key, version = self._booking_event_identity(booking, event_type)
        payload = self._serialize_booking_event_payload(booking, event_type, version)
        self.event_outbox_repository.enqueue(
            event_type=event_type,
            aggregate_id=booking.id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def _snapshot_booking(self, booking: Booking) -> dict[str, Any]:
        """Return a redacted snapshot of a booking suitable for audit logging."""
        data = booking.to_dict()
        status_value = data.get("status")
        if isinstance(status_value, BookingStatus):
            data["status"] = status_value.value
        return redact(data) or {}

    def _write_booking_audit(
        self,
        booking: Booking,
        action: str,
        *,
        actor: Any | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        default_role: str = "system",
    ) -> None:
        """Persist an audit row capturing the change."""
        actor_payload = self._resolve_actor_payload(actor, default_role=default_role)
        audit_entry = AuditLog.from_change(
            entity_type="booking",
            entity_id=booking.id,
            action=action,
            actor=actor_payload,
            before=before,
            after=after,
        )
        booking_service_module = _booking_service_module()
        if booking_service_module.AUDIT_ENABLED:
            self.audit_repository.write(audit_entry)
            try:
                normalized_action = action.lower()
                if "cancel" in normalized_action:
                    audit_action = "booking.cancel"
                elif "complete" in normalized_action:
                    audit_action = "booking.complete"
                elif normalized_action == "create":
                    audit_action = "booking.create"
                else:
                    audit_action = f"booking.{action}"
                    if normalized_action == "status_change" and isinstance(after, dict):
                        status_value = after.get("status")
                        if status_value:
                            normalized_status = str(status_value).lower()
                            if normalized_status in {"completed", "complete"}:
                                audit_action = "booking.complete"
                            elif normalized_status in {"cancelled", "canceled"}:
                                audit_action = "booking.cancel"

                booking_service_module.AuditService(self.db).log_changes(
                    action=audit_action,
                    resource_type="booking",
                    resource_id=booking.id,
                    old_values=before,
                    new_values=after,
                    actor=actor if isinstance(actor, User) else None,
                    actor_type="user" if actor is not None else "system",
                    actor_id=actor_payload.get("id") if actor is not None else None,
                    description=f"Booking {action}",
                    metadata={"legacy_action": action},
                )
            except Exception:
                logger.debug(
                    "Failed to write booking audit trail for booking %s",
                    booking.id,
                    exc_info=True,
                )

    @BaseService.measure_operation("invalidate_booking_cache")
    def invalidate_booking_cache(self, booking_or_id: Booking | str) -> None:
        """Invalidate cached booking data for a specific booking."""
        target_booking: Optional[Booking]
        if isinstance(booking_or_id, Booking):
            target_booking = booking_or_id
        else:
            target_booking = self.repository.get_by_id(booking_or_id)

        if not target_booking:
            return

        self._invalidate_booking_caches(target_booking)

    def _invalidate_booking_caches(self, booking: Booking) -> None:
        """
        Invalidate caches affected by booking changes using enhanced cache service.

        Note: Ghost keys removed in v123 cleanup. Only active cache keys are invalidated:
        - Availability caches via invalidate_instructor_availability()
        - booking_stats:instructor (active - used in get_instructor_booking_stats)
        - BookingRepository cached methods via delete_pattern
        """
        booking_service_module = _booking_service_module()
        if self.cache_service:
            try:
                self.cache_service.invalidate_instructor_availability(
                    booking.instructor_id, [booking.booking_date]
                )
                booking_service_module.invalidate_on_availability_change(str(booking.instructor_id))
                stats_cache_key = f"booking_stats:instructor:{booking.instructor_id}"
                self.cache_service.delete(stats_cache_key)
                logger.debug(
                    "Invalidated availability, search, and stats caches for instructor %s",
                    booking.instructor_id,
                )
            except Exception as cache_error:
                logger.warning("Failed to invalidate caches: %s", cache_error)

            try:
                self.cache_service.delete_pattern("booking:get_student_bookings:*")
                self.cache_service.delete_pattern("booking:get_instructor_bookings:*")
                logger.debug(
                    "Invalidated BookingRepository caches after booking %s change",
                    booking.id,
                )
            except Exception as e:
                logger.warning("Failed to invalidate BookingRepository caches: %s", e)
