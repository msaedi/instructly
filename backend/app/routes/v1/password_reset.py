# backend/app/routes/v1/password_reset.py
"""
Password reset request and confirmation endpoints.

Anti-enumeration is intentionally OFF on the request endpoint per
A-Team product decision for the invite-only beta; unknown emails
return 404 rather than the standard "if an account exists..." pattern.
Rate limiting at the IP and email level is the primary mitigation.

REVISIT AT PUBLIC LAUNCH: when iNSTAiNSTRU opens beyond invite-only,
the enumeration tradeoff should be re-evaluated alongside login and
registration anti-enumeration in auth.py.
"""

import asyncio
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from ...api.dependencies.services import get_password_reset_service
from ...core.config import settings
from ...core.exceptions import NotFoundException, ServiceException, ValidationException
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...schemas.password_reset import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetVerifyResponse,
)
from ...services.password_reset_service import PasswordResetService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["password-reset"])


@router.post(
    "/request",
    response_model=PasswordResetResponse,
    responses={
        404: {
            "description": "Account not found for the provided email",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["detail"],
                        "properties": {"detail": {"type": "string"}},
                    },
                    "example": {
                        "detail": "We couldn't find an account with that email. Please double-check and try again."
                    },
                }
            },
        },
        503: {
            "description": "Reset email could not be sent",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["detail"],
                        "properties": {"detail": {"type": "string"}},
                    },
                    "example": {
                        "detail": "Couldn't send reset email. Please try again or contact support."
                    },
                }
            },
        },
    },
)
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
    request: Request,  # Required by the rate_limit dependency
    payload: PasswordResetRequest = Body(...),
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
) -> PasswordResetResponse:
    """
    Request a password reset link.

    Returns 404 if no account matches the email; sends the reset link otherwise.
    Returns 503 if the reset email could not be sent for a valid account.

    Rate limited by both IP and email to prevent abuse.

    Args:
        payload: Email address for password reset
        password_reset_service: Password reset service

    Returns:
        PasswordResetResponse: Success message

    Raises:
        HTTPException: If rate limit exceeded
    """
    try:
        await asyncio.to_thread(password_reset_service.request_password_reset, email=payload.email)
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="We couldn't find an account with that email. Please double-check and try again.",
        )
    except ServiceException as e:
        if e.code == "PASSWORD_RESET_EMAIL_FAILED":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Couldn't send reset email. Please try again or contact support.",
            )
        logger.exception(
            "Unhandled ServiceException code in password reset request",
            extra={"code": e.code},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while requesting your password reset.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during password reset request: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while requesting your password reset.",
        )

    return PasswordResetResponse(message="Check your email for the reset link.")


@router.post("/confirm", response_model=PasswordResetResponse)
@rate_limit(
    "10/minute",
    key_type=RateLimitKeyType.IP,
    error_message="Too many password reset confirmation attempts. Please try again later.",
)
async def confirm_password_reset(
    request: Request,  # Required by the rate_limit dependency
    payload: PasswordResetConfirm = Body(...),
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
) -> PasswordResetResponse:
    """
    Confirm password reset with token and new password.

    Rate limited to prevent token brute forcing.

    Args:
        payload: Token and new password
        password_reset_service: Password reset service

    Returns:
        PasswordResetResponse: Success message

    Raises:
        HTTPException: If token is invalid, expired, already used, or rate limit exceeded
    """
    try:
        await asyncio.to_thread(
            password_reset_service.confirm_password_reset,
            token=payload.token,
            new_password=payload.new_password,
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
        logger.error("Unexpected error during password reset: %s", str(e))
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
    request: Request,  # Required by the rate_limit dependency
    token: str,
    password_reset_service: PasswordResetService = Depends(get_password_reset_service),
) -> PasswordResetVerifyResponse:
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
    is_valid, masked_email = await asyncio.to_thread(
        password_reset_service.verify_reset_token, token=token
    )

    return PasswordResetVerifyResponse(
        valid=is_valid,
        email=masked_email if is_valid else None,
    )
