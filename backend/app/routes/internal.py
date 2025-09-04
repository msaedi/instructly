import hmac
import os
from hashlib import sha256
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.ratelimit.config import get_effective_policy, reload_config

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _verify_hmac(request: Request) -> None:
    secret = os.getenv("CONFIG_RELOAD_SECRET", "").encode()
    if not secret:
        raise HTTPException(status_code=403, detail="reload disabled")
    sig = request.headers.get("X-Config-Reload-Signature", "")
    body = b""
    try:
        body = request.scope.get("body", b"")  # not always present
    except Exception:
        body = b""
    mac = hmac.new(secret, body, sha256).hexdigest()
    if not hmac.compare_digest(sig, mac):
        raise HTTPException(status_code=403, detail="invalid signature")


@router.post("/config/reload", response_model="InternalReloadResponse")
async def reload_endpoint(request: Request) -> "InternalReloadResponse":
    _verify_hmac(request)
    info = reload_config()
    return InternalReloadResponse(
        ok=True,
        enabled=bool(info.get("enabled")),
        shadow=bool(info.get("shadow")),
        bucket_shadows=info.get("bucket_shadows") or {},
        policy_overrides_count=int(info.get("policy_overrides_count", 0)),
    )


@router.get("/rate-limit/policy", response_model="PolicyResponse")
async def policy_introspection(
    route: Optional[str] = None, method: Optional[str] = None, bucket: str = "read"
) -> "PolicyResponse":
    policy = get_effective_policy(route, method, bucket)
    return PolicyResponse(
        bucket=str(policy.get("bucket", bucket)),
        rate_per_min=int(policy.get("rate_per_min", 60)),
        burst=int(policy.get("burst", 0)),
        window_s=int(policy.get("window_s", 60)),
        shadow=bool(policy.get("shadow", False)),
    )


class InternalReloadResponse(BaseModel):
    ok: bool
    enabled: bool
    shadow: bool
    bucket_shadows: Dict[str, bool]
    policy_overrides_count: int


class PolicyResponse(BaseModel):
    bucket: str
    rate_per_min: int
    burst: int
    window_s: int
    shadow: bool
