# backend/app/services/search/patterns.py
"""
Regex patterns for NL search query parsing.

Apply patterns in this order: price -> audience -> time -> location -> skill -> urgency
"""
import re
from typing import Dict, List, Pattern, Tuple

# =============================================================================
# PRICE PATTERNS (Apply First)
# =============================================================================

# Explicit price with $ symbol
PRICE_UNDER_DOLLAR: Pattern[str] = re.compile(r"under\s*\$(\d+)", re.IGNORECASE)
PRICE_LESS_THAN: Pattern[str] = re.compile(r"less\s+than\s*\$(\d+)", re.IGNORECASE)
PRICE_MAX: Pattern[str] = re.compile(r"max\s*\$?(\d+)", re.IGNORECASE)
PRICE_OR_LESS: Pattern[str] = re.compile(r"\$?(\d+)\s*or\s*(?:less|under)", re.IGNORECASE)

# Price with explicit currency words
PRICE_DOLLARS: Pattern[str] = re.compile(r"(\d+)\s*dollars", re.IGNORECASE)
PRICE_PER_HOUR: Pattern[str] = re.compile(r"\$?(\d+)\s*(?:per\s+hour|/hr|an\s+hour)", re.IGNORECASE)

# Implicit price (must check for age disambiguation)
PRICE_UNDER_IMPLICIT: Pattern[str] = re.compile(
    r"under\s+(\d+)(?!\s*(?:year|yr|old))", re.IGNORECASE
)

# Price intent keywords
BUDGET_KEYWORDS: Pattern[str] = re.compile(
    r"\b(?:cheap|budget|affordable|inexpensive)\b", re.IGNORECASE
)
PREMIUM_KEYWORDS: Pattern[str] = re.compile(r"\b(?:premium|luxury|high-end|top)\b", re.IGNORECASE)

# Context check for price/age disambiguation
KID_CONTEXT: Pattern[str] = re.compile(
    r"\b(?:kid|kids|child|children|age|year|yr|old)\b", re.IGNORECASE
)

# =============================================================================
# AUDIENCE PATTERNS (Apply Second)
# =============================================================================

AGE_YEAR_OLD: Pattern[str] = re.compile(r"(\d{1,2})\s*(?:year|yr)s?\s*old", re.IGNORECASE)
AGE_EXPLICIT: Pattern[str] = re.compile(r"age\s*(\d{1,2})", re.IGNORECASE)
AGE_FOR_MY: Pattern[str] = re.compile(r"for\s+my\s+(\d{1,2})\s*(?:year|yr)", re.IGNORECASE)
KIDS_KEYWORDS: Pattern[str] = re.compile(
    r"\b(?:kid|kids|child|children|toddler|toddlers)\b", re.IGNORECASE
)
TEEN_KEYWORDS: Pattern[str] = re.compile(r"\b(?:teen|teens|teenager|teenagers)\b", re.IGNORECASE)
ADULT_KEYWORDS: Pattern[str] = re.compile(r"\b(?:adult|adults)\b", re.IGNORECASE)

# =============================================================================
# TIME PATTERNS (Apply Third)
# =============================================================================

TIME_AFTER: Pattern[str] = re.compile(r"after\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
TIME_BEFORE: Pattern[str] = re.compile(r"before\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
TIME_AT: Pattern[str] = re.compile(r"(?:^|\s)at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
TIME_AROUND: Pattern[str] = re.compile(r"around\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
TIME_MORNING: Pattern[str] = re.compile(r"\b(?:morning|mornings)\b", re.IGNORECASE)
TIME_AFTERNOON: Pattern[str] = re.compile(r"\b(?:afternoon|afternoons)\b", re.IGNORECASE)
TIME_EVENING: Pattern[str] = re.compile(r"\b(?:evening|evenings|tonight)\b", re.IGNORECASE)

# Time window resolution
TIME_WINDOWS: Dict[str, Tuple[str, str]] = {
    "morning": ("06:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "21:00"),
}

# =============================================================================
# LOCATION PATTERNS (Apply Fourth)
# =============================================================================

# Location extraction:
# - Supports multi-word locations ("lower east side")
# - Avoids swallowing trailing constraints ("for kids", "under 80", "monday", etc.)
# - Allows optional "the" ("in the upper west side")
LOCATION_PREPOSITION: Pattern[str] = re.compile(
    r"\b(?:in|near|around)\b\s+(?:the\s+)?"
    r"([A-Za-z][A-Za-z\s\-'’.]{2,30}?)"
    r"(?:\s+(?:area|neighborhood|district))?"
    r"(?=\s+(?:for|under|after|before|today|tomorrow|this|next|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\s*$)",
    re.IGNORECASE,
)
NEAR_ME: Pattern[str] = re.compile(r"\b(?:near\s+me|nearby|close\s+by)\b", re.IGNORECASE)

# =============================================================================
# SKILL LEVEL PATTERNS (Apply Fifth)
# =============================================================================

SKILL_BEGINNER: Pattern[str] = re.compile(
    r"\b(?:beginner|beginners|beginning|novice|starter|new\s+to)\b", re.IGNORECASE
)
SKILL_INTERMEDIATE: Pattern[str] = re.compile(
    r"\b(?:intermediate|mid-level|some\s+experience)\b", re.IGNORECASE
)
SKILL_ADVANCED: Pattern[str] = re.compile(
    r"\b(?:advanced|expert|experienced|professional)\b", re.IGNORECASE
)

# =============================================================================
# URGENCY PATTERNS (Apply Sixth)
# =============================================================================

URGENCY_HIGH: Pattern[str] = re.compile(
    r"\b(?:urgent|urgently|asap|immediately|right\s+now)\b", re.IGNORECASE
)
URGENCY_MEDIUM: Pattern[str] = re.compile(
    r"\b(?:soon|soonest|earliest|first\s+available)\b", re.IGNORECASE
)

# =============================================================================
# CATEGORY DETECTION (for price intent resolution)
# =============================================================================

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "music": [
        "piano",
        "guitar",
        "violin",
        "drums",
        "voice",
        "singing",
        "cello",
        "flute",
        "saxophone",
        "trumpet",
    ],
    "tutoring": [
        "math",
        "sat",
        "act",
        "tutor",
        "homework",
        "essay",
        "science",
        "reading",
        "writing",
        "algebra",
    ],
    "sports": [
        "yoga",
        "tennis",
        "swimming",
        "fitness",
        "basketball",
        "soccer",
        "martial",
        "boxing",
        "pilates",
    ],
    "language": [
        "spanish",
        "french",
        "mandarin",
        "chinese",
        "esl",
        "japanese",
        "korean",
        "italian",
        "german",
    ],
}
