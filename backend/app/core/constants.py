"""Application-wide constants for InstaInstru platform."""

from __future__ import annotations

import os

# Service duration constraints (still needed for service-level overrides)
MIN_SESSION_DURATION = 30  # minutes
MAX_SESSION_DURATION = 240  # minutes (4 hours)

# SSE (Server-Sent Events) configuration
SSE_PATH_PREFIX = "/api/messages/stream"  # Centralized SSE path for middleware

# The following constants are DEPRECATED and will be removed
# They were part of the old booking system
# DEFAULT_SESSION_DURATION = 60  # DEPRECATED - moved to service level
# MIN_BUFFER_TIME = 0  # DEPRECATED - will be in booking v2
# MAX_BUFFER_TIME = 120  # DEPRECATED - will be in booking v2
# DEFAULT_BUFFER_TIME = 0  # DEPRECATED - will be in booking v2
# MIN_ADVANCE_BOOKING = 0  # DEPRECATED - will be in booking v2
# MAX_ADVANCE_BOOKING = 168  # DEPRECATED - will be in booking v2
# DEFAULT_ADVANCE_BOOKING = 2  # DEPRECATED - will be in booking v2

# Text constraints
MIN_BIO_LENGTH = 10
MAX_BIO_LENGTH = 1000
MAX_REASON_LENGTH = 255

# Query limits
DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 1000

# Availability constraints
MAX_FUTURE_DAYS = 365  # Maximum days in the future for availability (1 year)
MAX_SLOTS_PER_DAY = 10  # Maximum time slots per day

# Day of week mapping
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Frontend URLs
DEFAULT_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3100",
    "http://beta-local.instainstru.com:3000",
    "http://beta-local.instainstru.com:3100",
]


def _split_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [origin.strip() for origin in value.split(",") if origin.strip()]


ALLOWED_ORIGINS = (
    _split_env("ALLOWED_ORIGINS")
    or _split_env("CORS_ALLOW_ORIGINS")
    or _split_env("CORS_ALLOWED_ORIGINS")
    or DEFAULT_DEV_ORIGINS
)

# CORS regex pattern for Vercel preview deployments
CORS_ORIGIN_REGEX = (
    r"(^https://[a-zA-Z0-9-]+\.vercel\.app$)"
    r"|(^https?://(localhost|127\.0\.0\.1|beta-local\.instainstru\.com)(:\d+)?$)"
)

# Error messages
ERROR_INSTRUCTOR_ONLY = "Only instructors can perform this action"
ERROR_INSTRUCTOR_NOT_FOUND = "Instructor profile not found"
ERROR_USER_NOT_FOUND = "User not found"
ERROR_INVALID_TIME_RANGE = "End time must be after start time"
ERROR_OVERLAPPING_SLOT = "Time slot overlaps with existing slot"
ERROR_PAST_DATE = "Cannot create availability for past dates"
ERROR_TOO_FAR_FUTURE = f"Cannot create availability more than {MAX_FUTURE_DAYS} days in the future"
ERROR_TOO_MANY_SLOTS = f"Cannot create more than {MAX_SLOTS_PER_DAY} time slots per day"

# Success messages
SUCCESS_AVAILABILITY_SAVED = "Availability saved successfully"
SUCCESS_AVAILABILITY_DELETED = "Availability deleted successfully"
SUCCESS_PROFILE_UPDATED = "Profile updated successfully"

# Brand Configuration
BRAND_NAME = "iNSTAiNSTRU"
BRAND_TAGLINE = "Book Expert Instructors Instantly"
BRAND_DOMAIN = "instainstru.com"
SUPPORT_EMAIL = "support@instainstru.com"
MONITORING_EMAIL = "InstaInstru Alerts <alerts@instainstru.com>"
NOREPLY_EMAIL = "InstaInstru <hello@instainstru.com>"  # Keep for backward compatibility

# API Documentation
API_TITLE = f"{BRAND_NAME} API"
API_DESCRIPTION = f"Backend API for {BRAND_NAME} - A platform connecting students with instructors"
API_VERSION = "1.0.0"

# Rate limiting (for future implementation)
MAX_REQUESTS_PER_MINUTE = 60
MAX_REQUESTS_PER_HOUR = 1000
