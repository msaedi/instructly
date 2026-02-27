"""Shared schema types for consistent API contracts."""

from typing import Literal

# Canonical location types for bookings
LocationTypeLiteral = Literal[
    "student_location",
    "instructor_location",
    "online",
    "neutral_location",
]

# Service location types
ServiceLocationTypeLiteral = Literal["in_person", "online"]
