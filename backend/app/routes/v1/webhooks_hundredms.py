"""
100ms webhook endpoints for video session tracking (v1).

Mounted under /api/v1/webhooks/hundredms
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import json
import logging
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...core.config import settings
from ...database import get_db
from ...models.webhook_event import WebhookEvent
from ...repositories.booking_repository import BookingRepository
from ...schemas.webhook_responses import WebhookAckResponse
from ...services.webhook_ledger_service import WebhookLedgerService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# ---------------------------------------------------------------------------
# In-memory delivery dedup cache (mirrors webhooks_checkr.py)
# ---------------------------------------------------------------------------

_WEBHOOK_CACHE_TTL_SECONDS = 300
_WEBHOOK_CACHE_MAX_SIZE = 1000
_delivery_cache: OrderedDict[str, float] = OrderedDict()

_HANDLED_EVENT_TYPES = frozenset(
    {
        "session.open.success",
        "session.close.success",
        "peer.join.success",
        "peer.leave.success",
    }
)


def _delivery_seen(delivery_key: str | None) -> bool:
    """Return True when a delivery key has already been processed recently."""
    if not delivery_key:
        return False

    now = monotonic()
    expired = [key for key, ts in _delivery_cache.items() if now - ts > _WEBHOOK_CACHE_TTL_SECONDS]
    for key in expired:
        _delivery_cache.pop(key, None)

    return delivery_key in _delivery_cache


def _mark_delivery(delivery_key: str | None) -> None:
    if not delivery_key:
        return
    _delivery_cache[delivery_key] = monotonic()
    while len(_delivery_cache) > _WEBHOOK_CACHE_MAX_SIZE:
        _delivery_cache.popitem(last=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_hundredms_secret(request: Request) -> None:
    """Verify 100ms webhook shared secret header."""
    webhook_secret = settings.hundredms_webhook_secret
    if webhook_secret is None:
        logger.error("100ms webhook secret not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook authentication not configured",
        )

    provided = (request.headers.get("x-hundredms-secret") or "").strip()
    if not provided:
        logger.warning("Missing 100ms webhook secret header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    if provided != webhook_secret.get_secret_value():
        logger.warning(
            "100ms webhook secret mismatch",
            extra={"evt": "hundredms_webhook_invalid_secret"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


def _extract_booking_id_from_room_name(room_name: str | None) -> str | None:
    """Extract booking_id from 100ms room name ``lesson-{booking_id}``."""
    if not room_name or not isinstance(room_name, str):
        return None
    prefix = "lesson-"
    if room_name.startswith(prefix):
        booking_id = room_name[len(prefix) :]
        if len(booking_id) == 26:
            return booking_id
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a tz-aware UTC datetime."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    normalized = trimmed.replace("Z", "+00:00") if trimmed.endswith("Z") else trimmed
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------


def _append_metadata(video_session: Any, event_type: str, data: dict[str, Any]) -> None:
    """Append event to provider_metadata JSONB for debugging."""
    existing = video_session.provider_metadata or {}
    events = existing.get("events", [])
    events.append(
        {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
    )
    video_session.provider_metadata = {**existing, "events": events}


def _handle_peer_join(video_session: Any, data: dict[str, Any]) -> None:
    """Update peer tracking columns on join."""
    role = (data.get("role") or "").lower()
    peer_id = data.get("peer_id") or ""
    joined_at = _parse_timestamp(data.get("joined_at"))

    if role == "host":
        video_session.instructor_peer_id = peer_id
        video_session.instructor_joined_at = joined_at
    elif role == "guest":
        video_session.student_peer_id = peer_id
        video_session.student_joined_at = joined_at
    else:
        logger.info("100ms peer.join unknown role=%s peer_id=%s", role, peer_id)


def _handle_peer_leave(video_session: Any, data: dict[str, Any]) -> None:
    """Update peer tracking columns on leave."""
    role = (data.get("role") or "").lower()
    left_at = _parse_timestamp(data.get("left_at"))

    if role == "host":
        video_session.instructor_left_at = left_at
    elif role == "guest":
        video_session.student_left_at = left_at


def _process_hundredms_event(
    *,
    event_type: str,
    data: dict[str, Any],
    booking_repo: BookingRepository,
) -> tuple[str | None, str]:
    """
    Process a single 100ms webhook event.

    Returns ``(error_message, outcome)`` where outcome is
    ``"processed"``, ``"skipped"``, or ``"failed"``.
    """
    room_name = data.get("room_name") or ""

    booking_id = _extract_booking_id_from_room_name(room_name)
    if not booking_id:
        logger.info("100ms webhook ignored: unrecognized room_name=%s", room_name)
        return None, "skipped"

    video_session = booking_repo.get_video_session_by_booking_id(booking_id)
    if video_session is None:
        logger.warning(
            "100ms webhook: no video session for booking %s",
            booking_id,
            extra={"room_name": room_name, "event_type": event_type},
        )
        return None, "skipped"

    if event_type == "session.open.success":
        video_session.session_id = data.get("session_id") or ""
        video_session.session_started_at = _parse_timestamp(data.get("session_started_at"))

    elif event_type == "session.close.success":
        video_session.session_ended_at = _parse_timestamp(data.get("session_stopped_at"))
        duration = data.get("session_duration")
        if isinstance(duration, (int, float)):
            video_session.session_duration_seconds = int(duration)

    elif event_type == "peer.join.success":
        _handle_peer_join(video_session, data)

    elif event_type == "peer.leave.success":
        _handle_peer_leave(video_session, data)

    else:
        return None, "skipped"

    _append_metadata(video_session, event_type, data)
    booking_repo.flush()
    return None, "processed"


# ---------------------------------------------------------------------------
# DI
# ---------------------------------------------------------------------------


def _get_booking_repository(db: Session = Depends(get_db)) -> BookingRepository:
    return BookingRepository(db)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=WebhookAckResponse)
async def handle_hundredms_webhook(
    request: Request,
    booking_repo: BookingRepository = Depends(_get_booking_repository),
) -> WebhookAckResponse:
    """Process 100ms webhook events for video session tracking."""

    # 1. Verify secret header
    raw_body = await request.body()
    _verify_hundredms_secret(request)

    # 2. Parse JSON
    try:
        payload: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # 3. Extract event metadata
    event_type = (payload.get("type") or "").strip()
    event_id: str | None = payload.get("id")
    data: dict[str, Any] = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    # 4. Skip unhandled event types early
    if event_type not in _HANDLED_EVENT_TYPES:
        logger.debug("Ignoring 100ms event type=%s", event_type)
        return WebhookAckResponse(ok=True)

    # 5. In-memory dedup
    delivery_key = event_id or f"{event_type}:{data.get('room_id')}:{data.get('session_id')}"
    if _delivery_seen(delivery_key):
        logger.info(
            "Duplicate 100ms webhook ignored",
            extra={"delivery_key": delivery_key},
        )
        return WebhookAckResponse(ok=True)

    # 6. Persistent dedup via webhook ledger
    ledger_db = getattr(booking_repo, "db", None)
    ledger_service = WebhookLedgerService(ledger_db) if ledger_db is not None else None
    ledger_event: WebhookEvent | None = None
    if ledger_service is not None:
        ledger_event = await asyncio.to_thread(
            ledger_service.log_received,
            source="hundredms",
            event_type=event_type,
            payload=payload,
            headers=dict(request.headers),
            event_id=event_id,
        )

    if ledger_event is not None and ledger_event.status == "processed":
        logger.info(
            "100ms webhook retry for already-processed event %s (retry_count=%s)",
            ledger_event.id,
            ledger_event.retry_count,
        )
        return WebhookAckResponse(ok=True)

    # 7. Process event
    start_time = monotonic()
    processing_error: str | None = None

    try:
        error, _outcome = await asyncio.to_thread(
            _process_hundredms_event,
            event_type=event_type,
            data=data,
            booking_repo=booking_repo,
        )
        processing_error = error
        _mark_delivery(delivery_key)
    except Exception as exc:
        processing_error = str(exc)
        logger.exception(
            "100ms webhook processing failed",
            extra={"event_type": event_type},
        )

    # 8. Update ledger
    duration_ms = int((monotonic() - start_time) * 1000)
    if ledger_service is not None and ledger_event is not None:
        if processing_error:
            await asyncio.to_thread(
                ledger_service.mark_failed,
                ledger_event,
                error=processing_error,
                duration_ms=duration_ms,
            )
        else:
            await asyncio.to_thread(
                ledger_service.mark_processed,
                ledger_event,
                related_entity_type="booking_video_session",
                related_entity_id=_extract_booking_id_from_room_name(data.get("room_name")),
                duration_ms=duration_ms,
            )

    # 9. Always return 200
    return WebhookAckResponse(ok=True)
