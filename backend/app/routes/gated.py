# backend/app/routes/gated.py
"""
Tiny gated probe endpoint for CI smoke tests.

Returns 200 in preview (bypass short-circuits phase gate), and 401/403
in prod/beta when the phase is not open or beta checks are enforced.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..api.dependencies.auth import require_beta_phase_access

router = APIRouter(prefix="/v1/gated", tags=["gated"])


class GatedPingResponse(BaseModel):
    ok: bool


@router.get(
    "/ping",
    response_model=GatedPingResponse,
    dependencies=[Depends(require_beta_phase_access())],
)
async def gated_ping() -> GatedPingResponse:
    return GatedPingResponse(ok=True)
