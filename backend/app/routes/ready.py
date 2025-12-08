from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.database import SessionLocal
from app.schemas.main_responses import ReadyProbeResponse
from app.services.cache_service import get_healthcheck_redis_client

router = APIRouter(tags=["internal"])
logger = logging.getLogger(__name__)


@router.get("/ready", response_model=ReadyProbeResponse)
def ready_probe(response_obj: Response) -> ReadyProbeResponse:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        response_obj.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyProbeResponse(status="db_not_ready")

    try:
        client = get_healthcheck_redis_client()
        try:
            client.ping()
        finally:
            pool = getattr(client, "connection_pool", None)
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass
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
