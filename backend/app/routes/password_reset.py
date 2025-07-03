# backend/app/routes/password_reset.py
"""
Password reset routes for InstaInstru platform.

This module provides thin controller endpoints for password reset,
delegating all business logic to the PasswordResetService.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..api.dependencies.services import get_password_reset_service
from ..core.exceptions import ValidationException
from ..schemas.password_reset import PasswordResetConfirm, PasswordResetRequest, PasswordResetResponse
from ..services.password_reset_service import PasswordResetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/password-reset", tags=["password-reset"])


@router.post("/request", response_model=PasswordResetResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
):
    """
    Request a password reset email.

    This endpoint always returns success to prevent email enumeration attacks.
    If the email exists, a reset link will be sent.

    Args:
        request: Email address for password reset
        password_reset_service: Password reset service

    Returns:
        PasswordResetResponse: Success message
    """
    await password_reset_service.request_password_reset(email=request.email)

    # Always return success to prevent email enumeration
    return PasswordResetResponse(
        message="If an account exists with this email, you will receive a password reset link shortly."
    )


@router.post("/confirm", response_model=PasswordResetResponse)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
):
    """
    Confirm password reset with token and new password.

    Args:
        request: Token and new password
        password_reset_service: Password reset service

    Returns:
        PasswordResetResponse: Success message

    Raises:
        HTTPException: If token is invalid, expired, or already used
    """
    try:
        await password_reset_service.confirm_password_reset(
            token=request.token,
            new_password=request.new_password,
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


@router.get("/verify/{token}")
async def verify_reset_token(
    token: str,
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
):
    """
    Verify if a reset token is valid.

    This endpoint can be used by the frontend to check if a token
    is valid before showing the password reset form.

    Args:
        token: The reset token to verify
        password_reset_service: Password reset service

    Returns:
        dict: Validity status and user email (masked)
    """
    is_valid, masked_email = password_reset_service.verify_reset_token(token=token)

    if is_valid:
        return {"valid": True, "email": masked_email}
    else:
        return {"valid": False}
