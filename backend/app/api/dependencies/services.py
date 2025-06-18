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
from ...services.availability_service import AvailabilityService
from ...services.conflict_checker import ConflictChecker
from ...services.slot_manager import SlotManager
from ...services.week_operation_service import WeekOperationService
from ...services.bulk_operation_service import BulkOperationService
from ...services.presentation_service import PresentationService


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
    return BookingService(db, notification_service)


def get_availability_service(
    db: Session = Depends(get_db)
) -> AvailabilityService:
    """
    Get availability service instance.
    
    Args:
        db: Database session
        
    Returns:
        AvailabilityService instance
    """
    return AvailabilityService(db)


def get_conflict_checker(
    db: Session = Depends(get_db)
) -> ConflictChecker:
    """
    Get conflict checker service instance.
    
    Args:
        db: Database session
        
    Returns:
        ConflictChecker instance
    """
    return ConflictChecker(db)


def get_slot_manager(
    db: Session = Depends(get_db),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker)
) -> SlotManager:
    """
    Get slot manager service instance.
    
    Args:
        db: Database session
        conflict_checker: Conflict checker service
        
    Returns:
        SlotManager instance
    """
    return SlotManager(db, conflict_checker)


def get_week_operation_service(
    db: Session = Depends(get_db),
    availability_service: AvailabilityService = Depends(get_availability_service),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker)
) -> WeekOperationService:
    """
    Get week operation service instance.
    
    Args:
        db: Database session
        availability_service: Availability service
        conflict_checker: Conflict checker service
        
    Returns:
        WeekOperationService instance
    """
    return WeekOperationService(db, availability_service, conflict_checker)


def get_bulk_operation_service(
    db: Session = Depends(get_db),
    slot_manager: SlotManager = Depends(get_slot_manager),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker)
) -> BulkOperationService:
    """
    Get bulk operation service instance.
    
    Args:
        db: Database session
        slot_manager: Slot manager service
        conflict_checker: Conflict checker service
        
    Returns:
        BulkOperationService instance
    """
    return BulkOperationService(db, slot_manager, conflict_checker)


def get_presentation_service(
    db: Session = Depends(get_db)
) -> PresentationService:
    """
    Get presentation service instance.
    
    Args:
        db: Database session
        
    Returns:
        PresentationService instance
    """
    return PresentationService(db)