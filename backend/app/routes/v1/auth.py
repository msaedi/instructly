# backend/app/routes/v1/auth.py
"""
Authentication routes - API v1

Versioned authentication endpoints under /api/v1/auth.
Handles user registration, login, session management, and profile updates.

Endpoints:
    POST /register                       → User registration
    POST /login                          → OAuth2 password login
    POST /login-with-session             → Login with guest session conversion
    POST /change-password                → Change password for authenticated user
    GET /me                              → Get current user with permissions
    PATCH /me                            → Update current user profile
"""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any, Optional, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...api.dependencies.services import get_auth_service, get_cache_service_dep
from ...auth import (
    DUMMY_HASH_FOR_TIMING_ATTACK,
    create_access_token,
    create_refresh_token,
    create_temp_token,
    decode_access_token,
    get_current_user,
    is_refresh_token_payload,
    verify_password_async,
)
from ...core.config import settings
from ...core.enums import RoleName
from ...core.exceptions import NotFoundException, ValidationException
from ...core.login_protection import (
    account_lockout,
    account_rate_limiter,
    captcha_verifier,
    login_slot,
    record_captcha_event,
    record_login_result,
)
from ...database import get_db
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.user import User
from ...ratelimit.dependency import rate_limit as bucket_rate_limit
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...schemas.auth_responses import (
    AuthUserWithPermissionsResponse,
    RegisterResponse,
)
from ...schemas.security import (
    LoginResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    SessionRefreshResponse,
)
from ...schemas.user import (
    UserCreate,
    UserLogin,
    UserUpdate,
)
from ...services.audit_service import AuditService
from ...services.auth_service import AuthService
from ...services.beta_service import BetaService
from ...services.cache_service import CacheService
from ...services.permission_service import PermissionService
from ...services.search_history_service import SearchHistoryService
from ...services.token_blacklist_service import TokenBlacklistService
from ...utils.cookies import (
    refresh_cookie_base_name,
    session_cookie_candidates,
    set_auth_cookies,
)
from ...utils.invite_cookie import invite_cookie_name
from ...utils.strict import model_filter
from ...utils.token_utils import parse_epoch_claim, parse_token_iat

logger = logging.getLogger(__name__)

# New device tracking config
KNOWN_DEVICE_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 days
KNOWN_DEVICE_MAX = 10

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["auth-v1"])


def _extract_request_token(request: Request) -> Optional[str]:
    """Extract the access token from Authorization header or session cookie."""
    auth_header = (request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token
    if hasattr(request, "cookies"):
        cookies = cast(dict[str, str], request.cookies)
        for cookie_name in session_cookie_candidates():
            token = cookies.get(cookie_name)
            if token:
                return token
    return None


async def _extract_captcha_token(request: Request) -> Optional[str]:
    """Return captcha_token from request form if present (OAuth2 form)."""
    try:
        form = await request.form()
        raw_value = form.get("captcha_token")
        return cast(Optional[str], raw_value)
    except Exception:
        return None


def _device_fingerprint(ip_address: str, user_agent: str) -> str:
    raw = f"{ip_address}:{user_agent}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _send_new_device_login_notification_sync(
    *, user_id: str, ip_address: str, user_agent: str, login_time: datetime
) -> None:
    from app.services.notification_service import NotificationService

    service = NotificationService()
    try:
        service.send_new_device_login_notification(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            login_time=login_time,
        )
    finally:
        if getattr(service, "_owns_db", False) and hasattr(service, "db"):
            service.db.close()


