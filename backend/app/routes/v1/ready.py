from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.database import SessionLocal
from app.schemas.main_responses import ReadyProbeResponse
from app.services.cache_service import get_healthcheck_redis_client

router = APIRouter(tags=["internal"])
logger = logging.getLogger(__name__)


@router.get("", response_model=ReadyProbeResponse)
async def ready_probe(response_obj: Response) -> ReadyProbeResponse:
    try:

        def _db_probe() -> None:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
                session.rollback()  # Clean up transaction before returning to pool

        await asyncio.to_thread(_db_probe)
    except Exception:
        response_obj.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyProbeResponse(status="db_not_ready")

    try:
        client_candidate: Any = get_healthcheck_redis_client()
        client: Any
        if inspect.isawaitable(client_candidate):
            client = await client_candidate
        else:
            client = client_candidate
        if client is None:
            raise RuntimeError("Redis unavailable")
        ping_candidate: Any = client.ping()
        if inspect.isawaitable(ping_candidate):
            await ping_candidate
    except Exception:
        response_obj.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyProbeResponse(status="cache_not_ready")

    # Check Broadcaster health (real-time SSE messaging via multiplexer)
    notifications_healthy: bool | None = None
    try:
        from app.core.broadcast import is_broadcast_initialized

        notifications_healthy = is_broadcast_initialized()

        if not notifications_healthy:
            logger.warning("[BROADCAST] /ready: SSE multiplexer not initialized")
            # Return degraded status but don't fail the probe
            return ReadyProbeResponse(
                status="degraded",
                notifications_healthy=False,
            )
    except Exception as e:
        # If messaging health can't be determined, log but don't fail
        logger.debug(f"[BROADCAST] /ready: Could not check messaging health: {e}")
        # notifications_healthy remains None (unknown)

    return ReadyProbeResponse(status="ok", notifications_healthy=notifications_healthy)
