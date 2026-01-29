"""MCP Admin endpoints for service catalog tools (service token auth)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.mcp import (
    MCPActor,
    MCPMeta,
    MCPServiceCatalogData,
    MCPServiceCatalogItem,
    MCPServiceCatalogResponse,
    MCPServiceLookupData,
    MCPServiceLookupResponse,
)
from app.services.mcp_service_catalog_service import MCPServiceCatalogService

router = APIRouter(tags=["MCP Admin - Services"])


@router.get(
    "/catalog",
    response_model=MCPServiceCatalogResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def list_service_catalog(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPServiceCatalogResponse:
    """List all services with canonical slugs and category mappings."""
    service = MCPServiceCatalogService(db)
    services = await asyncio.to_thread(service.list_catalog_services)
    items = [MCPServiceCatalogItem(**svc) for svc in services]

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(
            id=principal.id,
            email=principal.identifier,
            principal_type=principal.principal_type,
        ),
    )

    return MCPServiceCatalogResponse(
        meta=meta,
        data=MCPServiceCatalogData(
            services=items,
            count=len(items),
        ),
    )


@router.get(
    "/lookup",
    response_model=MCPServiceLookupResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def lookup_service_catalog(
    q: str = Query(..., min_length=2, description="Service name or slug to resolve"),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPServiceLookupResponse:
    """Resolve a service name or slug to canonical service records."""
    service = MCPServiceCatalogService(db)
    matches = await asyncio.to_thread(service.lookup_services, q)
    items = [MCPServiceCatalogItem(**svc) for svc in matches]
    message = None
    if not items:
        message = f"No services matched '{q}'."

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(
            id=principal.id,
            email=principal.identifier,
            principal_type=principal.principal_type,
        ),
    )

    return MCPServiceLookupResponse(
        meta=meta,
        data=MCPServiceLookupData(
            query=q,
            matches=items,
            count=len(items),
            message=message,
        ),
    )
