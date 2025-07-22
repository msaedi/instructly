# backend/app/api/dependencies/__init__.py
"""
Central export point for all dependencies.

This module re-exports all dependencies from submodules
for convenient access throughout the application.
"""

from .auth import get_current_active_user, get_current_user
from .database import get_async_db, get_db
from .services import (  # Future services will be added here; get_availability_service,; get_instructor_service,
    get_account_lifecycle_service,
    get_booking_service,
    get_notification_service,
)

__all__ = [
    # Auth
    "get_current_user",
    "get_current_active_user",
    # Database
    "get_db",
    "get_async_db",
    # Services
    "get_account_lifecycle_service",
    "get_notification_service",
    "get_booking_service",
]
