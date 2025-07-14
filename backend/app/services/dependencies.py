# backend/app/services/dependencies.py
"""
Dependency injection functions for services.

Add these to your existing dependencies file or create this new file
to provide proper dependency injection for TemplateService and NotificationService.
"""

from typing import Optional

from fastapi import Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .booking_service import BookingService
from .cache_service import CacheService, get_cache_service
from .notification_service import NotificationService
from .template_service import TemplateService


def get_template_service(
    db: Session = Depends(get_db), cache: Optional[CacheService] = Depends(get_cache_service)
) -> TemplateService:
    """
    Dependency injection function for TemplateService.

    Usage in routes:
        template_service: TemplateService = Depends(get_template_service)
    """
    return TemplateService(db, cache)


def get_notification_service(
    db: Session = Depends(get_db),
    cache: Optional[CacheService] = Depends(get_cache_service),
    template_service: TemplateService = Depends(get_template_service),
) -> NotificationService:
    """
    Dependency injection function for NotificationService.

    Note: This properly injects TemplateService as a dependency.

    Usage in routes:
        notification_service: NotificationService = Depends(get_notification_service)
    """
    return NotificationService(db, cache, template_service)


def get_booking_service(
    db: Session = Depends(get_db),
    cache: Optional[CacheService] = Depends(get_cache_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> BookingService:
    """
    Dependency injection function for BookingService with cache support.

    Usage in routes:
        booking_service: BookingService = Depends(get_booking_service)
    """
    return BookingService(
        db=db,
        notification_service=notification_service,
        cache_service=cache,
    )


# Example of how to use in a route:
"""
from fastapi import APIRouter, Depends
from app.services.dependencies import get_notification_service
from app.services.notification_service import NotificationService

router = APIRouter()

@router.post("/send-test-email")
async def send_test_email(
    notification_service: NotificationService = Depends(get_notification_service)
):
    # Use the injected service
    result = await notification_service.send_booking_confirmation(booking)
    return {"success": result}
"""

# Example of how to use in another service:
"""
class BookingService(BaseService):
    def __init__(
        self,
        db: Session,
        notification_service: Optional[NotificationService] = None,
        template_service: Optional[TemplateService] = None
    ):
        super().__init__(db)
        # Create instances if not provided
        if template_service is None:
            template_service = TemplateService(db)
        self.template_service = template_service

        if notification_service is None:
            notification_service = NotificationService(db, None, template_service)
        self.notification_service = notification_service
"""
