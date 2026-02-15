# backend/app/routes/v1/two_factor_auth.py
"""
Two-Factor Authentication routes for InstaInstru platform (API v1).

This module provides endpoints for managing two-factor authentication,
including setup, verification, and disabling 2FA.
"""

from datetime import datetime, timedelta, timezone
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import jwt
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_current_user,
)
from app.core.config import settings
from app.database import get_db
from app.middleware.rate_limiter import RateLimitKeyType, rate_limit
from app.repositories.factory import RepositoryFactory
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.notification_service import NotificationService
from app.services.search_history_service import SearchHistoryService
from app.services.token_blacklist_service import TokenBlacklistService
from app.services.two_factor_auth_service import TwoFactorAuthService
from app.utils.cookies import (
    session_cookie_base_name,
    session_cookie_candidates,
    set_refresh_cookie,
    set_session_cookie,
)

from ...api.dependencies.services import get_auth_service
from ...schemas.security import (
    BackupCodesResponse,
    TFADisableRequest,
    TFADisableResponse,
    TFASetupInitiateResponse,
    TFASetupVerifyRequest,
    TFASetupVerifyResponse,
    TFAStatusResponse,
    TFAVerifyLoginRequest,
    TFAVerifyLoginResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["2fa"])


def _extract_request_token(request: Request) -> str | None:
    """Extract access token from Authorization header or session cookie."""
    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token
    if hasattr(request, "cookies"):
        for cookie_name in session_cookie_candidates():
            token = request.cookies.get(cookie_name)
            if token:
                return token
    return None


def _blacklist_current_token(request: Request, trigger: str) -> None:
    """Best-effort blacklist of the current request's token JTI."""
    token = _extract_request_token(request)
    if not token:
        return
    try:
        payload = decode_access_token(token, enforce_audience=False)
        jti = payload.get("jti")
        exp_raw = payload.get("exp")
        exp_ts = int(exp_raw) if isinstance(exp_raw, (int, float)) else None
        if isinstance(jti, str) and jti and exp_ts is not None:
            revoked = TokenBlacklistService().revoke_token_sync(
                jti,
                exp_ts,
                trigger=trigger,
                emit_metric=False,
            )
            if not revoked:
                logger.error("2FA %s blacklist write failed for jti=%s", trigger, jti)
    except Exception:
        logger.warning("Failed to blacklist current token during 2FA %s", trigger, exc_info=True)


def get_tfa_service(db: Session = Depends(get_db)) -> TwoFactorAuthService:
    return TwoFactorAuthService(db)


@router.post("/setup/initiate", response_model=TFASetupInitiateResponse)
@rate_limit(
    f"{settings.rate_limit_auth_per_minute}/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many 2FA setup attempts. Please try again later.",
)
def setup_initiate(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
) -> TFASetupInitiateResponse:
    user = auth_service.get_current_user(current_user)
    data = tfa_service.setup_initiate(user)
    return TFASetupInitiateResponse(**data)


