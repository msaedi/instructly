# backend/app/routes/v1/__init__.py
"""
API v1 Routes

Versioned API endpoints under /api/v1.
All new endpoints should be added here.
"""

from . import instructors

__all__ = ["instructors"]
