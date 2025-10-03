# backend/app/api/dependencies/auth.py
"""
Authentication and authorization dependencies.
"""

import hmac
import logging
import os
from typing import Awaitable, Callable, Optional, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...auth import (
    get_current_user as auth_get_current_user,
    get_current_user_optional as auth_get_current_user_optional,
)
from ...core.config import settings
from ...models.user import User
from ...monitoring.prometheus_metrics import prometheus_metrics
from ...repositories.beta_repository import BetaAccessRepository, BetaSettingsRepository

logger = logging.getLogger(__name__)


def _from_preview_origin(request: Request) -> bool:
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    xfhost = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").lower()
    api_host = request.url.hostname.lower() if request.url and request.url.hostname else ""
    front_ok = (
        settings.preview_frontend_domain in origin or settings.preview_frontend_domain in referer
    )
    api_ok = settings.preview_api_domain in xfhost or settings.preview_api_domain in api_host
    return bool(front_ok and api_ok)


def _preview_bypass(request: Request, user: User | None) -> bool:
    # Kill-switch: allow disabling bypass entirely via env
    if os.getenv("PREVIEW_BYPASS_ENABLED", "true").lower().strip() != "true":
        return False
    if os.getenv("SITE_MODE", "").lower().strip() != "preview":
        return False
    # Double-key to preview hosts only
    if not _from_preview_origin(request):
        return False
    # Never consider preview bypass for webhook calls
    try:
        path_l = (request.url.path or "").lower()
        if "webhook" in path_l:
            return False
    except Exception:
        pass
    # Prefer staff session/claim when available
    if getattr(user, "is_staff", False):
        try:
            logger.info(
                "preview_bypass",
                extra={
                    "event": "preview_bypass",
                    "route": request.url.path if request and request.url else "",
                    "user_id": getattr(user, "id", None),
                    "staff": True,
                    "origin": (request.headers.get("origin") or "").lower(),
                    "host": (
                        request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
                    ).lower(),
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent", ""),
                },
            )
            prometheus_metrics.inc_preview_bypass("session")
        except Exception:
            pass
        return True
    # Optional header path (only if explicitly allowed) – must come from preview origins
    if settings.allow_preview_header and _from_preview_origin(request):
        token = request.headers.get("x-staff-preview-token", "")
        if (
            token
            and settings.staff_preview_token
            and hmac.compare_digest(token, settings.staff_preview_token)
        ):
            try:
                logger.info(
                    "preview_bypass",
                    extra={
                        "event": "preview_bypass",
                        "route": request.url.path if request and request.url else "",
                        "user_id": getattr(user, "id", None),
                        "staff": getattr(user, "is_staff", False),
                        "origin": (request.headers.get("origin") or "").lower(),
                        "host": (
                            request.headers.get("x-forwarded-host")
                            or request.headers.get("host")
                            or ""
                        ).lower(),
                        "client_ip": request.client.host if request.client else None,
                        "user_agent": request.headers.get("user-agent", ""),
                        "via": "header",
                    },
                )
                prometheus_metrics.inc_preview_bypass("header")
            except Exception:
                pass
            return True
    return False


from .database import get_db


def _testing_bypass(request: Request | None) -> bool:
    """Return True when test mode should bypass beta/phase gates.

    - Respects explicit enforcement via header: x-enforce-beta-checks=1
    - Works whenever settings.is_testing is truthy, regardless of SITE_MODE
    """
    try:
        if request and request.headers.get("x-enforce-beta-checks") == "1":
            return False
    except Exception:
        pass
    return bool(getattr(settings, "is_testing", False))