@router.post("/setup/verify", response_model=TFASetupVerifyResponse)
def setup_verify(
    req: TFASetupVerifyRequest,
    response: Response,
    request: Request,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
) -> TFASetupVerifyResponse:
    user = auth_service.get_current_user(current_user)
    was_enabled = bool(getattr(user, "totp_enabled", False))
    try:
        backup_codes = tfa_service.setup_verify(user, req.code)
        user_repo = RepositoryFactory.create_user_repository(tfa_service.db)
        if not user_repo.invalidate_all_tokens(user.id, trigger="2fa_change"):
            logger.critical(
                "2FA enable succeeded but token invalidation returned false for %s — old tokens remain valid",
                user.id,
            )
        # Belt-and-suspenders: blacklist current token JTI for immediate rejection
        _blacklist_current_token(request, trigger="2fa_enable")
        # On successful re-setup, ensure trust cookie is cleared; user can re-trust on next verify
        response.delete_cookie(
            key="tfa_trusted",
            path="/",
            domain=None,  # Keep None so it matches current host
            secure=bool(settings.session_cookie_secure),
            samesite="lax",
        )
        try:
            notification_service = NotificationService(tfa_service.db)
            notification_service.send_two_factor_changed_notification(
                user_id=user.id,
                enabled=True,
                changed_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("Failed to send 2FA enabled notification for %s: %s", user.id, exc)
        try:
            AuditService(tfa_service.db).log_changes(
                action="user.2fa_enable",
                resource_type="user",
                resource_id=user.id,
                old_values={"totp_enabled": was_enabled},
                new_values={"totp_enabled": True},
                actor=user,
                actor_type="user",
                description="Two-factor authentication enabled",
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for 2FA enable", exc_info=True)
        return TFASetupVerifyResponse(enabled=True, backup_codes=backup_codes)
    except ValueError:
        # Return a user-friendly message without exposing internals
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code didn't work. Please check the 6-digit code and try again.",
        )


@router.post("/disable", response_model=TFADisableResponse)
def disable(
    req: TFADisableRequest,
    response: Response,
    request: Request,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
) -> TFADisableResponse:
    user = auth_service.get_current_user(current_user)
    was_enabled = bool(getattr(user, "totp_enabled", False))
    try:
        tfa_service.disable(user, req.current_password)
        user_repo = RepositoryFactory.create_user_repository(tfa_service.db)
        if not user_repo.invalidate_all_tokens(user.id, trigger="2fa_change"):
            logger.critical(
                "2FA disable succeeded but token invalidation returned false for %s — old tokens remain valid",
                user.id,
            )
        # Belt-and-suspenders: blacklist current token JTI for immediate rejection
        _blacklist_current_token(request, trigger="2fa_disable")
        # Invalidate any trusted-browser cookie on disable
        response.delete_cookie(
            key="tfa_trusted",
            path="/",
            domain=None,
            secure=bool(settings.session_cookie_secure),
            samesite="lax",
        )
        try:
            notification_service = NotificationService(tfa_service.db)
            notification_service.send_two_factor_changed_notification(
                user_id=user.id,
                enabled=False,
                changed_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("Failed to send 2FA disabled notification for %s: %s", user.id, exc)
        try:
            AuditService(tfa_service.db).log_changes(
                action="user.2fa_disable",
                resource_type="user",
                resource_id=user.id,
                old_values={"totp_enabled": was_enabled},
                new_values={"totp_enabled": False},
                actor=user,
                actor_type="user",
                description="Two-factor authentication disabled",
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for 2FA disable", exc_info=True)
        return TFADisableResponse(message="Two-factor authentication disabled")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/status", response_model=TFAStatusResponse)
def status_endpoint(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
) -> TFAStatusResponse:
    user = auth_service.get_current_user(current_user)
    data = tfa_service.status(user)
    return TFAStatusResponse(**data)


@router.post("/regenerate-backup-codes", response_model=BackupCodesResponse)
def regenerate_backup_codes(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
) -> BackupCodesResponse:
    user = auth_service.get_current_user(current_user)
    codes = tfa_service.generate_backup_codes()
    # Store hashed
    from app.auth import get_password_hash

    hashed = [get_password_hash(c) for c in codes]
    with tfa_service.transaction():
        user.backup_codes = hashed
        # Transaction context auto-commits on exit
    return BackupCodesResponse(backup_codes=codes)


@router.post(
    "/verify-login",
    response_model=TFAVerifyLoginResponse,
    response_model_exclude_none=True,
)
@rate_limit(
    f"{settings.rate_limit_auth_per_minute}/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many verification attempts. Please try again later.",
)
def verify_login(
    req: TFAVerifyLoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
) -> TFAVerifyLoginResponse:
    # temp_token is a short-lived JWT with sub=email and tfa_pending=true
    temp_secret = settings.temp_token_secret or settings.secret_key
    secret_value = getattr(temp_secret, "get_secret_value", None)
    secret_value = secret_value() if callable(secret_value) else str(temp_secret)
    try:
        payload = jwt.decode(
            req.temp_token,
            secret_value,
            algorithms=[settings.algorithm],
            audience=settings.temp_token_aud,
            issuer=settings.temp_token_iss,
        )
        email = payload.get("sub")
        tfa_pending = payload.get("tfa_pending", False)
        if not email or not tfa_pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid temp token"
            )
    except Exception as exc:
        site_mode = os.getenv("SITE_MODE", "").strip().lower()
        if settings.is_testing or site_mode in {"preview", "int", "stg"}:
            reason = getattr(exc, "args", ["decode_error"])[0]
            logger.info("2FA verify temp-token reject: %s", reason)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid temp token")

    user = auth_service.get_current_user(identifier=email)
    if not user or not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA not enabled")

    ok = tfa_service.verify_login(user, code=req.code, backup_code=req.backup_code)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code didn't work. Please check the 6-digit code or use a backup code.",
        )

    # Issue final access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(days=settings.refresh_token_lifetime_days),
    )
    # Write session cookie (API host only)
    site_mode = settings.site_mode
    base_cookie_name = session_cookie_base_name(site_mode)

    set_session_cookie(
        response,
        base_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        domain=settings.session_cookie_domain,
    )
    set_refresh_cookie(
        response,
        refresh_token,
        max_age=settings.refresh_token_lifetime_days * 24 * 60 * 60,
        domain=settings.session_cookie_domain,
    )

    guest_session_id = payload.get("guest_session_id")
    if guest_session_id:
        try:
            search_service = SearchHistoryService(tfa_service.db)
            converted_count = search_service.convert_guest_searches_to_user(
                guest_session_id=guest_session_id, user_id=user.id
            )
            logger.info(
                "Converted %s guest searches during post-2FA login for user %s",
                converted_count,
                user.id,
            )
        except Exception as exc:
            logger.error("Failed to convert guest searches after 2FA login: %s", exc)

    # Optionally set a trust cookie if client requested trust (header flag)
    trust_header = request.headers.get("X-Trust-Browser", "false").lower() == "true"
    if trust_header:
        max_age = settings.two_factor_trust_days * 24 * 60 * 60
        response.set_cookie(
            key="tfa_trusted",
            value="1",
            max_age=max_age,
            httponly=True,
            secure=bool(settings.session_cookie_secure),
            samesite=settings.session_cookie_samesite or "lax",
            path="/",
        )
    try:
        AuditService(tfa_service.db).log(
            action="user.login",
            resource_type="user",
            resource_id=user.id,
            actor_type="user",
            actor_id=user.id,
            actor_email=user.email,
            description="User login (2FA)",
            request=request,
        )
    except Exception:
        logger.warning("Audit log write failed for 2FA login", exc_info=True)

    return TFAVerifyLoginResponse()
