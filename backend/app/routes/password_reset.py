# backend/app/routes/password_reset.py

import logging
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.password_reset import PasswordResetToken as PasswordResetTokenModel
from ..schemas.password_reset import (
    PasswordResetRequest,
    PasswordResetConfirm,
    PasswordResetResponse
)
from ..auth import get_password_hash
from ..services.email import email_service
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth/password-reset",
    tags=["password-reset"]
)

def generate_reset_token() -> str:
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)

@router.post("/request", response_model=PasswordResetResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset email.
    
    This endpoint always returns success to prevent email enumeration attacks.
    If the email exists, a reset link will be sent.
    
    Args:
        request: Email address for password reset
        db: Database session
        
    Returns:
        PasswordResetResponse: Success message
    """
    logger.info(f"Password reset requested for email: {request.email}")
    
    # Find user by email
    user = db.query(User).filter(User.email == request.email).first()
    
    if user:
        # Invalidate any existing tokens for this user
        db.query(PasswordResetTokenModel).filter(
            PasswordResetTokenModel.user_id == user.id,
            PasswordResetTokenModel.used == False
        ).update({"used": True})
        
        # Generate new token
        token = generate_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)  # Token expires in 1 hour
        
        # Save token to database
        reset_token = PasswordResetTokenModel(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        db.add(reset_token)
        
        try:
            db.commit()
            
            # Create reset URL
            reset_url = f"{settings.frontend_url}/reset-password?token={token}"
            
            # Send email asynchronously
            await email_service.send_password_reset_email(
                to_email=user.email,
                reset_url=reset_url,
                user_name=user.full_name
            )
            
            logger.info(f"Password reset token created for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error creating password reset token: {str(e)}")
            db.rollback()
    else:
        # Log that email doesn't exist but don't reveal this to the user
        logger.warning(f"Password reset requested for non-existent email: {request.email}")
    
    # Always return success to prevent email enumeration
    return PasswordResetResponse(
        message="If an account exists with this email, you will receive a password reset link shortly."
    )

@router.post("/confirm", response_model=PasswordResetResponse)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """
    Confirm password reset with token and new password.
    
    Args:
        request: Token and new password
        db: Database session
        
    Returns:
        PasswordResetResponse: Success message
        
    Raises:
        HTTPException: If token is invalid, expired, or already used
    """
    logger.info(f"Password reset confirmation attempted with token: {request.token[:8]}...")
    
    # Find the token
    reset_token = db.query(PasswordResetTokenModel).filter(
        PasswordResetTokenModel.token == request.token
    ).first()
    
    if not reset_token:
        logger.warning(f"Invalid password reset token: {request.token[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if token is already used
    if reset_token.used:
        logger.warning(f"Attempted to reuse password reset token: {request.token[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used"
        )
    
    # Check if token is expired
    if datetime.now(timezone.utc) > reset_token.expires_at:
        logger.warning(f"Expired password reset token used: {request.token[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired"
        )
    
    # Get the user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        logger.error(f"User not found for reset token: {reset_token.user_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    
    # Mark token as used
    reset_token.used = True
    
    try:
        db.commit()
        
        # Send confirmation email
        await email_service.send_password_reset_confirmation(
            to_email=user.email,
            user_name=user.full_name
        )
        
        logger.info(f"Password successfully reset for user {user.id}")
        
        return PasswordResetResponse(
            message="Your password has been successfully reset. You can now log in with your new password."
        )
        
    except Exception as e:
        logger.error(f"Error resetting password: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting your password"
        )

@router.get("/verify/{token}")
async def verify_reset_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Verify if a reset token is valid.
    
    This endpoint can be used by the frontend to check if a token
    is valid before showing the password reset form.
    
    Args:
        token: The reset token to verify
        db: Database session
        
    Returns:
        dict: Validity status and user email (masked)
    """
    reset_token = db.query(PasswordResetTokenModel).filter(
        PasswordResetTokenModel.token == token
    ).first()
    
    if not reset_token or reset_token.used or datetime.now(timezone.utc) > reset_token.expires_at:
        return {"valid": False}
    
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        return {"valid": False}
    
    # Mask email for privacy
    email_parts = user.email.split('@')
    if len(email_parts[0]) > 2:
        masked_email = email_parts[0][:2] + '***' + '@' + email_parts[1]
    else:
        masked_email = '***@' + email_parts[1]
    
    return {
        "valid": True,
        "email": masked_email
    }