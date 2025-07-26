"""
Application-wide constants for InstaInstru platform.

This module contains all constant values used throughout the application,
organized by category for easy maintenance and updates.
"""

# Service duration constraints (still needed for service-level overrides)
MIN_SESSION_DURATION = 30  # minutes
MAX_SESSION_DURATION = 240  # minutes (4 hours)

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
ALLOWED_ORIGINS = [
    # Local development
    "http://localhost:3000",
    "https://localhost:3000",  # HTTPS on standard port
    "https://localhost:3001",  # HTTPS on alternate port
    "http://localhost:8000",  # Backend HTTP
    "https://localhost:8001",  # Backend HTTPS
    # Current production URLs
    "https://instructly-ten.vercel.app",  # Current frontend (Vercel)
    "https://instructly-0949.onrender.com",  # Current backend (Render)
    "https://api.instainstru.com",  # New production backend URL
    # Future production URLs (keep for later migration)
    "https://instainstru.com",  # Future production URL
    "https://www.instainstru.com",  # Future production URL with www
    # Vercel preview deployments
    "https://*.vercel.app",  # All Vercel preview deployments
]

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
NOREPLY_EMAIL = "noreply@auth.instainstru.com"

# API Documentation
API_TITLE = f"{BRAND_NAME} API"
API_DESCRIPTION = f"Backend API for {BRAND_NAME} - A platform connecting students with instructors"
API_VERSION = "1.0.0"

# Rate limiting (for future implementation)
MAX_REQUESTS_PER_MINUTE = 60
MAX_REQUESTS_PER_HOUR = 1000
