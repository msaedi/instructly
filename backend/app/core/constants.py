"""Application-wide constants"""

# Time constraints
MIN_SESSION_DURATION = 30  # minutes
MAX_SESSION_DURATION = 240  # minutes
DEFAULT_SESSION_DURATION = 60  # minutes

MIN_BUFFER_TIME = 0  # minutes
MAX_BUFFER_TIME = 120  # minutes
DEFAULT_BUFFER_TIME = 0  # minutes

MIN_ADVANCE_BOOKING = 0  # hours
MAX_ADVANCE_BOOKING = 168  # hours (1 week)
DEFAULT_ADVANCE_BOOKING = 2  # hours

# Text constraints
MIN_BIO_LENGTH = 10
MAX_BIO_LENGTH = 1000
MAX_REASON_LENGTH = 255

# Query limits
DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 1000

# Day of week mapping
DAYS_OF_WEEK = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

# Frontend URLs
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://instructly-ten.vercel.app",
    "https://*.vercel.app",
]

# Error messages
ERROR_INSTRUCTOR_ONLY = "Only instructors can perform this action"
ERROR_INSTRUCTOR_NOT_FOUND = "Instructor profile not found"
ERROR_USER_NOT_FOUND = "User not found"
ERROR_INVALID_TIME_RANGE = "End time must be after start time"
ERROR_OVERLAPPING_SLOT = "Time slot overlaps with existing slot"