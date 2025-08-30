# backend/app/routes/auth.py
"""
Authentication routes for InstaInstru platform.

This module provides thin controller endpoints for authentication,
delegating all business logic to the AuthService.

UPDATED: Added rate limiting to protect against brute force attacks.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..api.dependencies.services import get_auth_service
from ..auth import create_access_token, get_current_user
from ..core.config import settings
from ..core.exceptions import ConflictException, NotFoundException
from ..database import get_db
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..schemas import Token, UserCreate, UserLogin, UserResponse, UserUpdate, UserWithPermissionsResponse
from ..schemas.security import LoginResponse, PasswordChangeRequest, PasswordChangeResponse
from ..services.auth_service import AuthService
from ..services.beta_service import BetaService
from ..services.permission_service import PermissionService
from ..services.search_history_service import SearchHistoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(
    f"{settings.rate_limit_register_per_hour}/hour",
    key_type=RateLimitKeyType.IP,
    error_message="Too many registration attempts. Please try again later.",
)
async def register(
    request: Request,  # Add this for rate limiting
    user: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
):
    """
    Register a new user.

    Rate limited to prevent spam registrations.

    Args:
        user: User creation data (including optional guest_session_id)
        auth_service: Authentication service
        db: Database session

    Returns:
        UserResponse: The created user

    Raises:
        HTTPException: If email already registered or rate limit exceeded
    """
    try:
        db_user = auth_service.register_user(
            email=user.email,
            password=user.password,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            zip_code=user.zip_code,
            role=user.role,
        )

        # Convert guest searches if guest_session_id provided
        if user.guest_session_id:
            try:
                search_service = SearchHistoryService(db)
                converted_count = await search_service.convert_guest_searches_to_user(
                    guest_session_id=user.guest_session_id, user_id=db_user.id
                )
                logger.info(f"Converted {converted_count} guest searches for new user {db_user.id}")
            except Exception as e:
                logger.error(f"Failed to convert guest searches during registration: {str(e)}")
                # Don't fail registration if conversion fails

        # Beta invite consumption (server-side guarantee)
        try:
            invite_code = None
            if isinstance(getattr(user, "metadata", None), dict):
                invite_code = user.metadata.get("invite_code")
            if invite_code:
                svc = BetaService(db)
                grant, reason = svc.consume_and_grant(
                    code=str(invite_code),
                    user_id=db_user.id,
                    role=user.role or "student",
                    phase="instructor_only",
                )
                if grant:
                    logger.info(f"Consumed beta invite for user {db_user.id} via register")
                else:
                    logger.warning(f"Invite not consumed on register for user {db_user.id}: {reason}")
        except Exception as e:
            # Log only; do not block registration if invite handling fails
            logger.error(f"Error consuming invite on register for {db_user.id}: {e}")

        # Use Pydantic model for response
        return UserResponse(
            id=db_user.id,
            email=db_user.email,
            first_name=db_user.first_name,
            last_name=db_user.last_name,
            phone=db_user.phone,
            zip_code=db_user.zip_code,
            is_active=db_user.is_active,
            timezone=db_user.timezone,
            roles=[role.name for role in db_user.roles],
            permissions=[],  # TODO: Add permissions if needed
        )
    except ConflictException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user",
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
):
    """
    Login with username (email) and password.

    Rate limited to prevent brute force attacks.

    Args:
        form_data: OAuth2 form with username and password
        auth_service: Authentication service

    Returns:
        Token: Access token and token type

    Raises:
        HTTPException: If credentials are invalid or rate limit exceeded
    """
    user = auth_service.authenticate_user(
        email=form_data.username,
        password=form_data.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If user has 2FA enabled and not trusted (no trust cookie), return requires_2fa
    if getattr(user, "totp_enabled", False):
        # Check trust cookie set by 2FA verification
        is_trusted = request.cookies.get("tfa_trusted") == "1"
        # Dev convenience: allow header-based trust when not in production (since cross-origin cookies may be restricted locally)
        if not is_trusted and settings.environment != "production":
            if request.headers.get("X-Trusted-Bypass", "false").lower() == "true":
                is_trusted = True
        if not is_trusted:
            temp_token = create_access_token(
                data={"sub": user.email, "tfa_pending": True}, expires_delta=timedelta(minutes=5)
            )
            return LoginResponse(requires_2fa=True, temp_token=temp_token)

    # Create access token (HTTP concern - stays in route)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
    )

    # Set cookie for SSE authentication
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # Prevent JavaScript access for security
        secure=settings.environment == "production",  # HTTPS only in production
        samesite="lax",  # CSRF protection
        max_age=settings.access_token_expire_minutes * 60,  # Convert to seconds
    )

    return LoginResponse(access_token=access_token, token_type="bearer", requires_2fa=False)


@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(
    request: PasswordChangeRequest,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
):
    """
    Change password for the current authenticated user.

    Verifies the current password, enforces minimal strength, and updates the hash.
    """
    # Get user object
    user = auth_service.get_current_user(email=current_user)

    # Verify current password
    from app.auth import get_password_hash, verify_password

    if not verify_password(request.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    # Basic strength checks
    new_pw = request.new_password
    if len(new_pw) < 8 or new_pw.lower() == new_pw or not any(c.isdigit() for c in new_pw):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password is too weak")

    hashed = get_password_hash(new_pw)

    from app.repositories import RepositoryFactory

    user_repository = RepositoryFactory.create_user_repository(db)
    success = user_repository.update_password(user.id, hashed)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update password")

    return PasswordChangeResponse(message="Password changed successfully")


@router.post("/login-with-session", response_model=Token)
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
):
    """
    Login with email and password, optionally converting guest searches.

    This endpoint supports guest session conversion.

    Args:
        login_data: Login credentials with optional guest_session_id
        auth_service: Authentication service
        db: Database session

    Returns:
        Token: Access token and token type

    Raises:
        HTTPException: If credentials are invalid or rate limit exceeded
    """
    user = auth_service.authenticate_user(
        email=login_data.email,
        password=login_data.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert guest searches if guest_session_id provided
    if login_data.guest_session_id:
        try:
            search_service = SearchHistoryService(db)
            converted_count = await search_service.convert_guest_searches_to_user(
                guest_session_id=login_data.guest_session_id, user_id=user.id
            )
            logger.info(f"Converted {converted_count} guest searches for user {user.id}")
        except Exception as e:
            logger.error(f"Failed to convert guest searches during login: {str(e)}")
            # Don't fail login if conversion fails

    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
    )

    # Set cookie for SSE authentication
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # Prevent JavaScript access for security
        secure=settings.environment == "production",  # HTTPS only in production
        samesite="lax",  # CSRF protection
        max_age=settings.access_token_expire_minutes * 60,  # Convert to seconds
    )

    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserWithPermissionsResponse)
async def read_users_me(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
):
    """
    Get current user information with roles and permissions.

    No additional rate limiting as this requires authentication.

    Args:
        current_user: Current user email from JWT
        auth_service: Authentication service
        db: Database session

    Returns:
        UserWithPermissionsResponse: Current user data with roles and permissions

    Raises:
        HTTPException: If user not found
    """
    try:
        user = auth_service.get_current_user(email=current_user)

        # Get permissions for the user
        permission_service = PermissionService(db)
        permissions = permission_service.get_user_permissions(user.id)
        roles = permission_service.get_user_roles(user.id)

        # Fetch beta access info
        from app.repositories.beta_repository import BetaAccessRepository

        beta_repo = BetaAccessRepository(db)
        beta = beta_repo.get_latest_for_user(user.id)

        # Create response with roles, permissions, and beta info (if any)
        resp = UserWithPermissionsResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            zip_code=user.zip_code,
            is_active=user.is_active,
            timezone=user.timezone,
            # Include profile picture metadata so clients can react to updates
            profile_picture_version=user.profile_picture_version or 0,
            has_profile_picture=user.has_profile_picture,
            roles=roles,
            permissions=list(permissions),
        )

        # Attach beta fields dynamically (Pydantic will ignore extras if not defined)
        if beta:
            setattr(resp, "beta_access", True)
            setattr(resp, "beta_role", beta.role)
            setattr(resp, "beta_phase", beta.phase)
            setattr(resp, "beta_invited_by", beta.invited_by_code)

        return resp
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.patch("/me", response_model=UserWithPermissionsResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
):
    """
    Update current user's profile (including timezone).

    Args:
        user_update: Fields to update
        current_user: Current user email from JWT
        auth_service: Authentication service
        db: Database session

    Returns:
        UserWithPermissionsResponse: Updated user data

    Raises:
        HTTPException: If user not found or update fails
    """
    try:
        user = auth_service.get_current_user(email=current_user)

        # Use repository for updates
        from app.repositories import RepositoryFactory

        user_repository = RepositoryFactory.create_user_repository(db)

        # Prepare update data
        update_data = {}
        if user_update.first_name is not None:
            update_data["first_name"] = user_update.first_name
        if user_update.last_name is not None:
            update_data["last_name"] = user_update.last_name
        if user_update.phone is not None:
            update_data["phone"] = user_update.phone

        # Handle zip code change with automatic timezone update
        if user_update.zip_code is not None:
            old_zip = user.zip_code
            update_data["zip_code"] = user_update.zip_code

            # Auto-update timezone when zip code changes
            if old_zip != user_update.zip_code:
                from app.core.timezone_service import get_timezone_from_zip

                new_timezone = get_timezone_from_zip(user_update.zip_code)
                logger.info(
                    f"Updating timezone from {user.timezone} to {new_timezone} for zip change {old_zip} -> {user_update.zip_code}"
                )
                update_data["timezone"] = new_timezone

        # Allow manual timezone override
        if user_update.timezone is not None:
            update_data["timezone"] = user_update.timezone

        # Update using repository
        updated_user = user_repository.update_profile(user.id, **update_data)

        if not updated_user:
            raise NotFoundException("Failed to update user")

        # Get permissions for the response
        permission_service = PermissionService(db)
        permissions = permission_service.get_user_permissions(updated_user.id)
        roles = permission_service.get_user_roles(updated_user.id)

        return UserWithPermissionsResponse(
            id=updated_user.id,
            email=updated_user.email,
            first_name=updated_user.first_name,
            last_name=updated_user.last_name,
            phone=updated_user.phone,
            zip_code=updated_user.zip_code,
            is_active=updated_user.is_active,
            timezone=updated_user.timezone,
            roles=roles,
            permissions=list(permissions),
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
