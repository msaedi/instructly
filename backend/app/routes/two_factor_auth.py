import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.core.config import settings
from app.database import get_db
from app.middleware.rate_limiter import RateLimitKeyType, rate_limit
from app.services.auth_service import AuthService
from app.services.two_factor_auth_service import TwoFactorAuthService

from ..api.dependencies.services import get_auth_service
from ..schemas.security import (
    BackupCodesResponse,
    LoginResponse,
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

router = APIRouter(prefix="/api/auth/2fa", tags=["2fa"])


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
):
    user = auth_service.get_current_user(email=current_user)
    data = tfa_service.setup_initiate(user)
    return TFASetupInitiateResponse(**data)


@router.post("/setup/verify", response_model=TFASetupVerifyResponse)
def setup_verify(
    req: TFASetupVerifyRequest,
    response: Response,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
):
    user = auth_service.get_current_user(email=current_user)
    try:
        backup_codes = tfa_service.setup_verify(user, req.code)
        # On successful re-setup, ensure trust cookie is cleared; user can re-trust on next verify
        response.delete_cookie(
            key="tfa_trusted",
            path="/",
            domain=None,  # Keep None so it matches current host
            secure=settings.environment == "production",
            samesite="lax",
        )
        return TFASetupVerifyResponse(enabled=True, backup_codes=backup_codes)
    except ValueError:
        # Return a user-friendly message without exposing internals
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code didn’t work. Please check the 6‑digit code and try again.",
        )


@router.post("/disable", response_model=TFADisableResponse)
def disable(
    req: TFADisableRequest,
    response: Response,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
):
    user = auth_service.get_current_user(email=current_user)
    try:
        tfa_service.disable(user, req.current_password)
        # Invalidate any trusted-browser cookie on disable
        response.delete_cookie(
            key="tfa_trusted",
            path="/",
            domain=None,
            secure=settings.environment == "production",
            samesite="lax",
        )
        return TFADisableResponse(message="Two-factor authentication disabled")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/status", response_model=TFAStatusResponse)
def status_endpoint(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
):
    user = auth_service.get_current_user(email=current_user)
    data = tfa_service.status(user)
    return TFAStatusResponse(**data)


@router.post("/regenerate-backup-codes", response_model=BackupCodesResponse)
def regenerate_backup_codes(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    tfa_service: TwoFactorAuthService = Depends(get_tfa_service),
):
    user = auth_service.get_current_user(email=current_user)
    codes = tfa_service.generate_backup_codes()
    # Store hashed
    from app.auth import get_password_hash

    hashed = [get_password_hash(c) for c in codes]
    with tfa_service.transaction():
        user.backup_codes = hashed
        tfa_service.db.commit()
    return BackupCodesResponse(backup_codes=codes)


@router.post("/verify-login", response_model=TFAVerifyLoginResponse)
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
):
    # temp_token is a normal JWT with sub=email and tfa_pending=true
    from jose import jwt

    try:
        payload = jwt.decode(
            req.temp_token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
        )
        email = payload.get("sub")
        tfa_pending = payload.get("tfa_pending", False)
        if not email or not tfa_pending:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid temp token")
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid temp token")

    user = auth_service.get_current_user(email=email)
    if not user or not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA not enabled")

    ok = tfa_service.verify_login(user, code=req.code, backup_code=req.backup_code)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code didn’t work. Please check the 6‑digit code or use a backup code.",
        )

    # Issue final access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    # Optionally set a trust cookie if client requested trust (header flag)
    trust_header = request.headers.get("X-Trust-Browser", "false").lower() == "true"
    if trust_header:
        max_age = settings.two_factor_trust_days * 24 * 60 * 60
        response.set_cookie(
            key="tfa_trusted",
            value="1",
            max_age=max_age,
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
            path="/",
        )
    return TFAVerifyLoginResponse(access_token=access_token, token_type="bearer")
