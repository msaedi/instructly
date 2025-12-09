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
from datetime import timedelta
import logging
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ...api.dependencies.services import get_auth_service
from ...auth import (
    DUMMY_HASH_FOR_TIMING_ATTACK,
    create_access_token,
    create_temp_token,
    get_current_user,
    verify_password_async,
)
from ...core.config import settings
from ...core.exceptions import ConflictException, NotFoundException, ValidationException
from ...database import get_db
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.user import User
from ...schemas.auth_responses import (
    AuthUserResponse,
    AuthUserWithPermissionsResponse,
)
from ...schemas.security import LoginResponse, PasswordChangeRequest, PasswordChangeResponse
from ...schemas.user import (
    UserCreate,
    UserLogin,
    UserUpdate,
)
from ...services.auth_service import AuthService
from ...services.beta_service import BetaService
from ...services.permission_service import PermissionService
from ...services.search_history_service import SearchHistoryService
from ...utils.cookies import (
    expire_parent_domain_cookie,
    session_cookie_base_name,
    set_session_cookie,
)
from ...utils.invite_cookie import invite_cookie_name
from ...utils.strict import model_filter

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["auth-v1"])


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


@router.post("/register", response_model=AuthUserResponse, status_code=status.HTTP_201_CREATED)
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
) -> AuthUserResponse:
    """
    Register a new user.

    Rate limited to prevent spam registrations.

    Args:
        payload: User creation data (including optional guest_session_id)
        auth_service: Authentication service
        db: Database session

    Returns:
        AuthUserResponse: The created user

    Raises:
        HTTPException: If email already registered or rate limit exceeded
    """
    try:
        db_user = auth_service.register_user(
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            zip_code=payload.zip_code,
            role=payload.role,
        )

        # Convert guest searches if guest_session_id provided
        if payload.guest_session_id:
            try:
                search_service = SearchHistoryService(db)
                converted_count = search_service.convert_guest_searches_to_user(
                    guest_session_id=payload.guest_session_id, user_id=db_user.id
                )
                logger.info(f"Converted {converted_count} guest searches for new user {db_user.id}")
            except Exception as e:
                logger.error(f"Failed to convert guest searches during registration: {str(e)}")
                # Don't fail registration if conversion fails

        # Beta invite consumption (server-side guarantee)
        try:
            invite_code = None
            metadata_obj = getattr(payload, "metadata", None)
            if isinstance(metadata_obj, dict):
                invite_code = metadata_obj.get("invite_code")
            if invite_code:
                svc = BetaService(db)
                grant, reason = svc.consume_and_grant(
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
        except Exception as e:
            # Log only; do not block registration if invite handling fails
            logger.error(f"Error consuming invite on register for {db_user.id}: {e}")

        response_data = {
            "id": db_user.id,
            "email": db_user.email,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "phone": getattr(db_user, "phone", None),
            "zip_code": getattr(db_user, "zip_code", None),
            "is_active": getattr(db_user, "is_active", True),
            "timezone": getattr(db_user, "timezone", None),
            "roles": [role.name for role in getattr(db_user, "roles", [])],
            "permissions": [],
            "profile_picture_version": getattr(db_user, "profile_picture_version", 0),
            "has_profile_picture": getattr(db_user, "has_profile_picture", False),
        }
        user_payload = AuthUserResponse(**model_filter(AuthUserResponse, response_data))

        # Clear invite verification cookie after successful registration
        response.delete_cookie(
            key=invite_cookie_name(),
            path="/",
            domain=None,
        )

        return user_payload
    except ValidationException as e:
        raise e.to_http_exception()
    except ConflictException as e:
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


@router.post("/login", response_model=LoginResponse)
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
) -> LoginResponse:
    """
    Login with username (email) and password.

    Rate limited to prevent brute force attacks.

    PERFORMANCE OPTIMIZATION: This endpoint releases the DB connection BEFORE
    running bcrypt verification (~200ms). This reduces DB connection hold time
    from ~200ms to ~5-20ms, allowing 10x more concurrent logins.

    Args:
        form_data: OAuth2 form with username and password
        auth_service: Authentication service

    Returns:
        LoginResponse: Access token metadata for the client

    Raises:
        HTTPException: If credentials are invalid or rate limit exceeded
    """
    # Step 1: Fetch user data from DB (brief DB hold ~5-20ms)
    # CRITICAL: Run in thread pool to avoid blocking event loop under load
    user_data = await asyncio.to_thread(auth_service.fetch_user_for_auth, form_data.username)

    # Step 2: Extract data needed BEFORE releasing DB
    if user_data:
        user_email = user_data["email"]
        hashed_password = user_data["hashed_password"]
        account_status = user_data.get("account_status")
        totp_enabled = user_data.get("totp_enabled", False)
        # Keep reference to user object for 2FA check (attributes already loaded)
        user_obj = user_data.get("_user_obj")
        # Beta claims pre-fetched in fetch_user_for_auth (no extra DB query needed)
        beta_claims = user_data.get("_beta_claims")
    else:
        user_email = None
        hashed_password = DUMMY_HASH_FOR_TIMING_ATTACK
        account_status = None
        totp_enabled = False
        user_obj = None
        beta_claims = None

    # Step 3: Release DB connection BEFORE bcrypt (critical for throughput)
    # The auth_service.db session will be released by FastAPI after response,
    # but we ensure no further DB operations happen during bcrypt.
    # For explicit control, close the underlying session:
    try:
        auth_service.db.close()
    except Exception:
        pass  # Session may already be closed or in different state

    # Step 4: Run bcrypt verification (~200ms, no DB held)
    password_valid = await verify_password_async(form_data.password, hashed_password)

    # Step 5: Validate authentication result
    if not user_data or not password_valid:
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
            return two_factor_response

    # Step 7: Create access token (no DB needed)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    import os as _os_jwt

    _site_mode_jwt = _os_jwt.getenv("SITE_MODE", "").lower().strip()
    _claims = {"sub": user_email}
    if _site_mode_jwt == "preview":
        _claims.update({"aud": "preview", "iss": f"https://{settings.preview_api_domain}"})
    elif _site_mode_jwt in {"prod", "production", "live"}:
        _claims.update({"aud": "prod", "iss": f"https://{settings.prod_api_domain}"})

    access_token = create_access_token(
        data=_claims,
        expires_delta=access_token_expires,
        beta_claims=beta_claims,  # Pre-fetched in thread pool, no blocking DB call
    )

    # Step 8: Set cookie for SSE authentication (no DB needed)
    site_mode = settings.site_mode
    base_cookie_name = session_cookie_base_name(site_mode)

    set_session_cookie(
        response,
        base_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        domain=settings.session_cookie_domain,
    )

    if site_mode != "local":
        expire_parent_domain_cookie(response, base_cookie_name, ".instainstru.com")

    return LoginResponse(access_token=access_token, token_type="bearer", requires_2fa=False)


