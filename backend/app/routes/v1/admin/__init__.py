# backend/app/routes/v1/admin/__init__.py
"""
API v1 Admin Routes

Administrative endpoints under /api/v1/admin.
"""

from . import (
    audit,
    background_checks,
    badges,
    config,
    instructors,
)

__all__ = [
    "audit",
    "background_checks",
    "badges",
    "config",
    "instructors",
]
