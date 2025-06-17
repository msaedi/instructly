# backend/app/api/dependencies/services.py
"""
Service layer dependencies for dependency injection.

This module provides factory functions that create service instances
with their required dependencies properly injected.
"""

from typing import Generator
from fastapi import Depends
from sqlalchemy.orm import Session

from .database import get_db
from ...services.booking_service import BookingService
from ...services.notification_service import NotificationService
# Future imports
# from ...services.availability_service import AvailabilityService
# from ...services.instructor_service import InstructorService
# from ...services.auth_service import AuthService


def get_notification_service(
    db: Session = Depends(get_db)
) -> NotificationService:
    """
    Get notification service instance.
    
    Args:
        db: Database session
        
    Returns:
        NotificationService instance
    """
    return NotificationService(db)


def get_booking_service(
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service)
) -> BookingService:
    """
    Get booking service instance with all dependencies.
    
    Args:
        db: Database session
        notification_service: Notification service for sending emails
        
    Returns:
        BookingService instance
    """