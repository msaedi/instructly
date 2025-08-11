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
from ..services.auth_service import AuthService
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

        # Use Pydantic model for response
        return UserResponse(
            id=db_user.id,
            email=db_user.email,
            full_name=db_user.full_name,
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


@router.post("/login", response_model=Token)
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

    return Token(access_token=access_token, token_type="bearer")


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

        # Create response with roles and permissions
        return UserWithPermissionsResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            timezone=user.timezone,
            roles=roles,
            permissions=list(permissions),
        )
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

        # Update fields if provided
        if user_update.full_name is not None:
            user.full_name = user_update.full_name
        if user_update.timezone is not None:
            user.timezone = user_update.timezone

        # Save changes
        db.commit()
        db.refresh(user)

        # Get permissions for the response
        permission_service = PermissionService(db)
        permissions = permission_service.get_user_permissions(user.id)
        roles = permission_service.get_user_roles(user.id)

        return UserWithPermissionsResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            timezone=user.timezone,
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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile",
        )
