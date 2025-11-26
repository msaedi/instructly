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
    config,
    favorites,
    instructor_bookings,
    instructors,
    messages,
    password_reset,
    payments,
    pricing,
    privacy,
    public,
    referrals,
    reviews,
    search,
    search_history,
    services,
    student_badges,
    two_factor_auth,
    uploads,
    users,
)

__all__ = [
    "account",
    "addresses",
    "auth",
    "bookings",
    "config",
    "favorites",
    "instructor_bookings",
    "instructors",
    "messages",
    "password_reset",
    "payments",
    "pricing",
    "privacy",
    "public",
    "referrals",
    "reviews",
    "search",
    "search_history",
    "services",
    "student_badges",
    "two_factor_auth",
    "uploads",
    "users",
]
