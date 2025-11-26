# backend/app/routes/v1/__init__.py
"""
API v1 Routes

Versioned API endpoints under /api/v1.
All new endpoints should be added here.
"""

from . import (
    account,
    addresses,
    auth,
    bookings,
    favorites,
    instructor_bookings,
    instructors,
    messages,
    password_reset,
    payments,
    referrals,
    reviews,
    search,
    search_history,
    services,
    two_factor_auth,
)

__all__ = [
    "account",
    "addresses",
    "auth",
    "bookings",
    "favorites",
    "instructor_bookings",
    "instructors",
    "messages",
    "password_reset",
    "payments",
    "referrals",
    "reviews",
    "search",
    "search_history",
    "services",
    "two_factor_auth",
]
