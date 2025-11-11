from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.database import SessionLocal
from app.schemas.main_responses import ReadyProbeResponse
from app.services.cache_service import get_healthcheck_redis_client

router = APIRouter(tags=["internal"])


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

    return ReadyProbeResponse(status="ok")
