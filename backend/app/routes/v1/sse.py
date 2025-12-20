# backend/app/routes/v1/sse.py
"""
SSE support endpoints - API v1.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from ...api.dependencies.auth import get_current_active_user
from ...auth_sse import SSE_TOKEN_PREFIX, SSE_TOKEN_TTL_SECONDS
from ...core.cache_redis import get_async_cache_redis_client
from ...models.user import User

router = APIRouter(tags=["sse-v1"])


class SseTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    expires_in_s: int


@router.post(
    "/token",
    response_model=SseTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sse_token(
    current_user: User = Depends(get_current_active_user),
) -> SseTokenResponse:
    """Exchange a long-lived session for a short-lived SSE token."""
    redis = await get_async_cache_redis_client()
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSE token cache unavailable",
        )

    token = secrets.token_urlsafe(32)
    await redis.setex(
        f"{SSE_TOKEN_PREFIX}{token}",
        SSE_TOKEN_TTL_SECONDS,
        str(current_user.id),
    )

    return SseTokenResponse(token=token, expires_in_s=SSE_TOKEN_TTL_SECONDS)