async def _maybe_send_new_device_login_notification(
    *,
    user_id: Optional[str],
    request: Request,
    cache_service: CacheService,
) -> None:
    if not user_id:
        return

    # Skip for newly registered users — they already received a welcome email
    recently_registered = await cache_service.get(f"recently_registered:{user_id}")
    if recently_registered:
        # Still register the device as known so future logins from it are silent
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "") or "unknown"
        fingerprint = _device_fingerprint(ip_address, user_agent)
        cache_key = f"known_devices:{user_id}"
        await cache_service.set(cache_key, [fingerprint], ttl=KNOWN_DEVICE_TTL_SECONDS)
        await cache_service.delete(f"recently_registered:{user_id}")
        return

    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "") or "unknown"
    fingerprint = _device_fingerprint(ip_address, user_agent)
    cache_key = f"known_devices:{user_id}"

    known_devices_raw = await cache_service.get(cache_key)
    known_devices: list[str] = (
        [str(item) for item in known_devices_raw] if isinstance(known_devices_raw, list) else []
    )

    if fingerprint in known_devices:
        return

    login_time = datetime.now(timezone.utc)
    try:
        await asyncio.to_thread(
            _send_new_device_login_notification_sync,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            login_time=login_time,
        )
        logger.info("New device login notification queued for user %s", user_id)
    except Exception as exc:
        logger.warning("Failed to send new device login notification: %s", exc)

    known_devices.append(fingerprint)
    if len(known_devices) > KNOWN_DEVICE_MAX:
        known_devices = known_devices[-KNOWN_DEVICE_MAX:]
    await cache_service.set(cache_key, known_devices, ttl=KNOWN_DEVICE_TTL_SECONDS)


def _send_password_changed_notification_sync(*, user_id: str, changed_at: datetime) -> None:
    from app.services.notification_service import NotificationService

    service = NotificationService()
    try:
        service.send_password_changed_notification(
            user_id=user_id,
            changed_at=changed_at,
        )
    finally:
        if getattr(service, "_owns_db", False) and hasattr(service, "db"):
            service.db.close()


def _should_trust_device(request: Request) -> bool:
    is_trusted_cookie = request.cookies.get("tfa_trusted") == "1"
    if is_trusted_cookie:
        return True
    if settings.environment != "production":
        trusted_header = cast(str | None, request.headers.get("X-Trusted-Bypass"))
        return (trusted_header or "false").lower() == "true"
    return False


def _issue_two_factor_challenge_if_needed(
    user: User, request: Request, extra_claims: dict[str, str] | None = None
) -> LoginResponse | None:
    if not getattr(user, "totp_enabled", False):
        return None

    if _should_trust_device(request):
        return None

    temp_claims = {"sub": user.email, "tfa_pending": True}
    if extra_claims:
        temp_claims.update(extra_claims)

    temp_token = create_temp_token(
        data=temp_claims,
        expires_delta=timedelta(seconds=60),
    )
    return LoginResponse(requires_2fa=True, temp_token=temp_token)


@router.post("/register", response_model=RegisterResponse)
@rate_limit(
    f"{settings.rate_limit_register_per_hour}/hour",
    key_type=RateLimitKeyType.IP,
    error_message="Too many registration attempts. Please try again later.",
)
async def register(
    request: Request,
    response: Response,
    payload: UserCreate = Body(...),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> RegisterResponse:
    """Register a new user. Always returns a generic response to prevent email enumeration."""
    generic_response = RegisterResponse(message="Please check your email to verify your account.")

    try:
        db_user = await asyncio.to_thread(
            auth_service.register_user,
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            zip_code=payload.zip_code,
            role=payload.role,
        )

        if db_user is None:
            # Existing email or race condition — return generic response
            return generic_response

        # --- New user: post-registration work (not visible in response) ---

        # Convert guest searches if guest_session_id provided
        if payload.guest_session_id:
            try:
                search_service = SearchHistoryService(db)
                converted_count = await asyncio.to_thread(
                    search_service.convert_guest_searches_to_user,
                    guest_session_id=payload.guest_session_id,
                    user_id=db_user.id,
                )
                logger.info(f"Converted {converted_count} guest searches for new user {db_user.id}")
            except Exception as e:
                logger.error(f"Failed to convert guest searches during registration: {str(e)}")

        # Beta invite consumption (server-side guarantee)
        try:
            invite_code = None
            metadata_obj = getattr(payload, "metadata", None)
            if metadata_obj is not None:
                if isinstance(metadata_obj, dict):
                    invite_code = metadata_obj.get("invite_code")
                else:
                    invite_code = getattr(metadata_obj, "invite_code", None)
            if invite_code:
                svc = BetaService(db)
                grant, reason, invite = await asyncio.to_thread(
                    svc.consume_and_grant,
                    code=str(invite_code),
                    user_id=db_user.id,
                    role=payload.role or "student",
                    phase="instructor_only",
                )
                if grant:
                    logger.info(f"Consumed beta invite for user {db_user.id} via register")
                else:
                    logger.warning(
                        f"Invite not consumed on register for user {db_user.id}: {reason}"
                    )
                if grant and invite and getattr(invite, "grant_founding_status", False):
                    role_name = (payload.role or RoleName.STUDENT).lower()
                    if role_name == RoleName.INSTRUCTOR.value:
                        repo = InstructorProfileRepository(db)
                        profile = await asyncio.to_thread(repo.get_by_user_id, db_user.id)
                        if profile:
                            granted, message = await asyncio.to_thread(
                                svc.try_grant_founding_status, profile.id
                            )
                            if granted:
                                logger.info(
                                    "Granted founding status for user %s: %s",
                                    db_user.id,
                                    message,
                                )
                            else:
                                logger.info(
                                    "Founding status not granted for user %s: %s",
                                    db_user.id,
                                    message,
                                )
        except Exception as e:
            logger.error(f"Error consuming invite on register for {db_user.id}: {e}")

        try:
            AuditService(db).log(
                action="user.create",
                resource_type="user",
                resource_id=db_user.id,
                actor=db_user,
                actor_type="user",
                description="User registered",
                metadata={"role": payload.role or RoleName.STUDENT.value},
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for user registration", exc_info=True)

        # Send welcome email and suppress new-device-login for initial login
        try:
            user_role = (payload.role or RoleName.STUDENT.value).lower()

            def _send_welcome_sync() -> None:
                from app.services.notification_service import NotificationService

                service = NotificationService(db)
                service.send_welcome_email(db_user.id, role=user_role)

            await asyncio.to_thread(_send_welcome_sync)
        except Exception:
            logger.warning("Welcome email failed for user %s", db_user.id, exc_info=True)

        try:
            await cache_service.set(f"recently_registered:{db_user.id}", True, ttl=300)
        except Exception:
            logger.debug("Failed to set recently_registered cache flag", exc_info=True)

        response.delete_cookie(
            key=invite_cookie_name(),
            path="/",
            domain=None,
        )

        return generic_response

    except ValidationException as e:
        raise e.to_http_exception()
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Error creating user",
                "code": "AUTH_UNEXPECTED_ERROR",
            },
        )


