"""
100ms webhook endpoints for video session tracking (v1).

Mounted under /api/v1/webhooks/hundredms
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import secrets as _secrets
from time import monotonic
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from ...core.config import settings
from ...database import get_db
from ...domain.video_utils import compute_grace_minutes
from ...models.webhook_event import WebhookEvent
from ...ratelimit.dependency import rate_limit as new_rate_limit
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
_PROCESSING_RETRY_AFTER_SECONDS = "2"
_WEBHOOK_EVENT_MAX_AGE = timedelta(hours=6)
_WEBHOOK_EVENT_MAX_FUTURE_SKEW = timedelta(minutes=2)
_MAX_WEBHOOK_BODY_BYTES = 1_048_576
_ULID_PATTERN = r"[0-9A-HJKMNP-TV-Z]{26}"
_ROOM_NAME_RE = re.compile(rf"^lesson-(?P<booking_id>{_ULID_PATTERN})$")

_HANDLED_EVENT_TYPES = frozenset(
    {
        "session.open.success",
        "session.close.success",
        "peer.join.success",
        "peer.leave.success",
    }
)


class _WebhookBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class _HandledEventData(_WebhookBaseModel):
    room_id: str = Field(min_length=1, max_length=100)
    room_name: str = Field(min_length=1, max_length=255)

    @field_validator("room_name")
    @classmethod
    def _validate_room_name(cls, value: str) -> str:
        if _extract_booking_id_from_room_name(value) is None:
            raise ValueError("room_name must follow lesson-{ULID} format")
        return value


class _SessionOpenData(_HandledEventData):
    session_id: str = Field(min_length=1, max_length=100)
    session_started_at: str | None = Field(default=None, min_length=1, max_length=64)


class _SessionCloseData(_HandledEventData):
    session_id: str = Field(min_length=1, max_length=100)
    session_started_at: str | None = Field(default=None, min_length=1, max_length=64)
    session_stopped_at: str | None = Field(default=None, min_length=1, max_length=64)
    session_duration: int | float | None = None


class _PeerJoinData(_HandledEventData):
    session_id: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["host", "guest"]
    peer_id: str | None = Field(default=None, min_length=1, max_length=100)
    user_id: str | None = Field(default=None, min_length=1, max_length=100)
    joined_at: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, Any] | str | None = None
    peer: dict[str, Any] | None = None


class _PeerLeaveData(_HandledEventData):
    session_id: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["host", "guest"]
    peer_id: str | None = Field(default=None, min_length=1, max_length=100)
    user_id: str | None = Field(default=None, min_length=1, max_length=100)
    joined_at: str | None = Field(default=None, min_length=1, max_length=64)
    left_at: str | None = Field(default=None, min_length=1, max_length=64)
    peer: dict[str, Any] | None = None


class _HandledEventEnvelope(_WebhookBaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=255)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class _SessionOpenEnvelope(_HandledEventEnvelope):
    type: Literal["session.open.success"]
    data: _SessionOpenData


class _SessionCloseEnvelope(_HandledEventEnvelope):
    type: Literal["session.close.success"]
    data: _SessionCloseData


class _PeerJoinEnvelope(_HandledEventEnvelope):
    type: Literal["peer.join.success"]
    data: _PeerJoinData


class _PeerLeaveEnvelope(_HandledEventEnvelope):
    type: Literal["peer.leave.success"]
    data: _PeerLeaveData


_ParsedHandledEvent = (
    _SessionOpenEnvelope | _SessionCloseEnvelope | _PeerJoinEnvelope | _PeerLeaveEnvelope
)

_EVENT_SCHEMAS: dict[str, type[_ParsedHandledEvent]] = {
    "session.open.success": _SessionOpenEnvelope,
    "session.close.success": _SessionCloseEnvelope,
    "peer.join.success": _PeerJoinEnvelope,
    "peer.leave.success": _PeerLeaveEnvelope,
}


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


def _unmark_delivery(delivery_key: str | None) -> None:
    """Remove a delivery key from the in-memory cache."""
    if not delivery_key:
        return
    _delivery_cache.pop(delivery_key, None)


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

    secret_value = webhook_secret.get_secret_value()
    if not secret_value:
        logger.error("HUNDREDMS_WEBHOOK_SECRET is configured but empty")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook verification misconfigured",
        )

    if not _secrets.compare_digest(provided, secret_value):
        logger.warning(
            "100ms webhook secret mismatch",
            extra={"evt": "hundredms_webhook_invalid_secret"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


def _validate_replay_window(event_timestamp: datetime) -> None:
    now = datetime.now(timezone.utc)
    if event_timestamp < now - _WEBHOOK_EVENT_MAX_AGE:
        logger.warning(
            "Rejecting stale 100ms webhook timestamp=%s now=%s",
            event_timestamp.isoformat(),
            now.isoformat(),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stale webhook timestamp",
        )
    if event_timestamp > now + _WEBHOOK_EVENT_MAX_FUTURE_SKEW:
        logger.warning(
            "Rejecting future-dated 100ms webhook timestamp=%s now=%s",
            event_timestamp.isoformat(),
            now.isoformat(),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook timestamp",
        )


def _validate_handled_event_payload(
    payload: dict[str, Any], event_type: str
) -> tuple[str | None, dict[str, Any], datetime]:
    schema = _EVENT_SCHEMAS.get(event_type)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported event type",
        )
    try:
        parsed = schema.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Invalid 100ms webhook payload type=%s errors=%s",
            event_type,
            exc.errors(),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        ) from exc

    _validate_replay_window(parsed.timestamp)
    return parsed.id, parsed.data.model_dump(), parsed.timestamp


def _validate_webhook_body_size(
    *,
    content_length_header: str | None = None,
    raw_body: bytes | None = None,
) -> None:
    if content_length_header is not None:
        trimmed = content_length_header.strip()
        if trimmed:
            try:
                declared_size = int(trimmed)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length header",
                ) from exc
            if declared_size < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length header",
                )
            if declared_size > _MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Webhook payload too large",
                )

    if raw_body is not None and len(raw_body) > _MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Webhook payload too large",
        )


def _extract_booking_id_from_room_name(room_name: str | None) -> str | None:
    """Extract booking_id from 100ms room name ``lesson-{booking_id}``."""
    if not room_name or not isinstance(room_name, str):
        return None
    match = _ROOM_NAME_RE.match(room_name)
    if not match:
        return None
    return match.group("booking_id")


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


def _build_delivery_key(event_id: str | None, event_type: str, data: dict[str, Any]) -> str | None:
    """Build a delivery dedup key with peer disambiguation when event_id is absent."""
    if event_id:
        return event_id

    room_id = data.get("room_id")
    session_id = data.get("session_id")
    peer_obj = data.get("peer")
    peer_id: Any = None
    if isinstance(peer_obj, dict):
        peer_id = peer_obj.get("id")
    if not peer_id:
        peer_id = data.get("peer_id")
    peer_key = str(peer_id).strip() if peer_id is not None else ""
    return f"{event_type}:{room_id}:{session_id}:{peer_key or 'no-peer'}"


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


def _handle_peer_join(video_session: Any, booking: Any, data: dict[str, Any]) -> bool:
    """Update peer tracking columns on join.

    Returns False when metadata identity checks fail.
    """
    role = (data.get("role") or "").lower()
    peer_id = data.get("peer_id") or ""
    joined_at = _parse_timestamp(data.get("joined_at"))

    logger.info(
        "peer.join.success processing: booking_id=%s role=%s peer_id=%s joined_at=%s "
        "data_keys=%s direct_user_id=%s",
        video_session.booking_id,
        role,
        peer_id,
        joined_at,
        list(data.keys()),
        data.get("user_id"),
    )

    # Extract user_id: prefer direct field (always present from auth token),
    # fall back to peer metadata JSON (defense-in-depth).
    peer_user_id = data.get("user_id")
    if not isinstance(peer_user_id, str) or not peer_user_id:
        raw_metadata = data.get("metadata") or "{}"
        try:
            metadata = (
                json.loads(raw_metadata) if isinstance(raw_metadata, str) else (raw_metadata or {})
            )
            peer_user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
        except (json.JSONDecodeError, AttributeError):
            peer_user_id = None

    booking_start_utc = getattr(booking, "booking_start_utc", None)
    booking_duration = getattr(booking, "duration_minutes", None)
    if (
        joined_at is None
        or not isinstance(booking_start_utc, datetime)
        or not isinstance(booking_duration, (int, float))
    ):
        logger.warning(
            "Skipping peer.join with invalid attendance window data booking_id=%s",
            video_session.booking_id,
        )
        return False

    grace_minutes = compute_grace_minutes(int(booking_duration))
    join_opens_at = booking_start_utc - timedelta(minutes=5)
    join_closes_at = booking_start_utc + timedelta(minutes=grace_minutes)
    if joined_at < join_opens_at or joined_at > join_closes_at:
        logger.warning(
            "Skipping peer.join outside allowed window booking_id=%s joined_at=%s window=%s..%s",
            video_session.booking_id,
            joined_at.isoformat(),
            join_opens_at.isoformat(),
            join_closes_at.isoformat(),
        )
        return False

    # Phase-0 determination (M1): prior logic parsed peer metadata but did not
    # enforce identity. Reject mismatched/missing identities as permanent skips.
    if not isinstance(peer_user_id, str) or not peer_user_id:
        logger.warning(
            "Skipping peer.join without user_id metadata booking_id=%s role=%s peer_id=%s",
            video_session.booking_id,
            role,
            peer_id,
        )
        return False

    allowed_users = {getattr(booking, "student_id", None), getattr(booking, "instructor_id", None)}
    if peer_user_id not in allowed_users:
        logger.warning(
            "Skipping peer.join with non-participant user_id booking_id=%s peer_user_id=%s role=%s",
            video_session.booking_id,
            peer_user_id,
            role,
        )
        return False

    if role == "host":
        if peer_user_id != getattr(booking, "instructor_id", None):
            logger.warning(
                "Skipping peer.join host role mismatch booking_id=%s peer_user_id=%s expected=%s",
                video_session.booking_id,
                peer_user_id,
                getattr(booking, "instructor_id", None),
            )
            return False
        video_session.instructor_peer_id = peer_id
        if video_session.instructor_joined_at is None:
            video_session.instructor_joined_at = joined_at
        logger.info("100ms host peer identified: user_id=%s", peer_user_id)
    elif role == "guest":
        if peer_user_id != getattr(booking, "student_id", None):
            logger.warning(
                "Skipping peer.join guest role mismatch booking_id=%s peer_user_id=%s expected=%s",
                video_session.booking_id,
                peer_user_id,
                getattr(booking, "student_id", None),
            )
            return False
        video_session.student_peer_id = peer_id
        if video_session.student_joined_at is None:
            video_session.student_joined_at = joined_at
        logger.info("100ms guest peer identified: user_id=%s", peer_user_id)
    else:
        logger.info("100ms peer.join unknown role=%s peer_id=%s", role, peer_id)
        return False
    return True


def _handle_peer_leave(video_session: Any, booking: Any, data: dict[str, Any]) -> None:
    """Update peer tracking columns on leave.

    100ms peer.leave.success payloads include ``joined_at`` and ``user_id``.
    When no prior peer.join.success was recorded (e.g. event not enabled in
    the dashboard), we backfill ``joined_at`` and ``peer_id`` from the leave
    event as defense-in-depth.
    """
    role = (data.get("role") or "").lower()
    left_at = _parse_timestamp(data.get("left_at"))
    joined_at = _parse_timestamp(data.get("joined_at"))
    peer_id = data.get("peer_id") or ""
    peer_user_id = data.get("user_id")

    if role == "host":
        # Backfill join time from leave event when peer.join.success was missed
        if video_session.instructor_joined_at is None and joined_at is not None:
            if isinstance(peer_user_id, str) and peer_user_id == getattr(
                booking, "instructor_id", None
            ):
                video_session.instructor_joined_at = joined_at
                video_session.instructor_peer_id = peer_id
                logger.info(
                    "Backfilled instructor join from peer.leave: booking_id=%s joined_at=%s",
                    video_session.booking_id,
                    joined_at.isoformat(),
                )
            else:
                logger.warning(
                    "Ignoring peer.leave for instructor — no join recorded and "
                    "user_id mismatch. booking_id=%s room_id=%s peer_user_id=%s",
                    video_session.booking_id,
                    video_session.room_id,
                    peer_user_id,
                )
                return
        elif video_session.instructor_joined_at is None:
            logger.warning(
                "Ignoring peer.leave for instructor — no join recorded and "
                "no joined_at in leave event. booking_id=%s room_id=%s",
                video_session.booking_id,
                video_session.room_id,
            )
            return
        if video_session.instructor_left_at is None:
            video_session.instructor_left_at = left_at
    elif role == "guest":
        # Backfill join time from leave event when peer.join.success was missed
        if video_session.student_joined_at is None and joined_at is not None:
            if isinstance(peer_user_id, str) and peer_user_id == getattr(
                booking, "student_id", None
            ):
                video_session.student_joined_at = joined_at
                video_session.student_peer_id = peer_id
                logger.info(
                    "Backfilled student join from peer.leave: booking_id=%s joined_at=%s",
                    video_session.booking_id,
                    joined_at.isoformat(),
                )
            else:
                logger.warning(
                    "Ignoring peer.leave for student — no join recorded and "
                    "user_id mismatch. booking_id=%s room_id=%s peer_user_id=%s",
                    video_session.booking_id,
                    video_session.room_id,
                    peer_user_id,
                )
                return
        elif video_session.student_joined_at is None:
            logger.warning(
                "Ignoring peer.leave for student — no join recorded and "
                "no joined_at in leave event. booking_id=%s room_id=%s",
                video_session.booking_id,
                video_session.room_id,
            )
            return
        if video_session.student_left_at is None:
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

    booking = booking_repo.get_by_id(booking_id)
    if booking is None:
        logger.warning("100ms webhook: booking %s not found", booking_id)
        return None, "skipped"

    if event_type == "session.open.success":
        video_session.session_id = data.get("session_id") or ""
        video_session.session_started_at = _parse_timestamp(data.get("session_started_at"))

    elif event_type == "session.close.success":
        video_session.session_ended_at = _parse_timestamp(data.get("session_stopped_at"))
        duration = data.get("session_duration")
        if isinstance(duration, (int, float)):
            video_session.session_duration_seconds = int(duration)
        # Backfill session_started_at when session.open.success was missed
        if video_session.session_started_at is None:
            video_session.session_started_at = _parse_timestamp(data.get("session_started_at"))

    elif event_type == "peer.join.success":
        if not _handle_peer_join(video_session, booking, data):
            return None, "skipped"

    elif event_type == "peer.leave.success":
        _handle_peer_leave(video_session, booking, data)

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


@router.post(
    "",
    response_model=WebhookAckResponse,
    dependencies=[Depends(new_rate_limit("webhook_hundredms"))],
)
async def handle_hundredms_webhook(
    request: Request,
    db: Session = Depends(get_db),
    booking_repo: BookingRepository = Depends(_get_booking_repository),
) -> WebhookAckResponse:
    """Process 100ms webhook events for video session tracking."""

    # 0. Feature flag — skip all processing when video is disabled
    if not settings.hundredms_enabled:
        return WebhookAckResponse(ok=True)

    # 1. Verify secret header
    _verify_hundredms_secret(request)
    _validate_webhook_body_size(content_length_header=request.headers.get("content-length"))
    raw_body = await request.body()
    _validate_webhook_body_size(raw_body=raw_body)

    # 2. Parse JSON
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload encoding",
        )
    try:
        payload: dict[str, Any] = json.loads(body_text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # 3. Extract event metadata
    event_type_raw = payload.get("type")
    event_type = event_type_raw.strip() if isinstance(event_type_raw, str) else ""

    # 4. Skip unhandled event types early
    if event_type not in _HANDLED_EVENT_TYPES:
        logger.debug("Ignoring 100ms event type=%s", event_type)
        return WebhookAckResponse(ok=True)

    # 5. Validate handled payload shape and replay window.
    event_id, data, _ = _validate_handled_event_payload(payload, event_type)

    # 6. Delivery key used by cache dedup fallback
    delivery_key = _build_delivery_key(event_id, event_type, data)
    idempotency_key = None if event_id else delivery_key

    # 7. Persistent dedup via webhook ledger (source of truth)
    ledger_service = WebhookLedgerService(db)
    ledger_event: WebhookEvent = await asyncio.to_thread(
        ledger_service.log_received,
        source="hundredms",
        event_type=event_type,
        payload=payload,
        headers=dict(request.headers),
        event_id=event_id,
        idempotency_key=idempotency_key,
    )

    if ledger_event.status == "processed":
        logger.info(
            "100ms webhook retry for already-processed event %s (retry_count=%s)",
            ledger_event.id,
            ledger_event.retry_count,
        )
        return WebhookAckResponse(ok=True)

    claimed = await asyncio.to_thread(ledger_service.mark_processing, ledger_event)
    if not claimed:
        latest = await asyncio.to_thread(ledger_service.get_event, ledger_event.id)
        latest_status = latest.status if latest is not None else ledger_event.status
        if latest_status == "processed":
            logger.info(
                "100ms webhook already processed while duplicate was in flight: %s",
                ledger_event.id,
            )
            return WebhookAckResponse(ok=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="processing_in_progress",
            headers={"Retry-After": _PROCESSING_RETRY_AFTER_SECONDS},
        )

    # In-memory dedup protects against immediate retries between ledger transitions.
    _mark_delivery(delivery_key)

    # 8. Process event
    start_time = monotonic()

    try:
        _error, _outcome = await asyncio.to_thread(
            _process_hundredms_event,
            event_type=event_type,
            data=data,
            booking_repo=booking_repo,
        )

        duration_ms = int((monotonic() - start_time) * 1000)
        await asyncio.to_thread(
            ledger_service.mark_processed,
            ledger_event,
            related_entity_type="booking_video_session",
            related_entity_id=_extract_booking_id_from_room_name(data.get("room_name")),
            duration_ms=duration_ms,
        )
    except Exception as exc:
        processing_error = str(exc)
        _unmark_delivery(delivery_key)
        logger.exception(
            "100ms webhook processing failed",
            extra={"event_type": event_type},
        )
        duration_ms = int((monotonic() - start_time) * 1000)
        try:
            await asyncio.to_thread(
                ledger_service.mark_failed,
                ledger_event,
                error=processing_error,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception(
                "Failed to mark 100ms webhook ledger event as failed",
                extra={"event_type": event_type},
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="processing_failed",
        ) from exc

    # 9. Return 200 for successful processing
    return WebhookAckResponse(ok=True)
