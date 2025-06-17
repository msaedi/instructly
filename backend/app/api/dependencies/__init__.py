# backend/app/api/dependencies/__init__.py
"""
Central export point for all dependencies.

This module re-exports all dependencies from submodules
for convenient access throughout the application.
"""

from .auth import get_current_user, get_current_active_user
from .database import get_db, get_async_db
from .services import (
    get_notification_service,
    get_booking_service,
    # Future services will be added here
    # get_availability_service,
    # get_instructor_service,
)

__all__ = [
    # Auth
    "get_current_user",
    "get_current_active_user",
    # Database
    "get_db",
    "get_async_db",
    # Services
    "get_notification_service",
    "get_booking_service",
]