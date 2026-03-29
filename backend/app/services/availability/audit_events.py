"""Audit logging and outbox event publishing for availability changes."""

from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Any

from ...core.config import settings
from ...models.audit_log import AuditLog
from ...utils.bitmap_base64 import encode_bitmap_bytes
from ...utils.bitset import new_empty_bits, new_empty_tags
from ..audit_redaction import redact
from .mixin_base import AvailabilityMixinBase
from .types import (
    DayBitmaps,
    PreparedWeek,
    availability_service_module,
    build_availability_idempotency_key,
)

logger = logging.getLogger(__name__)


def _build_windows_payload(
    bitmap_map: dict[date, DayBitmaps], target_dates: list[date]
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for target in target_dates:
        result[target.isoformat()] = [
            {"start_time": start, "end_time": end}
            for start, end in availability_service_module().windows_from_bits(
                bitmap_map.get(target, DayBitmaps(new_empty_bits(), new_empty_tags())).bits
            )
        ]
    return result


def _build_tags_payload(
    bitmap_map: dict[date, DayBitmaps], target_dates: list[date]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for target in target_dates:
        result[target.isoformat()] = encode_bitmap_bytes(
            bitmap_map.get(target, DayBitmaps(new_empty_bits(), new_empty_tags())).format_tags
        )
    return result


def _build_window_counts(
    bitmap_map: dict[date, DayBitmaps], target_dates: list[date]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for target in target_dates:
        counts[target.isoformat()] = len(
            availability_service_module().windows_from_bits(
                bitmap_map.get(target, DayBitmaps(new_empty_bits(), new_empty_tags())).bits
            )
        )
    return counts


class AvailabilityAuditEventsMixin(AvailabilityMixinBase):
    """Audit logging and outbox event publishing for availability changes."""

    def _enqueue_week_save_event(
        self,
        instructor_id: str,
        week_start: date,
        week_dates: list[date],
        prepared: PreparedWeek,
        created_count: int,
        deleted_count: int,
        clear_existing: bool,
    ) -> None:
        """Persist outbox entry describing week availability save operation."""
        self.repository.flush()
        week_end = week_start + timedelta(days=6)
        version = self.compute_week_version(instructor_id, week_start, week_end)
        affected_dates = list(prepared.affected_dates)
        service_module = availability_service_module()
        if service_module.settings.suppress_past_availability_events:
            today = service_module.get_user_today_by_id(instructor_id, self.db)
            affected_dates = [d for d in affected_dates if d >= today]
        if not affected_dates:
            logger.info(
                "Skipping availability.week_saved event due to past-only edits",
                extra={
                    "instructor_id": instructor_id,
                    "week_start": week_start.isoformat(),
                },
            )
            return
        affected = {d.isoformat() for d in affected_dates}
        if clear_existing and not affected:
            affected = {d.isoformat() for d in week_dates}

        payload = {
            "instructor_id": instructor_id,
            "week_start": week_start.isoformat(),
            "affected_dates": sorted(affected),
            "clear_existing": bool(clear_existing),
            "created_slots": created_count,
            "deleted_slots": deleted_count,
            "version": version,
        }
        aggregate_id = f"{instructor_id}:{week_start.isoformat()}"
        key = build_availability_idempotency_key(
            instructor_id, week_start, "availability.week_saved", version
        )
        self.event_outbox_repository.enqueue(
            event_type="availability.week_saved",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=key,
        )
        if settings.instant_deliver_in_tests:
            try:
                attempt_count = max(created_count, 1)
                self.event_outbox_repository.mark_sent_by_key(key, attempt_count)
            except Exception as exc:  # pragma: no cover - diagnostics
                logger.warning(
                    "Failed to mark availability.week_saved outbox row as sent in tests",
                    extra={
                        "instructor_id": instructor_id,
                        "week_start": week_start.isoformat(),
                        "idempotency_key": key,
                        "error": str(exc),
                    },
                    exc_info=True,
                )

    def _build_week_audit_payload(
        self,
        instructor_id: str,
        week_start: date,
        dates: list[date],
        *,
        clear_existing: bool,
        created: int = 0,
        deleted: int = 0,
        window_cache: dict[date, list[tuple[str, str]]] | None = None,
    ) -> dict[str, Any]:
        """Construct a compact snapshot for audit logging."""
        unique_dates = sorted({d for d in dates})
        window_counts: dict[str, int] = {}
        bitmap_repo = self._bitmap_repo()
        for target in unique_dates:
            if window_cache is not None and target in window_cache:
                windows_for_day = window_cache[target]
            else:
                bits = bitmap_repo.get_day_bits(instructor_id, target)
                windows_for_day = (
                    availability_service_module().windows_from_bits(bits) if bits else []
                )
                if window_cache is not None:
                    window_cache[target] = windows_for_day
            window_counts[target.isoformat()] = len(windows_for_day)

        week_end = week_start + timedelta(days=6)
        payload: dict[str, Any] = {
            "week_start": week_start.isoformat(),
            "affected_dates": [d.isoformat() for d in unique_dates],
            "window_counts": window_counts,
            "clear_existing": bool(clear_existing),
            "version": self.compute_week_version(instructor_id, week_start, week_end),
        }
        if created or deleted:
            payload["delta"] = {"created": created, "deleted": deleted}
        return redact(payload) or {}

    def _build_bitmap_save_audit_payloads(
        self,
        *,
        week_start: date,
        normalized_current_map: dict[date, DayBitmaps],
        target_map: dict[date, DayBitmaps],
        changed_dates: set[date],
        skipped_window_dates: list[date],
        skipped_forbidden_dates: list[date],
        past_written_dates: set[date],
        audit_dates: list[date],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        before_payload: dict[str, Any] = {
            "week_start": week_start.isoformat(),
            "windows": _build_windows_payload(normalized_current_map, audit_dates),
            "format_tags": _build_tags_payload(normalized_current_map, audit_dates),
        }
        before_payload["window_counts"] = _build_window_counts(normalized_current_map, audit_dates)

        after_payload: dict[str, Any] = {
            "week_start": week_start.isoformat(),
            "windows": _build_windows_payload(target_map, audit_dates),
            "format_tags": _build_tags_payload(target_map, audit_dates),
            "edited_dates": [day.isoformat() for day in sorted(changed_dates)],
            "skipped_dates": [day.isoformat() for day in skipped_window_dates],
            "skipped_forbidden_dates": [day.isoformat() for day in skipped_forbidden_dates],
            "historical_edit": bool(
                past_written_dates or skipped_window_dates or skipped_forbidden_dates
            ),
            "skipped_past_window": bool(skipped_window_dates),
            "skipped_past_forbidden": bool(skipped_forbidden_dates),
            "days_written": len(changed_dates),
        }
        after_payload["window_counts"] = _build_window_counts(target_map, audit_dates)
        return before_payload, after_payload

    def _write_availability_audit(
        self,
        instructor_id: str,
        week_start: date,
        action: str,
        *,
        actor: Any | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        default_role: str = "instructor",
    ) -> None:
        """Persist audit entry for availability changes."""
        actor_payload = super()._resolve_actor_payload(actor, default_role=default_role)
        audit_entry = AuditLog.from_change(
            entity_type="availability",
            entity_id=f"{instructor_id}:{week_start.isoformat()}",
            action=action,
            actor=actor_payload,
            before=before,
            after=after,
        )
        if availability_service_module().AUDIT_ENABLED:
            self.audit_repository.write(audit_entry)
