"""MCP authentication dependencies for service-to-service access."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.core.config import settings
from app.m2m_auth import verify_m2m_token
from app.principal import Principal, ServicePrincipal, UserPrincipal
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


def _secret_value(value: object | None) -> str:
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        return str(getter())
    return str(value)


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

    expected = _secret_value(settings.mcp_service_token).strip()
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


def require_mcp_scope(required_scope: str) -> Callable[[Principal], Principal]:
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
