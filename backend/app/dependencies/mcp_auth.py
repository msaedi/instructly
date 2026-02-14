"""MCP authentication dependencies for service-to-service access."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
import logging
import secrets

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.core.config import secret_or_plain, settings
from app.database import get_db_session
from app.m2m_auth import verify_m2m_token
from app.principal import Principal, ServicePrincipal, UserPrincipal
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService, Status

logger = logging.getLogger(__name__)


async def get_mcp_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> Principal:
    """Validate MCP service authentication and return a Principal."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("mcp_auth_missing_header", extra={"path": request.url.path})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = auth_header[7:]

    claims = await verify_m2m_token(token)
    if claims:
        scopes = tuple(claims.scope.split()) if claims.scope else ()
        logger.info(
            "mcp_auth_m2m_jwt",
            extra={
                "client_id": claims.sub,
                "org_id": getattr(claims, "org_id", None),
                "scopes": scopes,
                "path": request.url.path,
            },
        )
        return ServicePrincipal(
            client_id=claims.sub,
            org_id=getattr(claims, "org_id", "") or "",
            scopes=scopes,
        )

    expected = secret_or_plain(settings.mcp_service_token).strip()
    if expected and secrets.compare_digest(token, expected):
        user_repo = UserRepository(db)
        service_user = await asyncio.to_thread(
            user_repo.get_by_email,
            settings.mcp_service_account_email,
        )
        if not service_user:
            logger.error(
                "mcp_service_account_missing",
                extra={"email": settings.mcp_service_account_email},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Service configuration error",
            )
        logger.info(
            "mcp_auth_static_token",
            extra={"path": request.url.path, "user_id": service_user.id},
        )
        return UserPrincipal(
            user_id=service_user.id,
            email=service_user.email or settings.mcp_service_account_email,
        )

    logger.warning(
        "mcp_auth_failed",
        extra={"path": request.url.path, "token_prefix": f"{token[:10]}..."},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid service token",
    )


def require_mcp_scope(required_scope: str) -> Callable[..., Awaitable[Principal]]:
    """Dependency factory that requires a specific scope."""

    async def _check_scope(principal: Principal = Depends(get_mcp_principal)) -> Principal:
        if isinstance(principal, ServicePrincipal):
            if not principal.has_scope(required_scope):
                logger.warning(
                    "mcp_scope_insufficient",
                    extra={
                        "required": required_scope,
                        "actual": principal.scopes,
                        "client_id": principal.id,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient scope. Required: {required_scope}",
                )
        return principal

    return _check_scope


async def audit_mcp_request(
    request: Request,
    principal: Principal = Depends(get_mcp_principal),
) -> AsyncGenerator[None, None]:
    """Audit MCP requests after they complete."""
    error_message: str | None = None
    status_value: Status = "success"
    try:
        yield
    except Exception as exc:
        status_value = "failed"
        error_message = str(exc)
        raise
    finally:
        with suppress(Exception):
            with get_db_session() as db:
                AuditService(db).log(
                    action=_mcp_action_from_path(request.url.path),
                    resource_type="mcp",
                    resource_id=_mcp_resource_id(request.url.path),
                    actor_type="mcp",
                    actor_id=principal.id,
                    actor_email=principal.identifier
                    if principal.principal_type == "user"
                    else None,
                    description=f"MCP {request.method} {request.url.path}",
                    metadata={
                        "method": request.method,
                        "path": request.url.path,
                        "principal_type": principal.principal_type,
                    },
                    status=status_value,
                    error_message=error_message,
                    request=request,
                )


def _mcp_action_from_path(path: str) -> str:
    prefix = "/api/v1/admin/mcp"
    if not (path == prefix or path.startswith(prefix + "/")):
        return "mcp.unknown"
    suffix = path[len(prefix) :].strip("/")
    if not suffix:
        return "mcp.root"
    return "mcp." + suffix.replace("/", ".")


def _mcp_resource_id(path: str) -> str | None:
    prefix = "/api/v1/admin/mcp"
    if not (path == prefix or path.startswith(prefix + "/")):
        return None
    parts = [part for part in path[len(prefix) :].split("/") if part]
    if not parts:
        return None
    last = parts[-1]
    if last.isdigit():
        return last
    if len(last) < 6:
        return None
    if any(char.isdigit() for char in last):
        return last
    return None
