# backend/app/api/dependencies/auth.py
"""
Authentication and authorization dependencies.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...auth import get_current_user as auth_get_current_user
from ...models.user import User
from .database import get_db


async def get_current_user(
    current_user_email: str = Depends(auth_get_current_user),
    db: Session = Depends(get_db)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def get_current_instructor(
    current_user: User = Depends(get_current_active_user)
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an instructor"
        )
    return current_user


async def get_current_student(
    current_user: User = Depends(get_current_active_user)
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a student"
        )
    return current_user