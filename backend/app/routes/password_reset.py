# backend/app/routes/password_reset.py
"""
Password reset routes for InstaInstru platform.

This module provides thin controller endpoints for password reset,
delegating all business logic to the PasswordResetService.

UPDATED: Added aggressive rate limiting to prevent email enumeration
and brute force attacks.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..api.dependencies.services import get_password_reset_service
from ..core.config import settings
from ..core.exceptions import ValidationException
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..schemas.password_reset import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetVerifyResponse,
    PasswordResetVerifyResponseInvalid,
    PasswordResetVerifyResponseValid,
)
from ..services.password_reset_service import PasswordResetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/password-reset", tags=["password-reset"])


@router.post("/request", response_model=PasswordResetResponse)
@rate_limit(
    f"{settings.rate_limit_password_reset_ip_per_hour}/hour",
    key_type=RateLimitKeyType.IP,
    error_message="Too many password reset attempts. Please try again later.",
)
@rate_limit(
    f"{settings.rate_limit_password_reset_per_hour}/hour",
    key_type=RateLimitKeyType.EMAIL,
    key_field="email",
    error_message="Too many password reset attempts for this email. Please try again later.",
)
async def request_password_reset(
    request: Request,  # Add this for rate limiting
    reset_request: PasswordResetRequest,  # Renamed to avoid confusion
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
):
    """
    Request a password reset email.

    This endpoint always returns success to prevent email enumeration attacks.
    If the email exists, a reset link will be sent.

    Rate limited by both IP and email to prevent abuse.

    Args:
        request: Email address for password reset
        password_reset_service: Password reset service

    Returns:
        PasswordResetResponse: Success message

    Raises:
        HTTPException: If rate limit exceeded
    """
    password_reset_service.request_password_reset(email=reset_request.email)

    # Always return success to prevent email enumeration
    return PasswordResetResponse(
        message="If an account exists with this email, you will receive a password reset link shortly."
    )


@router.post("/confirm", response_model=PasswordResetResponse)
@rate_limit(
    "10/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many password reset confirmation attempts. Please try again later.",
)
async def confirm_password_reset(
    request: Request,  # Add this for rate limiting
    confirm_request: PasswordResetConfirm,  # Renamed to avoid confusion
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
):
    """
    Confirm password reset with token and new password.

    Rate limited to prevent token brute forcing.

    Args:
        request: Token and new password
        password_reset_service: Password reset service

    Returns:
        PasswordResetResponse: Success message

    Raises:
        HTTPException: If token is invalid, expired, already used, or rate limit exceeded
    """
    try:
        password_reset_service.confirm_password_reset(
            token=confirm_request.token,
            new_password=confirm_request.new_password,
        )

        return PasswordResetResponse(
            message="Your password has been successfully reset. You can now log in with your new password."
        )

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during password reset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting your password",
        )


@router.get("/verify/{token}", response_model=PasswordResetVerifyResponse)
@rate_limit(
    "20/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many verification attempts. Please try again later.",
)
async def verify_reset_token(
    request: Request,  # Add this for rate limiting
    token: str,
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
):
    """
    Verify if a reset token is valid.

    This endpoint can be used by the frontend to check if a token
    is valid before showing the password reset form.

    Rate limited to prevent token enumeration.

    Args:
        token: The reset token to verify
        password_reset_service: Password reset service

    Returns:
        dict: Validity status and user email (masked)

    Raises:
        HTTPException: If rate limit exceeded
    """
    is_valid, masked_email = password_reset_service.verify_reset_token(token=token)

    if is_valid:
        return PasswordResetVerifyResponseValid(email=masked_email)
    else:
        return PasswordResetVerifyResponseInvalid()
