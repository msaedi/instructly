# backend/app/routes/v1/webhooks_checkr.py
"""
Checkr webhook endpoints for background check updates (v1).

Migrated from /webhooks/checkr to /api/v1/webhooks/checkr
"""

from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...api.dependencies.repositories import (
    get_background_job_repo,
    get_bgc_webhook_log_repo,
)
from ...api.dependencies.services import get_background_check_workflow_service
from ...core.config import settings
from ...core.exceptions import RepositoryException
from ...core.metrics import CHECKR_WEBHOOK_TOTAL
from ...models.webhook_event import WebhookEvent
from ...repositories.background_job_repository import BackgroundJobRepository
from ...repositories.bgc_webhook_log_repository import BGCWebhookLogRepository
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...schemas.webhook_responses import WebhookAckResponse
from ...services.background_check_workflow_service import (
    BackgroundCheckWorkflowService,
)
from ...services.webhook_ledger_service import WebhookLedgerService

logger = logging.getLogger(__name__)

# v1 router - mounted under /api/v1/webhooks/checkr
router = APIRouter(tags=["webhooks"])

_WEBHOOK_CACHE_TTL_SECONDS = 300
_WEBHOOK_CACHE_MAX_SIZE = 1000
_delivery_cache: OrderedDict[str, float] = OrderedDict()
_SIGNATURE_PLACEHOLDER = "Please create an API key to check the authenticity of our webhooks."


def _result_label(result: str) -> str:
    normalized = (result or "").lower()
    if normalized in {"clear", "eligible"}:
        return "clear"
    if normalized in {"consider", "needs_review"}:
        return "consider"
    if normalized == "canceled":
        return "canceled"
    return "other"


def _parse_timestamp(value: Any) -> datetime | None:
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


