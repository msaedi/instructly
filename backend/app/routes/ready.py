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

    # Check notification service health (real-time messaging)
    # Import here to avoid circular dependency
    notifications_healthy: bool | None = None
    try:
        from app.routes.v1.messages import get_notification_service

        notification_service = get_notification_service()
        notifications_healthy = notification_service.is_healthy()

        if not notifications_healthy:
            logger.warning(
                "[MSG-DEBUG] /ready: Notification service is unhealthy",
                extra=notification_service.get_health_details(),
            )
            # Return degraded status but don't fail the probe
            # Real-time messaging is degraded but core functionality works
            return ReadyProbeResponse(
                status="degraded",
                notifications_healthy=False,
            )
    except Exception as e:
        # If notification service isn't available, log but don't fail
        logger.debug(f"[MSG-DEBUG] /ready: Could not check notification service: {e}")
        # notifications_healthy remains None (unknown)

    return ReadyProbeResponse(status="ok", notifications_healthy=notifications_healthy)
