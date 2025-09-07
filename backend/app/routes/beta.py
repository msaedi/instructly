from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import requests
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import get_db
from ..dependencies.permissions import require_role
from ..monitoring.prometheus_metrics import prometheus_metrics
from ..repositories.beta_repository import BetaSettingsRepository
from ..schemas.beta import (
    AccessGrantResponse,
    BetaMetricsSummaryResponse,
    InviteBatchAsyncStartResponse,
    InviteBatchProgressResponse,
    InviteBatchSendFailure,
    InviteBatchSendRequest,
    InviteBatchSendResponse,
    InviteConsumeRequest,
    InviteGenerateRequest,
    InviteGenerateResponse,
    InviteRecord,
    InviteSendRequest,
    InviteSendResponse,
    InviteValidateResponse,
)
from ..services.beta_service import BetaService
from ..tasks.celery_app import celery_app

router = APIRouter(prefix="/api/beta", tags=["beta"])


def _fetch_prometheus_summary(
    prometheus_http_url: str, bearer_token: str | None
) -> BetaMetricsSummaryResponse | None:
    try:
        base = prometheus_http_url.rstrip("/")
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None

        def q(expr: str) -> float:
            r = requests.get(
                f"{base}/api/v1/query", params={"query": expr}, headers=headers, timeout=4
            )
            r.raise_for_status()
            data = r.json()
            try:
                val = float(data["data"]["result"][0]["value"][1])
            except Exception:
                val = 0.0
            return val

        invites_sent = q(
            'increase(instainstru_service_operations_total{operation="beta_invite_sent",status="success"}[24h])'
        )
        invites_err = q(
            'increase(instainstru_service_operations_total{operation="beta_invite_sent",status="error"}[24h])'
        )
        phases = {}
        for phase in ["disabled", "instructor_only", "open_beta", "unknown"]:
            phases[phase] = q(
                f'last_over_time(instainstru_beta_phase_header_total{{phase="{phase}"}}[24h])'
            )
        return BetaMetricsSummaryResponse(
            invites_sent_24h=int(invites_sent),
            invites_errors_24h=int(invites_err),
            phase_counts_24h={k: int(v) for k, v in phases.items() if v > 0},
        )
    except Exception:
        return None


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
    items = [
        InviteRecord(id=i.id, code=i.code, email=i.email, role=i.role, expires_at=i.expires_at)
        for i in created
    ]
    return InviteGenerateResponse(invites=items)


@router.get("/metrics/summary", response_model=BetaMetricsSummaryResponse)
def get_beta_metrics_summary(db: Session = Depends(get_db), admin=Depends(require_role("admin"))):
    """Lightweight summary derived from in-process counters.

    Note: Without Prometheus remote-read, we return cumulative counts observed since process start.
    """
    # If Prometheus HTTP API is configured, prefer a true 24h window query
    if settings.prometheus_http_url:
        result = _fetch_prometheus_summary(
            settings.prometheus_http_url, settings.prometheus_bearer_token
        )
        if result is not None:
            return result

    # Fallback: in-process cumulative counters
    try:
        # Access private registry scrape (text) and parse simple totals
        data = prometheus_metrics.get_metrics().decode("utf-8")
        invites_sent_total = 0
        invites_error_total = 0
        phase_counts: dict[str, int] = {}
        for line in data.splitlines():
            if line.startswith("instainstru_service_operations_total"):
                if 'operation="beta_invite_sent"' in line:
                    # ... status="success" or error
                    if 'status="success"' in line:
                        try:
                            invites_sent_total += int(float(line.split(" ")[-1]))
                        except Exception:
                            pass
                    elif 'status="error"' in line:
                        try:
                            invites_error_total += int(float(line.split(" ")[-1]))
                        except Exception:
                            pass
            elif line.startswith("instainstru_beta_phase_header_total"):
                # instainstru_beta_phase_header_total{phase="open_beta"} 123
                try:
                    phase = line.split("{", 1)[1].split("}", 1)[0]
                    for part in phase.split(","):
                        if part.startswith("phase="):
                            val = part.split("=")[1].strip('"')
                            count = int(float(line.split(" ")[-1]))
                            phase_counts[val] = phase_counts.get(val, 0) + count
                except Exception:
                    pass
        return BetaMetricsSummaryResponse(
            invites_sent_24h=invites_sent_total,  # best-effort cumulative
            invites_errors_24h=invites_error_total,
            phase_counts_24h=phase_counts,
        )
    except Exception:
        return BetaMetricsSummaryResponse(
            invites_sent_24h=0, invites_errors_24h=0, phase_counts_24h={}
        )


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
def send_invite(
    payload: InviteSendRequest, db: Session = Depends(get_db), admin=Depends(require_role("admin"))
):
    svc = BetaService(db)
    invite, join_url, welcome_url = svc.send_invite_email(
        to_email=payload.to_email,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
        source=payload.source,
        base_url=payload.base_url,
    )
    return InviteSendResponse(
        id=invite.id,
        code=invite.code,
        email=payload.to_email,
        join_url=join_url,
        welcome_url=welcome_url,
    )