def _require_basic_auth(request: Request) -> None:
    """Enforce HTTP basic authentication for inbound webhooks."""

    username_secret = settings.checkr_webhook_user
    password_secret = settings.checkr_webhook_pass
    if username_secret is None or password_secret is None:
        logger.error("Checkr webhook basic auth credentials are not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook authentication not configured",
        )

    header = request.headers.get("Authorization")
    if not header or not header.lower().startswith("basic "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    token = header.split(" ", 1)[1]
    try:
        provided = base64.b64decode(token).decode("utf-8")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        ) from None

    expected = f"{username_secret.get_secret_value()}:{password_secret.get_secret_value()}"
    if provided != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _compute_signature(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _verify_checkr_signature(request: Request, raw_body: bytes) -> None:
    provided_sig = request.headers.get("X-Checkr-Signature")
    if not provided_sig:
        logger.warning("Missing Checkr webhook signature header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    normalized_sig = provided_sig.strip()
    if normalized_sig == _SIGNATURE_PLACEHOLDER:
        logger.warning("Rejected Checkr webhook with placeholder signature header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    if normalized_sig.lower().startswith("sha256="):
        normalized_sig = normalized_sig.split("=", 1)[1].strip()

    if not normalized_sig:
        logger.warning("Empty Checkr webhook signature header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    api_key = settings.checkr_api_key.get_secret_value()
    if not api_key:
        logger.error("Checkr API key is not configured for signature verification")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook authentication not configured",
        )

    computed_sig = _compute_signature(api_key, raw_body)
    if not hmac.compare_digest(normalized_sig, computed_sig):
        logger.warning(
            "Checkr webhook signature mismatch",
            extra={
                "evt": "webhook_invalid_sig",
                "delivery_id": request.headers.get("X-Checkr-Delivery-Id"),
            },
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _delivery_seen(delivery_key: str | None) -> bool:
    """Return True when a delivery key has already been processed recently."""

    if not delivery_key:
        return False

    now = monotonic()

    expired = [
        key
        for key, timestamp in _delivery_cache.items()
        if now - timestamp > _WEBHOOK_CACHE_TTL_SECONDS
    ]
    for key in expired:
        _delivery_cache.pop(key, None)

    return delivery_key in _delivery_cache


def _mark_delivery(delivery_key: str | None) -> None:
    if not delivery_key:
        return

    _delivery_cache[delivery_key] = monotonic()
    while len(_delivery_cache) > _WEBHOOK_CACHE_MAX_SIZE:
        _delivery_cache.popitem(last=False)


def _record_webhook_event(
    log_repo: BGCWebhookLogRepository,
    *,
    event_type: str,
    resource_id: str | None,
    payload: dict[str, Any],
    delivery_id: str | None,
    signature: str | None,
    http_status: int | None,
) -> None:
    try:
        log_repo.record(
            event_type=event_type or "unknown",
            resource_id=resource_id,
            delivery_id=delivery_id,
            http_status=http_status,
            payload=payload,
            signature=signature,
        )
    except RepositoryException as exc:
        logger.warning("Unable to persist webhook log: %s", str(exc))


def _resolve_resource_id(event_type: str, data_object: dict[str, Any]) -> str | None:
    obj_id = data_object.get("id")
    if isinstance(obj_id, str) and obj_id:
        return obj_id
    if event_type.startswith("report."):
        report_id = data_object.get("report_id")
        return str(report_id) if isinstance(report_id, str) else None
    invitation_id = data_object.get("invitation_id")
    if isinstance(invitation_id, str) and invitation_id:
        return invitation_id
    return None


def _handle_invitation_event(
    repo: InstructorProfileRepository,
    *,
    data_object: dict[str, Any],
) -> None:
    invitation_id = data_object.get("id") or data_object.get("invitation_id")
    candidate_id = data_object.get("candidate_id")

    profile = None
    if isinstance(invitation_id, str) and invitation_id:
        profile = repo.update_bgc_by_invitation(
            invitation_id,
            status="pending",
            note=None,
        )
    if profile is None and isinstance(candidate_id, str) and candidate_id:
        repo.update_bgc_by_candidate(
            candidate_id,
            status="pending",
            note=None,
        )


def _format_note(event_type: str, reason: str | None) -> str:
    clean_reason = (reason or "").strip()
    if clean_reason:
        return f"{event_type}: {clean_reason}"
    return event_type


def _update_report_status(
    repo: InstructorProfileRepository,
    report_id: str | None,
    *,
    status: str | None,
    note: str | None,
) -> None:
    if not report_id:
        return
    repo.update_bgc_by_report_id(
        report_id,
        status=status,
        completed_at=None,
        note=note,
    )


def _extract_reason(data_object: dict[str, Any]) -> str | None:
    for key in ("reason", "status", "adjudication"):
        value = data_object.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def _extract_candidate_id(data_object: dict[str, Any]) -> str | None:
    candidate_id = data_object.get("candidate_id")
    if isinstance(candidate_id, str):
        cleaned = candidate_id.strip()
        if cleaned:
            return cleaned
    candidate_obj = data_object.get("candidate")
    if isinstance(candidate_obj, dict):
        nested = candidate_obj.get("id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def _extract_invitation_id(data_object: dict[str, Any]) -> str | None:
    invitation_id = data_object.get("invitation_id")
    if isinstance(invitation_id, str):
        cleaned = invitation_id.strip()
        if cleaned:
            return cleaned
    invitation_obj = data_object.get("invitation")
    if isinstance(invitation_obj, dict):
        nested = invitation_obj.get("id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def _bind_report_to_profile(
    repo: InstructorProfileRepository,
    *,
    report_id: str | None,
    candidate_id: str | None,
    invitation_id: str | None,
    env: str,
) -> str | None:
    """Attach a Checkr report identifier to a known instructor profile."""

    if not report_id:
        return None

    profile_id: str | None = repo.bind_report_to_candidate(candidate_id, report_id, env=env)
    if profile_id:
        return profile_id
    result: str | None = repo.bind_report_to_invitation(invitation_id, report_id, env=env)
    return result


async def _process_checkr_payload(
    *,
    event_type: str,
    data_object: dict[str, Any],
    payload: dict[str, Any],
    headers: Mapping[str, Any],
    workflow_service: BackgroundCheckWorkflowService,
    job_repository: BackgroundJobRepository,
    log_repository: BGCWebhookLogRepository,
    resource_id: str | None,
    skip_dedup: bool = False,
) -> str | None:
    processing_error: str | None = None
    normalized_headers = {str(key).lower(): value for key, value in headers.items()}

    def _header_value(name: str) -> Any | None:
        return normalized_headers.get(name.lower())

    delivery_id = _header_value("x-checkr-delivery-id")
    signature = _header_value("x-checkr-signature")

    _record_webhook_event(
        log_repository,
        event_type=event_type,
        resource_id=resource_id,
        payload=payload,
        delivery_id=delivery_id if isinstance(delivery_id, str) else None,
        signature=signature if isinstance(signature, str) else None,
        http_status=status.HTTP_200_OK,
    )

    result_value = data_object.get("result") or data_object.get("status")
    logger.info(
        "checkr_webhook type=%s resource=%s result=%s",
        event_type or "unknown",
        resource_id,
        result_value,
    )

    delivery_header = delivery_id if isinstance(delivery_id, str) else None
    delivery_key = delivery_header or (
        f"{event_type}:{resource_id}" if event_type and resource_id else None
    )

    if not event_type:
        return processing_error

    if not skip_dedup and _delivery_seen(delivery_key):
        logger.info(
            "Duplicate Checkr webhook delivery ignored",
            extra={"evt": "webhook_dedup", "delivery_id": delivery_key},
        )
        return processing_error

    repo = workflow_service.repo

    if event_type in {"invitation.created", "invitation.completed"}:
        try:
            _handle_invitation_event(repo, data_object=data_object)
            _mark_delivery(delivery_key)
        except RepositoryException as exc:
            processing_error = processing_error or str(exc)
            logger.warning(
                "Unable to process invitation event: %s",
                str(exc),
                extra={"event_type": event_type},
            )
        return processing_error

    if event_type == "report.updated":
        report_id = resource_id
        if not report_id:
            return processing_error

        eta_raw = data_object.get("estimated_completion_time")
        previous_attrs: dict[str, Any] | None = None
        data_envelope = payload.get("data")
        if isinstance(data_envelope, dict):
            maybe_prev = data_envelope.get("previous_attributes")
            if isinstance(maybe_prev, dict):
                previous_attrs = maybe_prev
        prev_eta_raw = previous_attrs.get("estimated_completion_time") if previous_attrs else None

        if eta_raw == prev_eta_raw and eta_raw is not None:
            return processing_error
        if eta_raw is None and prev_eta_raw is None:
            return processing_error

        eta_value = _parse_timestamp(eta_raw) if eta_raw else None
        candidate_id = _extract_candidate_id(data_object)
        _bind_report_to_profile(
            repo,
            report_id=report_id,
            candidate_id=candidate_id,
            invitation_id=_extract_invitation_id(data_object),
            env=settings.checkr_env,
        )

        try:
            await asyncio.to_thread(
                workflow_service.handle_report_eta_updated,
                report_id=report_id,
                env=settings.checkr_env,
                eta=eta_value,
                candidate_id=candidate_id,
            )
            CHECKR_WEBHOOK_TOTAL.labels(result="other", outcome="success").inc()
            _mark_delivery(delivery_key)
        except RepositoryException as exc:
            processing_error = processing_error or str(exc)
            CHECKR_WEBHOOK_TOTAL.labels(result="other", outcome="queued").inc()
            await asyncio.to_thread(
                job_repository.enqueue,
                type="webhook.report_eta",
                payload={
                    "report_id": report_id,
                    "eta": eta_value.isoformat() if eta_value else None,
                    "env": settings.checkr_env,
                    "candidate_id": candidate_id,
                },
            )
            logger.warning(
                "Unable to persist ETA update: %s",
                str(exc),
                extra={"evt": "checkr_webhook", "type": event_type, "report_id": report_id},
            )
        except Exception as exc:  # pragma: no cover
            processing_error = processing_error or str(exc)
            CHECKR_WEBHOOK_TOTAL.labels(result="other", outcome="error").inc()
            await asyncio.to_thread(
                job_repository.enqueue,
                type="webhook.report_eta",
                payload={
                    "report_id": report_id,
                    "eta": eta_value.isoformat() if eta_value else None,
                    "env": settings.checkr_env,
                    "candidate_id": candidate_id,
                },
            )
            logger.exception(
                "Unhandled error processing report.updated ETA",
                extra={"evt": "checkr_webhook", "type": event_type, "report_id": report_id},
            )
        return processing_error

    if event_type == "report.completed":
        report_id = resource_id
        if not report_id:
            return processing_error

        candidate_id = _extract_candidate_id(data_object)
        invitation_id = _extract_invitation_id(data_object)
        _bind_report_to_profile(
            repo,
            report_id=report_id,
            candidate_id=candidate_id,
            invitation_id=invitation_id,
            env=settings.checkr_env,
        )

        raw_result = (data_object.get("result") or data_object.get("adjudication") or "").lower()
        normalized_result = {
            "clear": "clear",
            "consider": "consider",
            "suspended": "suspended",
        }.get(raw_result, "unknown")
        assessment_raw = (data_object.get("assessment") or "").strip().lower()
        normalized_assessment = assessment_raw or None
        effective_result = normalized_assessment or normalized_result
        result_label = _result_label(effective_result)
        includes_canceled = data_object.get("includes_canceled")

        completed_at = datetime.now(timezone.utc)
        package_value = data_object.get("package") or settings.checkr_package

        try:
            status_value, profile, requires_follow_up = await asyncio.to_thread(
                workflow_service.handle_report_completed,
                report_id=report_id,
                result=normalized_result,
                assessment=normalized_assessment,
                package=package_value,
                env=settings.checkr_env,
                completed_at=completed_at,
                candidate_id=candidate_id,
                invitation_id=invitation_id,
                includes_canceled=includes_canceled,
            )
            if requires_follow_up and profile is not None:
                logger.info(
                    "Background check requires review",
                    extra={"instructor_id": profile.id, "report_id": report_id},
                )

            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="success").inc()
            logger.info(
                "Checkr webhook processed",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "result": normalized_result,
                    "report_id": report_id,
                    "outcome": "success",
                },
            )
            _mark_delivery(delivery_key)
        except RepositoryException as exc:
            processing_error = processing_error or str(exc)
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="queued").inc()
            logger.warning(
                "Background check workflow deferred: %s",
                str(exc),
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "result": normalized_result,
                    "assessment": normalized_assessment,
                    "report_id": report_id,
                    "outcome": "queued",
                },
            )
            await asyncio.to_thread(
                job_repository.enqueue,
                type="webhook.report_completed",
                payload={
                    "report_id": report_id,
                    "result": normalized_result,
                    "assessment": normalized_assessment,
                    "package": package_value,
                    "env": settings.checkr_env,
                    "completed_at": completed_at.isoformat(),
                    "candidate_id": candidate_id,
                    "invitation_id": invitation_id,
                    "includes_canceled": includes_canceled,
                },
            )
        except Exception as exc:  # pragma: no cover - safety fallback
            processing_error = processing_error or str(exc)
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="error").inc()
            logger.exception(
                "Unhandled error processing report.completed; enqueueing retry",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "result": normalized_result,
                    "assessment": normalized_assessment,
                    "report_id": report_id,
                    "outcome": "error",
                },
            )
            await asyncio.to_thread(
                job_repository.enqueue,
                type="webhook.report_completed",
                payload={
                    "report_id": report_id,
                    "result": normalized_result,
                    "assessment": normalized_assessment,
                    "package": package_value,
                    "env": settings.checkr_env,
                    "completed_at": completed_at.isoformat(),
                    "candidate_id": candidate_id,
                    "invitation_id": invitation_id,
                    "includes_canceled": includes_canceled,
                },
            )

        return processing_error

    if event_type == "report.canceled":
        report_id = resource_id
        if not report_id:
            return processing_error

        candidate_id = _extract_candidate_id(data_object)
        invitation_id = _extract_invitation_id(data_object)
        _bind_report_to_profile(
            repo,
            report_id=report_id,
            candidate_id=candidate_id,
            invitation_id=invitation_id,
            env=settings.checkr_env,
        )
        canceled_raw = (
            data_object.get("completed_at")
            or data_object.get("canceled_at")
            or data_object.get("closed_at")
        )
        canceled_at = _parse_timestamp(canceled_raw) or datetime.now(timezone.utc)
        result_label = _result_label("canceled")
        try:
            await asyncio.to_thread(
                workflow_service.handle_report_canceled,
                report_id=report_id,
                env=settings.checkr_env,
                canceled_at=canceled_at,
                candidate_id=candidate_id,
                invitation_id=invitation_id,
            )
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="success").inc()
            logger.info(
                "Checkr webhook processed",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "report_id": report_id,
                    "outcome": "success",
                },
            )
            _mark_delivery(delivery_key)
        except RepositoryException as exc:
            processing_error = processing_error or str(exc)
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="queued").inc()
            logger.warning(
                "Background check cancel deferred: %s",
                str(exc),
                extra={"evt": "checkr_webhook", "type": event_type, "report_id": report_id},
            )
            await asyncio.to_thread(
                job_repository.enqueue,
                type="webhook.report_canceled",
                payload={
                    "report_id": report_id,
                    "env": settings.checkr_env,
                    "canceled_at": canceled_at.isoformat(),
                    "candidate_id": candidate_id,
                    "invitation_id": invitation_id,
                },
            )
        except Exception as exc:  # pragma: no cover - safety fallback
            processing_error = processing_error or str(exc)
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="error").inc()
            logger.exception(
                "Unhandled error processing report.canceled; enqueueing retry",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "report_id": report_id,
                    "outcome": "error",
                },
            )
            await asyncio.to_thread(
                job_repository.enqueue,
                type="webhook.report_canceled",
                payload={
                    "report_id": report_id,
                    "env": settings.checkr_env,
                    "canceled_at": canceled_at.isoformat(),
                    "candidate_id": candidate_id,
                    "invitation_id": invitation_id,
                },
            )

        return processing_error

    if event_type == "report.suspended":
        report_id = resource_id
        if not report_id:
            return processing_error

        try:
            await asyncio.to_thread(
                workflow_service.handle_report_suspended,
                report_id,
                _format_note(event_type, _extract_reason(data_object)),
            )
            logger.info(
                "Checkr webhook processed",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "report_id": report_id,
                    "outcome": "success",
                },
            )
            _mark_delivery(delivery_key)
        except RepositoryException as exc:
            processing_error = processing_error or str(exc)
            logger.warning(
                "Unable to process report.suspended event: %s",
                str(exc),
                extra={"report_id": report_id},
            )
        except Exception as exc:  # pragma: no cover - safety fallback
            processing_error = processing_error or str(exc)
            logger.exception(
                "Unhandled error handling report.suspended",
                extra={"report_id": report_id},
            )
        return processing_error

    report_status_events: dict[str, dict[str, str | None]] = {
        "report.created": {"status": "pending", "note": None},
        "report.updated": {"status": None, "note": "report.updated"},
        "report.deferred": {"status": "pending", "note": None},
        "report.resumed": {"status": "pending", "note": "report.resumed"},
        "report.disputed": {"status": "consider", "note": "report.disputed"},
        "report.upgrade_failed": {"status": "pending", "note": None},
    }

    if event_type in report_status_events:
        report_id = resource_id
        if not report_id:
            return processing_error

        candidate_id = _extract_candidate_id(data_object)
        invitation_id = _extract_invitation_id(data_object)
        _bind_report_to_profile(
            repo,
            report_id=report_id,
            candidate_id=candidate_id,
            invitation_id=invitation_id,
            env=settings.checkr_env,
        )

        details = report_status_events[event_type]
        note = details["note"]
        if note is None:
            note = _format_note(event_type, _extract_reason(data_object))
        try:
            _update_report_status(
                repo,
                report_id,
                status=details["status"],
                note=note,
            )
            _mark_delivery(delivery_key)
        except RepositoryException as exc:
            processing_error = processing_error or str(exc)
            logger.warning(
                "Failed to update report status from %s: %s",
                event_type,
                str(exc),
                extra={"report_id": report_id},
            )
        return processing_error

    logger.debug("Ignoring unsupported Checkr webhook event", extra={"event_type": event_type})
    return processing_error


