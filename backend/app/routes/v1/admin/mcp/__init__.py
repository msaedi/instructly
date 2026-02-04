"""MCP admin routes package."""

from . import (
    analytics,
    booking_actions,
    booking_detail,
    instructor_actions,
    refunds,
    student_actions,
)

__all__ = [
    "booking_actions",
    "booking_detail",
    "analytics",
    "instructor_actions",
    "refunds",
    "student_actions",
]