@router.post("/login", response_model=LoginResponse, response_model_exclude_none=True)
@rate_limit(
    f"{settings.rate_limit_auth_per_minute}/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many login attempts. Please try again later.",
)
async def login(
    request: Request,  # Add this for rate limiting
    response: Response,  # Add this to set cookies
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> LoginResponse:
    """
    Login with username (email) and password.

    Rate limited to prevent brute force attacks.

    PERFORMANCE OPTIMIZATION: This endpoint releases the DB connection BEFORE
    running Argon2id verification (~200ms). This reduces DB connection hold time
    from ~200ms to ~5-20ms, allowing 10x more concurrent logins.

    Args:
        form_data: OAuth2 form with username and password
        auth_service: Authentication service

    Returns:
        LoginResponse: Login result metadata for the client

    Raises:
        HTTPException: If credentials are invalid or rate limit exceeded
    """
    email_input = (form_data.username or "").strip()
    captcha_token = await _extract_captcha_token(request)
    client_ip = request.client.host if request.client else None

    # Check lockout first (cheapest)
    locked, lockout_info = await account_lockout.check_lockout(email_input)
    if locked:
        record_login_result("locked_out")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout_info.get("message", "Account temporarily locked. Try again later."),
            headers={"Retry-After": str(lockout_info.get("retry_after", 1))},
        )

    # CAPTCHA requirement based on prior failures
    captcha_required = await captcha_verifier.is_captcha_required(email_input)
    if captcha_required:
        record_captcha_event("required")
        if not captcha_token:
            record_login_result("captcha_required")
            record_captcha_event("missing")
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="CAPTCHA verification required",
                headers={"X-Captcha-Required": "true"},
            )

        captcha_valid = await captcha_verifier.verify(captcha_token, client_ip)
        if not captcha_valid:
            record_captcha_event("failed")
            record_login_result("captcha_failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="CAPTCHA verification failed"
            )
        record_captcha_event("passed")

    # Per-account rate limiting
    # Check rate limit (don't increment yet - only count failed attempts)
    allowed, rate_info = await account_rate_limiter.check(email_input)
    if not allowed:
        record_login_result("rate_limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_info["message"],
            headers={"Retry-After": str(rate_info.get("retry_after", 1))},
        )

    # Step 1: Fetch user data from DB (brief DB hold ~5-20ms)
    # CRITICAL: Run in thread pool to avoid blocking event loop under load
    user_data = await asyncio.to_thread(auth_service.fetch_user_for_auth, email_input)

    # Step 2: Extract data needed BEFORE releasing DB
    if user_data:
        user_id = user_data["id"]
        user_email = user_data["email"]
        hashed_password = user_data["hashed_password"]
        account_status = user_data.get("account_status")
        totp_enabled = user_data.get("totp_enabled", False)
        # Keep reference to user object for 2FA check (attributes already loaded)
        user_obj = user_data.get("_user_obj")
        # Beta claims pre-fetched in fetch_user_for_auth (no extra DB query needed)
        beta_claims = user_data.get("_beta_claims")
    else:
        user_id = None
        user_email = None
        hashed_password = DUMMY_HASH_FOR_TIMING_ATTACK
        account_status = None
        totp_enabled = False
        user_obj = None
        beta_claims = None

    # Step 3: Release DB connection BEFORE Argon2id verification (critical for throughput)
    await asyncio.to_thread(auth_service.release_connection)

    # Step 4: ONLY password verification is concurrency-capped
    async with login_slot():
        password_valid = await verify_password_async(form_data.password, hashed_password)

    # Step 5: Validate authentication result
    if not user_data or not password_valid:
        # Only count failed attempts toward rate limiting (better UX)
        await account_rate_limiter.record_attempt(email_input)
        await account_lockout.record_failure(email_input)
        record_login_result("invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Incorrect email or password",
                "code": "AUTH_INVALID_CREDENTIALS",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check account status - deactivated users cannot login
    if account_status == "deactivated":
        record_login_result("deactivated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Account has been deactivated",
                "code": "AUTH_ACCOUNT_DEACTIVATED",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 6: Check 2FA requirement (uses pre-loaded attributes, no DB needed)
    if user_obj and totp_enabled:
        two_factor_response = _issue_two_factor_challenge_if_needed(user_obj, request)
        if two_factor_response:
            await account_lockout.reset(email_input)
            await account_rate_limiter.reset(email_input)
            record_login_result("two_factor_challenge")
            return two_factor_response

    # Step 7: Create access token (no DB needed)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    _claims = {"sub": user_id, "email": user_email}

    access_token = create_access_token(
        data=_claims,
        expires_delta=access_token_expires,
        beta_claims=beta_claims,  # Pre-fetched in thread pool, no blocking DB call
    )
    refresh_token = create_refresh_token(
        data=_claims,
        expires_delta=timedelta(days=settings.refresh_token_lifetime_days),
    )

    # Success - reset counters
    await account_lockout.reset(email_input)
    await account_rate_limiter.reset(email_input)
    record_login_result("success")

    # Step 8: Set access + refresh cookies
    set_auth_cookies(response, access_token, refresh_token)

    if hasattr(cache_service, "get") and hasattr(cache_service, "set"):
        await _maybe_send_new_device_login_notification(
            user_id=user_id,
            request=request,
            cache_service=cache_service,
        )

    try:
        if user_id:
            AuditService(db).log(
                action="user.login",
                resource_type="user",
                resource_id=user_id,
                actor_type="user",
                actor_id=user_id,
                actor_email=user_email,
                description="User login",
                request=request,
            )
    except Exception:
        logger.warning("Audit log write failed for user login", exc_info=True)

    return LoginResponse(requires_2fa=False)


@router.post(
    "/refresh",
    response_model=SessionRefreshResponse,
    dependencies=[Depends(bucket_rate_limit("auth_refresh"))],
)
async def refresh_session_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionRefreshResponse:
    """Rotate refresh token and issue a new access token."""
    not_authenticated = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    cookie_name = refresh_cookie_base_name(settings.site_mode)
    token = request.cookies.get(cookie_name) if hasattr(request, "cookies") else None
    if not token:
        raise not_authenticated

    try:
        payload = decode_access_token(token)
    except Exception:
        raise invalid_credentials

    if not is_refresh_token_payload(payload):
        raise invalid_credentials

    user_id_obj = payload.get("sub")
    user_id = user_id_obj if isinstance(user_id_obj, str) else None
    if not user_id:
        raise invalid_credentials

    jti_obj = payload.get("jti")
    jti = jti_obj if isinstance(jti_obj, str) else None
    if not jti:
        raise invalid_credentials

    # --- Step 1: Validate user ---
    from app.repositories import RepositoryFactory

    user_repo = RepositoryFactory.create_user_repository(db)
    user = await asyncio.to_thread(user_repo.get_by_id, user_id)
    if not user or not user.is_active:
        raise invalid_credentials

    iat_ts = parse_token_iat(payload)
    if iat_ts is not None and user.tokens_valid_after is not None:
        if iat_ts < int(user.tokens_valid_after.timestamp()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # --- Step 2: Atomic JTI claim (SETNX) — only one caller wins ---
    old_exp_ts = parse_epoch_claim(payload, "exp")
    if old_exp_ts is None:
        raise invalid_credentials

    claimed = await TokenBlacklistService().claim_and_revoke(jti, old_exp_ts)
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Step 3: Issue new tokens (old JTI is now atomically blacklisted) ---
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = create_refresh_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(days=settings.refresh_token_lifetime_days),
    )

    set_auth_cookies(response, access_token, refresh_token)
    return SessionRefreshResponse(message="Session refreshed")


@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(
    payload: PasswordChangeRequest,
    http_request: Request,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> PasswordChangeResponse:
    """
    Change password for the current authenticated user.

    Verifies the current password, enforces minimal strength, and updates the hash.
    """
    # Get user object - run in thread pool to avoid blocking event loop
    user = await asyncio.to_thread(auth_service.get_current_user, current_user)

    # Verify current password - use async version for Argon2id
    from app.auth import get_password_hash

    if not await verify_password_async(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )

    # Basic strength checks
    new_pw = payload.new_password
    if len(new_pw) < 8 or new_pw.lower() == new_pw or not any(c.isdigit() for c in new_pw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="New password is too weak"
        )

    hashed = get_password_hash(new_pw)

    from app.repositories import RepositoryFactory

    user_repository = RepositoryFactory.create_user_repository(db)
    success = await asyncio.to_thread(user_repository.update_password, user.id, hashed)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update password"
        )

    invalidated = await asyncio.to_thread(
        user_repository.invalidate_all_tokens,
        user.id,
        trigger="password_change",
    )
    if not invalidated:
        logger.critical(
            "Password changed but token invalidation failed for user %s — old tokens remain valid",
            user.id,
        )

    # Belt-and-suspenders: also blacklist the current token's JTI for immediate
    # Redis-based rejection (tokens_valid_after handles the rest on next cache refresh).
    token = _extract_request_token(http_request)
    if token:
        try:
            tok_payload = decode_access_token(token, enforce_audience=False)
            jti = tok_payload.get("jti")
            exp_raw = tok_payload.get("exp")
            exp_ts = int(exp_raw) if isinstance(exp_raw, (int, float)) else None
            if isinstance(jti, str) and jti and exp_ts is not None:
                revoked = await TokenBlacklistService().revoke_token(
                    jti,
                    exp_ts,
                    trigger="password_change",
                    emit_metric=False,
                )
                if not revoked:
                    logger.error("Password-change blacklist write failed for jti=%s", jti)
        except Exception:
            logger.warning(
                "Failed to blacklist current token during password change", exc_info=True
            )

    try:
        await asyncio.to_thread(
            _send_password_changed_notification_sync,
            user_id=user.id,
            changed_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.warning("Failed to send password change notification: %s", exc)

    try:
        AuditService(db).log(
            action="user.password_change",
            resource_type="user",
            resource_id=user.id,
            actor_type="user",
            actor_id=user.id,
            actor_email=user.email,
            description="Password changed",
            request=http_request,
        )
    except Exception:
        logger.warning("Audit log write failed for password change", exc_info=True)

    return PasswordChangeResponse(message="Password changed successfully")


@router.post(
    "/login-with-session",
    response_model=LoginResponse,
    response_model_exclude_none=True,
)
@rate_limit(
    f"{settings.rate_limit_auth_per_minute}/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many login attempts. Please try again later.",
)
async def login_with_session(
    request: Request,
    response: Response,
    login_data: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> LoginResponse:
    """
    Login with email and password, optionally converting guest searches.

    This endpoint supports guest session conversion.

    PERFORMANCE OPTIMIZATION: This endpoint releases the DB connection BEFORE
    running Argon2id verification (~200ms). This reduces DB connection hold time
    from ~200ms to ~5-20ms, allowing 10x more concurrent logins.

    Args:
        login_data: Login credentials with optional guest_session_id
        auth_service: Authentication service
        db: Database session (used only for guest search conversion after auth)

    Returns:
        LoginResponse: Login result metadata for the client

    Raises:
        HTTPException: If credentials are invalid or rate limit exceeded
    """
    email_input = (login_data.email or "").strip()
    client_ip = request.client.host if request.client else None

    locked, lockout_info = await account_lockout.check_lockout(email_input)
    if locked:
        record_login_result("locked_out")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout_info.get("message", "Account temporarily locked. Try again later."),
            headers={"Retry-After": str(lockout_info.get("retry_after", 1))},
        )

    captcha_required = await captcha_verifier.is_captcha_required(email_input)
    if captcha_required:
        record_captcha_event("required")
        if not login_data.captcha_token:
            record_login_result("captcha_required")
            record_captcha_event("missing")
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="CAPTCHA verification required",
                headers={"X-Captcha-Required": "true"},
            )

        captcha_valid = await captcha_verifier.verify(login_data.captcha_token, client_ip)
        if not captcha_valid:
            record_captcha_event("failed")
            record_login_result("captcha_failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="CAPTCHA verification failed"
            )
        record_captcha_event("passed")

    # Check rate limit (don't increment yet - only count failed attempts)
    allowed, rate_info = await account_rate_limiter.check(email_input)
    if not allowed:
        record_login_result("rate_limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_info["message"],
            headers={"Retry-After": str(rate_info.get("retry_after", 1))},
        )

    # Step 1: Fetch user data from DB (brief DB hold ~5-20ms)
    # CRITICAL: Run in thread pool to avoid blocking event loop under load
    user_data = await asyncio.to_thread(auth_service.fetch_user_for_auth, email_input)

    # Step 2: Extract data needed BEFORE releasing DB
    if user_data:
        user_id = user_data["id"]
        user_email = user_data["email"]
        hashed_password = user_data["hashed_password"]
        account_status = user_data.get("account_status")
        totp_enabled = user_data.get("totp_enabled", False)
        user_obj = user_data.get("_user_obj")
        # Beta claims pre-fetched in fetch_user_for_auth (no extra DB query needed)
        beta_claims = user_data.get("_beta_claims")
    else:
        user_id = None
        user_email = None
        hashed_password = DUMMY_HASH_FOR_TIMING_ATTACK
        account_status = None
        totp_enabled = False
        user_obj = None
        beta_claims = None

    # Step 3: Release auth_service DB connection BEFORE Argon2id verification
    await asyncio.to_thread(auth_service.release_connection)

    # Step 4: ONLY password verification is concurrency-capped
    async with login_slot():
        password_valid = await verify_password_async(login_data.password, hashed_password)

    # Step 5: Validate authentication result
    if not user_data or not password_valid:
        # Only count failed attempts toward rate limiting (better UX)
        await account_rate_limiter.record_attempt(email_input)
        await account_lockout.record_failure(email_input)
        record_login_result("invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check account status
    if account_status == "deactivated":
        record_login_result("deactivated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 6: Check 2FA requirement
    extra_claims: dict[str, str] = {}
    if login_data.guest_session_id:
        extra_claims["guest_session_id"] = login_data.guest_session_id

    if user_obj and totp_enabled:
        two_factor_response = _issue_two_factor_challenge_if_needed(
            user_obj, request, extra_claims=extra_claims
        )
        if two_factor_response:
            await account_lockout.reset(email_input)
            await account_rate_limiter.reset(email_input)
            record_login_result("two_factor_challenge")
            return two_factor_response

    # Step 7: Create access token (no DB needed)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user_id, "email": user_email},
        expires_delta=access_token_expires,
        beta_claims=beta_claims,  # Pre-fetched in thread pool, no blocking DB call
    )
    refresh_token = create_refresh_token(
        data={"sub": user_id, "email": user_email},
        expires_delta=timedelta(days=settings.refresh_token_lifetime_days),
    )

    # Success - reset counters
    await account_lockout.reset(email_input)
    await account_rate_limiter.reset(email_input)
    record_login_result("success")

    # Step 8: Set access + refresh cookies
    set_auth_cookies(response, access_token, refresh_token)

    # Step 9: Convert guest searches if guest_session_id provided
    # Uses the separate `db` session (not auth_service.db which is closed)
    if login_data.guest_session_id and user_id:
        try:
            search_service = SearchHistoryService(db)
            converted_count = await asyncio.to_thread(
                search_service.convert_guest_searches_to_user,
                guest_session_id=login_data.guest_session_id,
                user_id=user_id,
            )
            logger.info(f"Converted {converted_count} guest searches for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to convert guest searches during login: {str(e)}")
            # Don't fail login if conversion fails

    if hasattr(cache_service, "get") and hasattr(cache_service, "set"):
        await _maybe_send_new_device_login_notification(
            user_id=user_id,
            request=request,
            cache_service=cache_service,
        )

    try:
        if user_id:
            AuditService(db).log(
                action="user.login",
                resource_type="user",
                resource_id=user_id,
                actor_type="user",
                actor_id=user_id,
                actor_email=user_email,
                description="User login (guest conversion)",
                request=request,
            )
    except Exception:
        logger.warning("Audit log write failed for user login", exc_info=True)
    return LoginResponse(requires_2fa=False)


@router.get("/me", response_model=AuthUserWithPermissionsResponse)
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AuthUserWithPermissionsResponse:
    """
    Get current user information with roles and permissions.

    PERFORMANCE OPTIMIZED (v4.4): Uses cached User from auth dependency.
    - Auth cache provides user with roles, permissions, AND beta_access (0 queries if cached)
    - Previous (v4.3): 1 query for beta_access, took 1322ms under 200 concurrent users
    - Now: ZERO queries when cache is warm, typically <5ms

    Args:
        current_user: User object from auth cache (has roles, permissions, beta_access cached)
        db: Database session (unused, kept for signature compatibility)

    Returns:
        AuthUserWithPermissionsResponse: Current user data with roles and permissions
    """
    # Use cached data from auth dependency - NO re-querying for user/roles/permissions!
    # The auth cache already loaded user with roles and permissions

    # Get cached role names (stored by create_transient_user)
    cached_role_names = getattr(current_user, "_cached_role_names", None)
    if cached_role_names is not None:
        roles = cached_role_names
    else:
        # Fallback for ORM users - extract role names from relationship
        roles = [role.name for role in current_user.roles]

    # Get cached permissions (stored by create_transient_user)
    cached_permissions = getattr(current_user, "_cached_permissions", None)
    if cached_permissions is not None:
        permissions = list(cached_permissions)
    else:
        # Fallback for ORM users - extract permissions from roles
        perms_set: set[str] = set()
        for role in current_user.roles:
            for perm in role.permissions:
                perms_set.add(perm.name)
        permissions = list(perms_set)

    # Get has_profile_picture (property on ORM, cached attribute on transient)
    cached_has_pic = getattr(current_user, "_cached_has_profile_picture", None)
    if cached_has_pic is not None:
        has_profile_picture = cached_has_pic
    else:
        has_profile_picture = getattr(current_user, "has_profile_picture", False)

    # Get cached beta_access (stored by create_transient_user from auth cache)
    cached_beta_access = getattr(current_user, "_cached_beta_access", None)
    cached_beta_role = getattr(current_user, "_cached_beta_role", None)
    cached_beta_phase = getattr(current_user, "_cached_beta_phase", None)
    cached_beta_invited_by = getattr(current_user, "_cached_beta_invited_by", None)

    # Build response using cached data
    response_data = {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "phone": getattr(current_user, "phone", None),
        "phone_verified": getattr(current_user, "phone_verified", False),
        "zip_code": getattr(current_user, "zip_code", None),
        "is_active": getattr(current_user, "is_active", True),
        "timezone": getattr(current_user, "timezone", None),
        "profile_picture_version": getattr(current_user, "profile_picture_version", 0),
        "has_profile_picture": has_profile_picture,
        "roles": roles,
        "permissions": permissions,
    }

    if cached_beta_access:
        response_data.update(
            {
                "beta_access": True,
                "beta_role": cached_beta_role,
                "beta_phase": cached_beta_phase,
                "beta_invited_by": cached_beta_invited_by,
            }
        )

    return AuthUserWithPermissionsResponse(
        **model_filter(AuthUserWithPermissionsResponse, response_data)
    )


@router.patch("/me", response_model=AuthUserWithPermissionsResponse)
async def update_current_user(
    request: Request,
    user_update: UserUpdate = Body(...),
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> AuthUserWithPermissionsResponse:
    """
    Update current user's profile (including timezone).

    Args:
        user_update: Fields to update
        current_user: Current user identifier from JWT
        auth_service: Authentication service
        db: Database session

    Returns:
        AuthUserWithPermissionsResponse: Updated user data

    Raises:
        HTTPException: If user not found or update fails
    """
    # TODO(security): if email change is added to this endpoint, call
    # UserRepository.invalidate_all_tokens(updated_user.id) after commit.
    try:
        # Wrap all sync DB operations in thread pool to avoid blocking event loop
        def _update_user_profile() -> tuple[Any, ...]:
            """Perform all DB ops in one thread."""
            u = auth_service.get_current_user(current_user)

            # Use repository for updates
            from app.repositories import RepositoryFactory

            user_repo = RepositoryFactory.create_user_repository(db)

            # Prepare update data
            upd_data: dict[str, Any] = {}
            audit_before: dict[str, Any] = {}
            if user_update.first_name is not None:
                audit_before["first_name"] = getattr(u, "first_name", None)
                upd_data["first_name"] = user_update.first_name
            if user_update.last_name is not None:
                audit_before["last_name"] = getattr(u, "last_name", None)
                upd_data["last_name"] = user_update.last_name
            if user_update.phone is not None:
                old_phone = getattr(u, "phone", None)
                audit_before["phone"] = old_phone
                upd_data["phone"] = user_update.phone
                if user_update.phone != old_phone:
                    upd_data["phone_verified"] = False

            # Handle zip code change with automatic timezone update
            if user_update.zip_code is not None:
                old_zip = u.zip_code
                audit_before["zip_code"] = old_zip
                audit_before["timezone"] = getattr(u, "timezone", None)
                upd_data["zip_code"] = user_update.zip_code

                # Auto-update timezone when zip code changes
                if old_zip != user_update.zip_code:
                    from app.core.timezone_service import get_timezone_from_zip

                    new_tz = get_timezone_from_zip(user_update.zip_code)
                    logger.info(
                        f"Updating timezone from {u.timezone} to {new_tz} for zip change {old_zip} -> {user_update.zip_code}"
                    )
                    upd_data["timezone"] = new_tz

            # Allow manual timezone override
            if user_update.timezone is not None:
                audit_before["timezone"] = getattr(u, "timezone", None)
                upd_data["timezone"] = user_update.timezone

            # Update using repository
            upd_user = user_repo.update_profile(u.id, **upd_data)

            if not upd_user:
                raise NotFoundException("Failed to update user")

            # Get permissions for the response
            perm_svc = PermissionService(db)
            perms = perm_svc.get_user_permissions(upd_user.id)
            r = perm_svc.get_user_roles(upd_user.id)
            audit_after = {key: getattr(upd_user, key, None) for key in audit_before.keys()}
            return upd_user, perms, r, audit_before, audit_after

        updated_user, permissions, roles, audit_before, audit_after = await asyncio.to_thread(
            _update_user_profile
        )

        response_data = {
            "id": updated_user.id,
            "email": updated_user.email,
            "first_name": updated_user.first_name,
            "last_name": updated_user.last_name,
            "phone": getattr(updated_user, "phone", None),
            "phone_verified": getattr(updated_user, "phone_verified", False),
            "zip_code": getattr(updated_user, "zip_code", None),
            "is_active": getattr(updated_user, "is_active", True),
            "timezone": getattr(updated_user, "timezone", None),
            "roles": roles,
            "permissions": list(permissions),
            "profile_picture_version": getattr(updated_user, "profile_picture_version", 0),
            "has_profile_picture": getattr(updated_user, "has_profile_picture", False),
        }

        try:
            AuditService(db).log_changes(
                action="user.update",
                resource_type="user",
                resource_id=updated_user.id,
                old_values=audit_before,
                new_values=audit_after,
                actor=updated_user,
                actor_type="user",
                description="User profile updated",
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for user update", exc_info=True)

        return AuthUserWithPermissionsResponse(
            **model_filter(AuthUserWithPermissionsResponse, response_data)
        )
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile",
        )


__all__ = ["router"]