@router.post("", response_model=WebhookAckResponse)
async def handle_checkr_webhook(
    request: Request,
    workflow_service: BackgroundCheckWorkflowService = Depends(
        get_background_check_workflow_service
    ),
    job_repository: BackgroundJobRepository = Depends(get_background_job_repo),
    log_repository: BGCWebhookLogRepository = Depends(get_bgc_webhook_log_repo),
) -> WebhookAckResponse:
    """Process Checkr webhook events for background check reports."""

    _require_basic_auth(request)
    raw_body = await request.body()
    _verify_checkr_signature(request, raw_body)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = (payload.get("type") or "").strip()
    data_object = payload.get("data", {}).get("object") or {}
    if not isinstance(data_object, dict):
        data_object = {}

    resource_id = _resolve_resource_id(event_type, data_object)

    ledger_db = getattr(log_repository, "db", None)
    if ledger_db is None:
        repo = getattr(workflow_service, "repo", None)
        ledger_db = getattr(repo, "db", None)
    if ledger_db is None:
        ledger_db = getattr(job_repository, "db", None)

    ledger_service = WebhookLedgerService(ledger_db) if ledger_db is not None else None
    ledger_event: WebhookEvent | None = None
    if ledger_service is not None:
        ledger_event = await asyncio.to_thread(
            ledger_service.log_received,
            source="checkr",
            event_type=event_type or "unknown",
            payload=payload,
            headers=dict(request.headers),
            event_id=payload.get("id"),
            idempotency_key=request.headers.get("X-Checkr-Delivery-Id"),
        )
    start_time = monotonic()
    processing_error = await _process_checkr_payload(
        event_type=event_type,
        data_object=data_object,
        payload=payload,
        headers=request.headers,
        workflow_service=workflow_service,
        job_repository=job_repository,
        log_repository=log_repository,
        resource_id=resource_id,
    )

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
                related_entity_type="checkr",
                related_entity_id=resource_id,
                duration_ms=duration_ms,
            )

    return WebhookAckResponse(ok=True)
