# backend/app/routes/gated.py
"""
Tiny gated probe endpoint for CI smoke tests.

Returns 200 in preview (bypass short-circuits phase gate), and 401/403
in prod/beta when the phase is not open or beta checks are enforced.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import require_beta_phase_access
from app.schemas.gated_responses import GatedPingResponse
from app.utils.strict import model_filter

router = APIRouter(tags=["gated"])


def _enforce_no_query_params(request: Request) -> None:
    """Reject any unexpected query parameters with 422.

    This keeps the endpoint strict and mirrors extra-forbid semantics.
    """
    if len(request.query_params) > 0:
        # 422 Unprocessable Entity to align with validation errors
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="Unexpected query parameters are not allowed",
        )


@router.get(
    "/ping",
    response_model=GatedPingResponse,
    dependencies=[Depends(require_beta_phase_access())],
)
async def gated_ping(_strict: None = Depends(_enforce_no_query_params)) -> GatedPingResponse:
    response_payload = {"ok": True}
    return GatedPingResponse(**model_filter(GatedPingResponse, response_payload))