@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(
    request: PasswordChangeRequest,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> PasswordChangeResponse:
    """
    Change password for the current authenticated user.

    Verifies the current password, enforces minimal strength, and updates the hash.
    """
    # Get user object - run in thread pool to avoid blocking event loop
    user = await asyncio.to_thread(auth_service.get_current_user, email=current_user)

    # Verify current password - use async version for bcrypt
    from app.auth import get_password_hash

    if not await verify_password_async(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )

    # Basic strength checks
    new_pw = request.new_password
    if len(new_pw) < 8 or new_pw.lower() == new_pw or not any(c.isdigit() for c in new_pw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="New password is too weak"
        )

    hashed = get_password_hash(new_pw)

    from app.repositories import RepositoryFactory

    user_repository = RepositoryFactory.create_user_repository(db)
    success = user_repository.update_password(user.id, hashed)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update password"
        )

    return PasswordChangeResponse(message="Password changed successfully")


@router.post("/login-with-session", response_model=LoginResponse)
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
) -> LoginResponse:
    """
    Login with email and password, optionally converting guest searches.

    This endpoint supports guest session conversion.

    PERFORMANCE OPTIMIZATION: This endpoint releases the DB connection BEFORE
    running bcrypt verification (~200ms). This reduces DB connection hold time
    from ~200ms to ~5-20ms, allowing 10x more concurrent logins.

    Args:
        login_data: Login credentials with optional guest_session_id
        auth_service: Authentication service
        db: Database session (used only for guest search conversion after auth)

    Returns:
        LoginResponse: Access token metadata for the client

    Raises:
        HTTPException: If credentials are invalid or rate limit exceeded
    """
    # Step 1: Fetch user data from DB (brief DB hold ~5-20ms)
    # CRITICAL: Run in thread pool to avoid blocking event loop under load
    user_data = await asyncio.to_thread(auth_service.fetch_user_for_auth, login_data.email)

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

    # Step 3: Release auth_service DB connection BEFORE bcrypt
    # Note: The `db` session (separate dependency) is kept for guest search conversion
    try:
        auth_service.db.close()
    except Exception:
        pass

    # Step 4: Run bcrypt verification (~200ms, auth_service.db released)
    password_valid = await verify_password_async(login_data.password, hashed_password)

    # Step 5: Validate authentication result
    if not user_data or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check account status
    if account_status == "deactivated":
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
            return two_factor_response

    # Step 7: Create access token (no DB needed)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user_email},
        expires_delta=access_token_expires,
        beta_claims=beta_claims,  # Pre-fetched in thread pool, no blocking DB call
    )

    # Step 8: Set cookie for SSE authentication
    site_mode = settings.site_mode
    base_cookie_name = session_cookie_base_name(site_mode)

    set_session_cookie(
        response,
        base_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        domain=settings.session_cookie_domain,
    )

    if site_mode != "local":
        expire_parent_domain_cookie(response, base_cookie_name, ".instainstru.com")

    # Step 9: Convert guest searches if guest_session_id provided
    # Uses the separate `db` session (not auth_service.db which is closed)
    if login_data.guest_session_id and user_id:
        try:
            search_service = SearchHistoryService(db)
            converted_count = search_service.convert_guest_searches_to_user(
                guest_session_id=login_data.guest_session_id, user_id=user_id
            )
            logger.info(f"Converted {converted_count} guest searches for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to convert guest searches during login: {str(e)}")
            # Don't fail login if conversion fails

    response_payload = {"access_token": access_token, "token_type": "bearer", "requires_2fa": False}
    return LoginResponse(**model_filter(LoginResponse, response_payload))


