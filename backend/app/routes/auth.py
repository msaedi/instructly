# backend/app/routes/auth.py
"""
Authentication routes for InstaInstru platform.

This module provides thin controller endpoints for authentication,
delegating all business logic to the AuthService.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..api.dependencies.services import get_auth_service
from ..auth import create_access_token, get_current_user
from ..core.config import settings
from ..core.exceptions import ConflictException, NotFoundException
from ..schemas import Token, UserCreate, UserResponse
from ..services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Register a new user.

    Args:
        user: User creation data
        auth_service: Authentication service

    Returns:
        UserResponse: The created user

    Raises:
        HTTPException: If email already registered
    """
    try:
        db_user = auth_service.register_user(
            email=user.email,
            password=user.password,
            full_name=user.full_name,
            role=user.role,
        )
        return db_user
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
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Login with username (email) and password.

    Args:
        form_data: OAuth2 form with username and password
        auth_service: Authentication service

    Returns:
        Token: Access token and token type

    Raises:
        HTTPException: If credentials are invalid
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

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Get current user information.

    Args:
        current_user: Current user email from JWT
        auth_service: Authentication service

    Returns:
        UserResponse: Current user data

    Raises:
        HTTPException: If user not found
    """
    try:
        user = auth_service.get_current_user(email=current_user)
        return user
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
