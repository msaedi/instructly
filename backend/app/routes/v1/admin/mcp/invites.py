"""MCP Admin endpoints for founding instructor invites (service token auth)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
import ulid

from app.api.dependencies.auth import validate_mcp_service
from app.api.dependencies.database import get_db
from app.core.exceptions import MCPTokenError
from app.models.user import User
from app.schemas.mcp import (
    MCPActor,
    MCPInvitePreview,
    MCPInvitePreviewData,
    MCPInvitePreviewRecipient,
    MCPInvitePreviewRequest,
    MCPInvitePreviewResponse,
    MCPInviteSendData,
    MCPInviteSendRequest,
    MCPInviteSendResponse,
    MCPInviteSendResult,
    MCPMeta,
)
from app.services.beta_service import BetaService
from app.services.email_subjects import EmailSubject
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.mcp_invite_service import MCPInviteService

router = APIRouter(tags=["MCP Admin - Invites"])


def _normalize_emails(emails: Iterable[str]) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw in emails:
        email = raw.strip().lower()
        if not email:
            continue
        if email in seen:
            warnings.append(f"{email} duplicated in request")
            continue
        seen.add(email)
        normalized.append(email)
    return normalized, warnings


@router.post("/preview", response_model=MCPInvitePreviewResponse)
async def preview_invites(
    payload: MCPInvitePreviewRequest = Body(...),
    current_user: User = Depends(validate_mcp_service),
    db: Session = Depends(get_db),
) -> MCPInvitePreviewResponse:
    recipient_emails, warnings = _normalize_emails([str(e) for e in payload.recipient_emails])
    if not recipient_emails:
        raise HTTPException(status_code=400, detail="recipient_emails_required")

    invite_service = MCPInviteService(db)
    existing_users = await asyncio.to_thread(invite_service.get_existing_users, recipient_emails)
    user_map = {user.email.lower(): user for user in existing_users if user.email}

    recipients: list[MCPInvitePreviewRecipient] = []
    for email in recipient_emails:
        user = user_map.get(email)
        if user:
            warnings.append(f"{email} already exists in system")
        recipients.append(
            MCPInvitePreviewRecipient(
                email=email,
                exists_in_system=user is not None,
                user_id=user.id if user else None,
            )
        )

    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    cap_remaining = await asyncio.to_thread(invite_service.get_founding_cap_remaining)

    invite_preview = MCPInvitePreview(
        subject=EmailSubject.beta_invite(),
        expires_at=expires_at,
        grants_founding=payload.grant_founding_status,
        founding_cap_remaining=cap_remaining,
    )

    confirm_service = MCPConfirmTokenService(db)
    token_payload = {
        "recipient_emails": recipient_emails,
        "grant_founding_status": payload.grant_founding_status,
        "expires_in_days": payload.expires_in_days,
        "message_note": payload.message_note,
    }
    confirm_token, confirm_expires_at = await asyncio.to_thread(
        confirm_service.generate_token,
        token_payload,
        actor_id=current_user.id,
    )

    await asyncio.to_thread(
        invite_service.write_preview_audit,
        actor=current_user,
        recipient_count=len(recipient_emails),
        existing_user_count=len(existing_users),
        grant_founding=payload.grant_founding_status,
        expires_in_days=payload.expires_in_days,
        has_message_note=bool(payload.message_note),
    )

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    return MCPInvitePreviewResponse(
        meta=meta,
        data=MCPInvitePreviewData(
            recipient_count=len(recipient_emails),
            recipients=recipients,
            invite_preview=invite_preview,
            confirm_token=confirm_token,
            confirm_expires_at=confirm_expires_at,
            warnings=warnings,
        ),
    )


@router.post("/send", response_model=MCPInviteSendResponse)
async def send_invites(
    payload: MCPInviteSendRequest = Body(...),
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(validate_mcp_service),
    db: Session = Depends(get_db),
) -> MCPInviteSendResponse:
    if not idempotency_header:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")
    if payload.idempotency_key and payload.idempotency_key != idempotency_header:
        raise HTTPException(status_code=400, detail="idempotency_key_mismatch")

    idempotency_key = payload.idempotency_key or idempotency_header

    confirm_service = MCPConfirmTokenService(db)
    invite_service = MCPInviteService(db)
    try:
        token_data = await asyncio.to_thread(confirm_service.decode_token, payload.confirm_token)
    except MCPTokenError as exc:
        raise exc.to_http_exception()
    token_payload = token_data.get("payload")
    if not isinstance(token_payload, dict):
        raise HTTPException(status_code=400, detail="confirm_token_payload_missing")

    try:
        await asyncio.to_thread(
            confirm_service.validate_token,
            payload.confirm_token,
            token_payload,
            actor_id=current_user.id,
        )
    except MCPTokenError as exc:
        raise exc.to_http_exception()

    recipient_emails_raw = token_payload.get("recipient_emails", [])
    if not isinstance(recipient_emails_raw, list) or not recipient_emails_raw:
        raise HTTPException(status_code=400, detail="confirm_token_payload_invalid")

    recipient_emails = [
        str(email).strip().lower() for email in recipient_emails_raw if str(email).strip()
    ]
    expires_in_days = int(token_payload.get("expires_in_days", 14))
    grant_founding = bool(token_payload.get("grant_founding_status", True))

    idempotency_service = MCPIdempotencyService(db)
    already_done, cached_result = await idempotency_service.check_and_store(
        idempotency_key, operation="mcp_invites.send"
    )
    if already_done:
        if cached_result is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency_in_progress",
            )
        meta = MCPMeta(
            request_id=str(uuid4()),
            generated_at=datetime.now(timezone.utc),
            actor=MCPActor(id=current_user.id, email=current_user.email),
        )
        return MCPInviteSendResponse(
            meta=meta,
            data=MCPInviteSendData(**cached_result),
        )

    beta_service = BetaService(db)
    invites: list[MCPInviteSendResult] = []
    failed_count = 0

    for email in recipient_emails:
        try:
            invite, _join_url, _welcome_url = await asyncio.to_thread(
                beta_service.send_invite_email,
                to_email=email,
                role="instructor_beta",
                expires_in_days=expires_in_days,
                source="mcp_invite",
                base_url=None,
                grant_founding_status=grant_founding,
            )
            invites.append(
                MCPInviteSendResult(
                    email=email,
                    code=invite.code,
                    status="sent",
                )
            )
        except Exception:
            failed_count += 1
            invites.append(
                MCPInviteSendResult(
                    email=email,
                    code="",
                    status="failed",
                )
            )

    sent_count = len(invites) - failed_count
    audit_id = str(ulid.ULID())
    await asyncio.to_thread(
        invite_service.write_send_audit,
        actor=current_user,
        audit_id=audit_id,
        recipient_count=len(recipient_emails),
        sent_count=sent_count,
        failed_count=failed_count,
        grant_founding=grant_founding,
        expires_in_days=expires_in_days,
    )

    response_data = MCPInviteSendData(
        sent_count=sent_count,
        failed_count=failed_count,
        invites=invites,
        audit_id=audit_id,
    )

    await idempotency_service.store_result(idempotency_key, response_data.model_dump())

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    return MCPInviteSendResponse(meta=meta, data=response_data)
