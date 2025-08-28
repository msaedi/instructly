from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies.permissions import require_role
from ..schemas.beta import (
    AccessGrantResponse,
    InviteConsumeRequest,
    InviteGenerateRequest,
    InviteGenerateResponse,
    InviteRecord,
    InviteSendRequest,
    InviteSendResponse,
    InviteValidateResponse,
)
from ..services.beta_service import BetaService

router = APIRouter(prefix="/api/beta", tags=["beta"])


@router.get("/invites/validate", response_model=InviteValidateResponse)
def validate_invite(code: str = Query(...), db: Session = Depends(get_db)):
    svc = BetaService(db)
    ok, reason, invite = svc.validate_invite(code)
    return InviteValidateResponse(
        valid=ok,
        reason=reason,
        code=invite.code if invite else None,
        email=getattr(invite, "email", None) if invite else None,
        role=getattr(invite, "role", None) if invite else None,
        expires_at=getattr(invite, "expires_at", None) if invite else None,
        used_at=getattr(invite, "used_at", None) if invite else None,
    )


@router.post("/invites/generate", response_model=InviteGenerateResponse)
def generate_invites(
    payload: InviteGenerateRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    svc = BetaService(db)
    created = svc.bulk_generate(
        count=payload.count,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
        source=payload.source,
        emails=payload.emails,
    )
    items = [InviteRecord(id=i.id, code=i.code, email=i.email, role=i.role, expires_at=i.expires_at) for i in created]
    return InviteGenerateResponse(invites=items)


@router.post("/invites/consume", response_model=AccessGrantResponse)
def consume_invite(payload: InviteConsumeRequest, db: Session = Depends(get_db)):
    svc = BetaService(db)
    grant, reason = svc.consume_and_grant(
        code=payload.code, user_id=payload.user_id, role=payload.role, phase=payload.phase
    )
    if not grant:
        raise HTTPException(status_code=400, detail=reason or "invalid_invite")
    return AccessGrantResponse(
        access_id=grant.id,
        user_id=grant.user_id,
        role=grant.role,
        phase=grant.phase,
        invited_by_code=grant.invited_by_code,
    )


@router.post("/invites/send", response_model=InviteSendResponse)
def send_invite(payload: InviteSendRequest, db: Session = Depends(get_db), admin=Depends(require_role("admin"))):
    svc = BetaService(db)
    invite, join_url, welcome_url = svc.send_invite_email(
        to_email=payload.to_email,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
        source=payload.source,
        base_url=payload.base_url,
    )
    return InviteSendResponse(
        id=invite.id, code=invite.code, email=payload.to_email, join_url=join_url, welcome_url=welcome_url
    )
