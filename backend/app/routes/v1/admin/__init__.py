# backend/app/routes/v1/admin/__init__.py
"""
API v1 Admin Routes

Administrative endpoints under /api/v1/admin.
"""

from . import (
    audit,
    auth_blocks,
    background_checks,
    badges,
    bookings,
    config,
    instructors,
    location_learning,
    refunds,
    search_config,
    users,
)

__all__ = [
    "audit",
    "auth_blocks",
    "background_checks",
    "badges",
    "bookings",
    "config",
    "instructors",
    "location_learning",
    "refunds",
    "search_config",
    "users",
]