async def get_current_user(
    request: Request,
    current_user_email: str = Depends(auth_get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from the database.

    Args:
        current_user_email: Email from JWT token
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If user not found
    """
    # Backward-compat for tests that call get_current_user(email, db) positionally
    # In that case, request is a string (email) and current_user_email is a Session/Mock
    if not isinstance(current_user_email, str) and isinstance(request, str):
        # Swap into expected variables; ignore request in this mode
        swap_db = current_user_email if hasattr(current_user_email, "query") else db
        if not hasattr(swap_db, "query"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid database session for current user lookup",
            )
        current_user_email = request
        db = cast(Session, swap_db)
        request = None

    # Some tests might pass a Depends(...) sentinel for db; guard for real Session
    try:
        session: Optional[Session] = db if hasattr(db, "query") else None
    except Exception:
        session = None
    created = False
    if session is None:
        try:
            from ...database import SessionLocal

            session = SessionLocal()
            created = True
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection failed",
            )

    try:
        user = cast(
            Optional[User], session.query(User).filter(User.email == current_user_email).first()
        )
    finally:
        if created and session is not None:
            try:
                session.close()
            except Exception:
                pass
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Preview-only impersonation for staff (header: X-Impersonate-User-Id)
    try:
        if (
            request is not None
            and hasattr(request, "headers")
            and _preview_bypass(request, user)
            and getattr(user, "is_staff", False)
        ):
            imp_id = request.headers.get("x-impersonate-user-id", "").strip()
            if imp_id:
                active_session: Session = session if session is not None else db
                imp = cast(
                    Optional[User],
                    active_session.query(User).filter(User.id == imp_id).first(),
                )
                if imp:
                    logger.info(
                        "preview_impersonation",
                        extra={
                            "event": "preview_impersonation",
                            "route": request.url.path
                            if request and getattr(request, "url", None)
                            else "",
                            "staff_user_id": getattr(user, "id", None),
                            "impersonated_user_id": imp_id,
                            "origin": (request.headers.get("origin") or "").lower(),
                            "client_ip": request.client.host
                            if getattr(request, "client", None)
                            else None,
                        },
                    )
                    return imp
    except Exception:
        # Non-fatal: continue with actual user
        pass
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current authenticated and active user.

    Args:
        current_user: Current authenticated user

    Returns:
        User object if active

    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def get_current_instructor(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get the current authenticated instructor.

    Args:
        current_user: Current active user

    Returns:
        User object if instructor

    Raises:
        HTTPException: If user is not an instructor
    """
    if not current_user.is_instructor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an instructor")
    return current_user


async def get_current_student(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get the current authenticated student.

    Args:
        current_user: Current active user

    Returns:
        User object if student

    Raises:
        HTTPException: If user is not a student
    """
    if not current_user.is_student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a student")
    return current_user


async def get_current_active_user_optional(
    current_user_email: Optional[str] = Depends(auth_get_current_user_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get the current authenticated user if present, otherwise return None.

    This is useful for endpoints that work for both authenticated and anonymous users,
    but provide enhanced functionality for authenticated users.

    Args:
        current_user_email: Email from JWT token (if present)
        db: Database session

    Returns:
        User object if authenticated and found, None otherwise
    """
    if not current_user_email:
        return None

    user = cast(Optional[User], db.query(User).filter(User.email == current_user_email).first())
    if user and user.is_active:
        return user

    return None


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the caller has administrator privileges."""

    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_beta_access(role: Optional[str] = None) -> Callable[..., Awaitable[User]]:
    async def verify_beta(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Preview bypass (staff or proxy-only header)
        if _preview_bypass(request, current_user):
            return current_user

        # Testing bypass (independent of SITE_MODE; still overridable via header)
        if _testing_bypass(request):
            return current_user
        if getattr(settings, "beta_disabled", False):
            return current_user
        repo = BetaAccessRepository(db)
        beta = repo.get_latest_for_user(current_user.id)
        if not beta:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Beta access required"
            )
        if role and beta.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Beta {role} access required"
            )
        return current_user

    return verify_beta


def require_beta_phase_access(
    _expected_phase: Optional[str] = None,
) -> Callable[..., Awaitable[None]]:
    """Phase gate with preview as unconditional no-op.

    Behavior:
    - Preview: Always pass (no beta gating on preview).
    - Testing: If testing bypass active (default in tests), pass unless header x-enforce-beta-checks=1.
    - If beta is disabled (settings or DB), pass.
    - If phase is open (open_beta/open/ga), pass.
    - Else (e.g., instructor_only), require that the current user has a BetaAccess grant.
    """

    async def verify_phase(
        request: Request,
        current_user: Optional[User] = Depends(get_current_active_user_optional),
        db: Session = Depends(get_db),
    ) -> None:
        # 1) Preview means no gates
        site_mode = os.getenv("SITE_MODE", "").lower().strip() or "prod"
        if site_mode == "preview":
            return None

        # 2) Testing bypass (independent of SITE_MODE; can be disabled per-request)
        if _testing_bypass(request):
            return None

        # 3) Global beta disabled flags
        if getattr(settings, "beta_disabled", False):
            return None
        settings_repo = BetaSettingsRepository(db)
        s = settings_repo.get_singleton()
        if s and bool(getattr(s, "beta_disabled", False)):
            return None

        # 4) If phase is open, allow
        current_phase = str(getattr(s, "beta_phase", "instructor_only") or "").lower()
        if current_phase in {"open_beta", "open", "openbeta", "ga", "general_availability"}:
            return None

        # 5) Otherwise enforce that user has a BetaAccess grant
        # If the route also requires auth, current_user will be set; otherwise it may be None.
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Beta access required"
            )

        repo = BetaAccessRepository(db)
        beta = repo.get_latest_for_user(current_user.id)
        if not beta:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Beta access required"
            )

        return None

    return verify_phase