@router.post("/invites/send-batch", response_model=InviteBatchSendResponse)
def send_invite_batch(
    payload: InviteBatchSendRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    svc = BetaService(db)
    sent, failed = svc.send_invite_batch(
        emails=[str(e) for e in payload.emails],
        role=payload.role,
        expires_in_days=payload.expires_in_days,
        source=payload.source,
        base_url=payload.base_url,
    )
    sent_models = [
        InviteSendResponse(id=inv.id, code=inv.code, email=em, join_url=join, welcome_url=welcome)
        for (inv, em, join, welcome) in sent
    ]
    failed_models = [InviteBatchSendFailure(email=em, reason=reason) for (em, reason) in failed]
    return InviteBatchSendResponse(sent=sent_models, failed=failed_models)


@router.post("/invites/send-batch-async", response_model=InviteBatchAsyncStartResponse)
def send_invite_batch_async(
    payload: InviteBatchSendRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    task = celery_app.send_task(
        "app.tasks.email.send_beta_invites_batch",
        args=[
            list(map(str, payload.emails)),
            payload.role,
            payload.expires_in_days,
            payload.source,
            payload.base_url,
        ],
    )
    return InviteBatchAsyncStartResponse(task_id=task.id)


@router.get("/invites/send-batch-progress", response_model=InviteBatchProgressResponse)
def get_invite_batch_progress(task_id: str, admin=Depends(require_role("admin"))):
    result = celery_app.AsyncResult(task_id)
    meta = result.info or {}
    state = result.state or "PENDING"
    current = int(meta.get("current", 0))
    total = int(meta.get("total", 0))
    sent = int(meta.get("sent", 0))
    failed = int(meta.get("failed", 0))
    sent_items = meta.get("sent") or None
    failed_items = meta.get("failed") or None
    return InviteBatchProgressResponse(
        task_id=task_id,
        state=state,
        current=current,
        total=total,
        sent=sent,
        failed=failed,
        sent_items=sent_items,
        failed_items=failed_items,
    )


class BetaSettingsPayload(BaseModel):
    beta_disabled: bool
    beta_phase: str
    allow_signup_without_invite: bool


@router.get("/settings", response_model=BetaSettingsPayload)
def get_beta_settings(db: Session = Depends(get_db), admin=Depends(require_role("admin"))):
    repo = BetaSettingsRepository(db)
    s = repo.get_singleton()
    return BetaSettingsPayload(
        beta_disabled=bool(s.beta_disabled),
        beta_phase=str(s.beta_phase),
        allow_signup_without_invite=bool(s.allow_signup_without_invite),
    )


@router.put("/settings", response_model=BetaSettingsPayload)
def update_beta_settings(
    payload: BetaSettingsPayload,
    db: Session = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    repo = BetaSettingsRepository(db)
    rec = repo.update_settings(
        beta_disabled=payload.beta_disabled,
        beta_phase=payload.beta_phase,
        allow_signup_without_invite=payload.allow_signup_without_invite,
    )
    return BetaSettingsPayload(
        beta_disabled=bool(rec.beta_disabled),
        beta_phase=str(rec.beta_phase),
        allow_signup_without_invite=bool(rec.allow_signup_without_invite),
    )
