# backend/app/api/dependencies/auth.py
"""
Authentication and authorization dependencies.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...auth import get_current_user as auth_get_current_user
from ...auth import get_current_user_optional as auth_get_current_user_optional
from ...core.config import settings
from ...models.user import User
from ...repositories.beta_repository import BetaAccessRepository, BetaSettingsRepository
from .database import get_db


async def get_current_user(
    current_user_email: str = Depends(auth_get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from the database.

    Args:
        current_user_email: Email from JWT token
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If user not found
    """
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current authenticated and active user.

    Args:
        current_user: Current authenticated user

    Returns:
        User object if active

    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def get_current_instructor(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get the current authenticated instructor.

    Args:
        current_user: Current active user

    Returns:
        User object if instructor

    Raises:
        HTTPException: If user is not an instructor
    """
    if not current_user.is_instructor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an instructor")
    return current_user


async def get_current_student(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get the current authenticated student.

    Args:
        current_user: Current active user

    Returns:
        User object if student

    Raises:
        HTTPException: If user is not a student
    """
    if not current_user.is_student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a student")
    return current_user


async def get_current_active_user_optional(
    current_user_email: Optional[str] = Depends(auth_get_current_user_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get the current authenticated user if present, otherwise return None.

    This is useful for endpoints that work for both authenticated and anonymous users,
    but provide enhanced functionality for authenticated users.

    Args:
        current_user_email: Email from JWT token (if present)
        db: Database session

    Returns:
        User object if authenticated and found, None otherwise
    """
    if not current_user_email:
        return None

    user = db.query(User).filter(User.email == current_user_email).first()
    if user and user.is_active:
        return user

    return None


def require_beta_access(role: Optional[str] = None):
    async def verify_beta(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Testing and global bypasses
        if getattr(settings, "is_testing", False) and request.headers.get("x-enforce-beta-checks") != "1":
            return current_user
        if getattr(settings, "beta_disabled", False):
            return current_user
        repo = BetaAccessRepository(db)
        beta = repo.get_latest_for_user(current_user.id)
        if not beta:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Beta access required")
        if role and beta.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Beta {role} access required")
        return current_user

    return verify_beta


def require_beta_phase_access(expected_phase: Optional[str] = None):
    async def verify_phase(
        request: Request,
        db: Session = Depends(get_db),
    ) -> None:
        # Testing and global bypasses
        if getattr(settings, "is_testing", False) and request.headers.get("x-enforce-beta-checks") != "1":
            return None
        if getattr(settings, "beta_disabled", False):
            return None
        settings_repo = BetaSettingsRepository(db)
        s = settings_repo.get_singleton()
        if bool(s.beta_disabled):
            return None
        if expected_phase and str(s.beta_phase) != expected_phase:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Beta phase '{expected_phase}' required")
        return None

    return verify_phase