@router.get("/me", response_model=AuthUserWithPermissionsResponse)
async def read_users_me(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> AuthUserWithPermissionsResponse:
    """
    Get current user information with roles and permissions.

    No additional rate limiting as this requires authentication.

    Args:
        current_user: Current user email from JWT
        auth_service: Authentication service
        db: Database session

    Returns:
        AuthUserWithPermissionsResponse: Current user data with roles and permissions

    Raises:
        HTTPException: If user not found
    """
    try:
        # Wrap all sync DB operations in thread pool to avoid blocking event loop
        def _fetch_user_data() -> tuple[Any, ...]:
            """Fetch user, permissions, roles, and beta info in one thread."""
            u = auth_service.get_current_user(email=current_user)
            perm_svc = PermissionService(db)
            perms = perm_svc.get_user_permissions(u.id)
            r = perm_svc.get_user_roles(u.id)
            from app.repositories.beta_repository import BetaAccessRepository

            beta_repo = BetaAccessRepository(db)
            b = beta_repo.get_latest_for_user(u.id)
            return u, perms, r, b

        user, permissions, roles, beta = await asyncio.to_thread(_fetch_user_data)

        # Create response with roles, permissions, and beta info (if any)
        response_data = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": getattr(user, "phone", None),
            "zip_code": getattr(user, "zip_code", None),
            "is_active": getattr(user, "is_active", True),
            "timezone": getattr(user, "timezone", None),
            "profile_picture_version": getattr(user, "profile_picture_version", 0),
            "has_profile_picture": getattr(user, "has_profile_picture", False),
            "roles": roles,
            "permissions": list(permissions),
        }

        if beta:
            response_data.update(
                {
                    "beta_access": True,
                    "beta_role": getattr(beta, "role", None),
                    "beta_phase": getattr(beta, "phase", None),
                    "beta_invited_by": getattr(beta, "invited_by_code", None),
                }
            )

        return AuthUserWithPermissionsResponse(
            **model_filter(AuthUserWithPermissionsResponse, response_data)
        )
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.patch("/me", response_model=AuthUserWithPermissionsResponse)
async def update_current_user(
    user_update: UserUpdate = Body(...),
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> AuthUserWithPermissionsResponse:
    """
    Update current user's profile (including timezone).

    Args:
        user_update: Fields to update
        current_user: Current user email from JWT
        auth_service: Authentication service
        db: Database session

    Returns:
        AuthUserWithPermissionsResponse: Updated user data

    Raises:
        HTTPException: If user not found or update fails
    """
    try:
        # Wrap all sync DB operations in thread pool to avoid blocking event loop
        def _update_user_profile() -> tuple[Any, ...]:
            """Perform all DB ops in one thread."""
            u = auth_service.get_current_user(email=current_user)

            # Use repository for updates
            from app.repositories import RepositoryFactory

            user_repo = RepositoryFactory.create_user_repository(db)

            # Prepare update data
            upd_data = {}
            if user_update.first_name is not None:
                upd_data["first_name"] = user_update.first_name
            if user_update.last_name is not None:
                upd_data["last_name"] = user_update.last_name
            if user_update.phone is not None:
                upd_data["phone"] = user_update.phone

            # Handle zip code change with automatic timezone update
            if user_update.zip_code is not None:
                old_zip = u.zip_code
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
                upd_data["timezone"] = user_update.timezone

            # Update using repository
            upd_user = user_repo.update_profile(u.id, **upd_data)

            if not upd_user:
                raise NotFoundException("Failed to update user")

            # Get permissions for the response
            perm_svc = PermissionService(db)
            perms = perm_svc.get_user_permissions(upd_user.id)
            r = perm_svc.get_user_roles(upd_user.id)
            return upd_user, perms, r

        updated_user, permissions, roles = await asyncio.to_thread(_update_user_profile)

        response_data = {
            "id": updated_user.id,
            "email": updated_user.email,
            "first_name": updated_user.first_name,
            "last_name": updated_user.last_name,
            "phone": getattr(updated_user, "phone", None),
            "zip_code": getattr(updated_user, "zip_code", None),
            "is_active": getattr(updated_user, "is_active", True),
            "timezone": getattr(updated_user, "timezone", None),
            "roles": roles,
            "permissions": list(permissions),
            "profile_picture_version": getattr(updated_user, "profile_picture_version", 0),
            "has_profile_picture": getattr(updated_user, "has_profile_picture", False),
        }

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
