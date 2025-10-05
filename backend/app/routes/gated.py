# backend/app/routes/gated.py
"""
Tiny gated probe endpoint for CI smoke tests.

Returns 200 in preview (bypass short-circuits phase gate), and 401/403
in prod/beta when the phase is not open or beta checks are enforced.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ConfigDict

from ..api.dependencies.auth import require_beta_phase_access
from ..schemas._strict_base import StrictModel

router = APIRouter(prefix="/v1/gated", tags=["gated"])


class GatedPingResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    ok: bool


def _enforce_no_query_params(request: Request) -> None:
    """Reject any unexpected query parameters with 422.

    This keeps the endpoint strict and mirrors extra-forbid semantics.
    """
    if len(request.query_params) > 0:
        # 422 Unprocessable Entity to align with validation errors
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unexpected query parameters are not allowed",
        )


@router.get(
    "/ping",
    response_model=GatedPingResponse,
    dependencies=[Depends(require_beta_phase_access())],
)
async def gated_ping(_strict: None = Depends(_enforce_no_query_params)) -> GatedPingResponse:
    return GatedPingResponse(ok=True)
