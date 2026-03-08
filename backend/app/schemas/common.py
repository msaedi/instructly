"""Shared schema types for consistent API contracts."""

from typing import Literal

# Canonical location types for bookings
LocationTypeLiteral = Literal[
    "student_location",
    "instructor_location",
    "online",
    "neutral_location",
]

# Persisted service pricing formats
ServicePricingFormatLiteral = Literal[
    "student_location",
    "instructor_location",
    "online",
]

# Service location types
ServiceLocationTypeLiteral = Literal["in_person", "online"]
