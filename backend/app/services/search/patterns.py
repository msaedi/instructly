# backend/app/services/search/patterns.py
"""
Regex patterns for NL search query parsing.

Apply patterns in this order: price -> audience -> time -> location -> skill -> urgency
"""
import re
from typing import Dict, Pattern, Tuple

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
# Include optional leading "in the" to avoid leaving behind trailing "in the" tokens
# that can confuse location extraction (e.g., "in ues tomorrow in the morning").
TIME_MORNING: Pattern[str] = re.compile(
    r"\b(?:in\s+(?:the\s+)?)?(?:morning|mornings)\b", re.IGNORECASE
)
TIME_AFTERNOON: Pattern[str] = re.compile(
    r"\b(?:in\s+(?:the\s+)?)?(?:afternoon|afternoons)\b", re.IGNORECASE
)
TIME_EVENING: Pattern[str] = re.compile(
    r"\b(?:in\s+(?:the\s+)?)?(?:evening|evenings|tonight)\b", re.IGNORECASE
)

# Time window resolution
TIME_WINDOWS: Dict[str, Tuple[str, str]] = {
    "morning": ("06:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "21:00"),
}

# =============================================================================
# WEEKDAY PATTERNS (Apply near Date)
# =============================================================================

WEEKDAYS: Dict[str, int] = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

# Pattern: "monday", "this monday", "next mon", etc.
# Group 1: optional prefix ("this"|"next")
# Group 2: weekday token
WEEKDAY_PATTERN: Pattern[str] = re.compile(
    r"\b(?:(this|next)\s+)?(" + "|".join(WEEKDAYS.keys()) + r")\b",
    re.IGNORECASE,
)

# Pattern: "weekend", "this weekend", "next weekend"
WEEKEND_PATTERN: Pattern[str] = re.compile(r"\b(?:(this|next)\s+)?weekend\b", re.IGNORECASE)

# =============================================================================
# LESSON TYPE PATTERNS (Apply before Location)
# =============================================================================

# Online/virtual lesson patterns
LESSON_TYPE_ONLINE: Pattern[str] = re.compile(
    r"\b(?:online|virtual|remote|zoom|video|webcam)\b", re.IGNORECASE
)

# In-person lesson patterns
LESSON_TYPE_IN_PERSON: Pattern[str] = re.compile(
    r"\b(?:in[-\s]?person|face[-\s]?to[-\s]?face|in[-\s]?home|at[-\s]?home)\b", re.IGNORECASE
)


# =============================================================================
# LOCATION PATTERNS (Apply Fourth)
# =============================================================================

# Location extraction:
# - Supports multi-word locations ("lower east side")
# - Avoids swallowing trailing constraints ("for kids", "under 80", "monday", etc.)
# - Allows optional "the" ("in the upper west side")
LOCATION_PREPOSITION: Pattern[str] = re.compile(
    r"\b(?:in|near|around)\b\s+(?:the\s+)?"
    r"([A-Za-z][A-Za-z\s\-''.]{2,30}?)"
    r"(?:\s+(?:area|neighborhood|district))?"
    r"(?=\s+(?:for|under|after|before|today|tomorrow|this|next|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\s*$)",
    re.IGNORECASE,
)

# Near me patterns - expanded to catch more variations
NEAR_ME: Pattern[str] = re.compile(
    r"\b(?:near\s+me|nearby|close\s+(?:by|to\s+me)|in\s+my\s+area|around\s+me|my\s+neighborhood)\b",
    re.IGNORECASE,
)

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
# 3-LEVEL TAXONOMY DETECTION
#
# Category → Subcategory → Service.  Keys are category names (DB values).
# Used for: price intent resolution, search result narrowing, and LLM hints.
# =============================================================================

# Maps keyword → category name (service_categories.name)
CATEGORY_KEYWORDS: Dict[str, str] = {
    # ── Tutoring & Test Prep ──────────────────────────────────────
    "tutor": "Tutoring & Test Prep",
    "tutoring": "Tutoring & Test Prep",
    "test prep": "Tutoring & Test Prep",
    "sat": "Tutoring & Test Prep",
    "act": "Tutoring & Test Prep",
    "math": "Tutoring & Test Prep",
    "algebra": "Tutoring & Test Prep",
    "calculus": "Tutoring & Test Prep",
    "geometry": "Tutoring & Test Prep",
    "trigonometry": "Tutoring & Test Prep",
    "statistics": "Tutoring & Test Prep",
    "reading": "Tutoring & Test Prep",
    "phonics": "Tutoring & Test Prep",
    "writing": "Tutoring & Test Prep",
    "grammar": "Tutoring & Test Prep",
    "science": "Tutoring & Test Prep",
    "biology": "Tutoring & Test Prep",
    "chemistry": "Tutoring & Test Prep",
    "physics": "Tutoring & Test Prep",
    "environmental science": "Tutoring & Test Prep",
    "coding": "Tutoring & Test Prep",
    "stem": "Tutoring & Test Prep",
    "python": "Tutoring & Test Prep",
    "javascript": "Tutoring & Test Prep",
    "homework": "Tutoring & Test Prep",
    "homework help": "Tutoring & Test Prep",
    "shsat": "Tutoring & Test Prep",
    "ssat": "Tutoring & Test Prep",
    "isee": "Tutoring & Test Prep",
    "gre": "Tutoring & Test Prep",
    "gmat": "Tutoring & Test Prep",
    "lsat": "Tutoring & Test Prep",
    "mcat": "Tutoring & Test Prep",
    "regents": "Tutoring & Test Prep",
    "ged": "Tutoring & Test Prep",
    "psat": "Tutoring & Test Prep",
    "ielts": "Tutoring & Test Prep",
    "toefl": "Tutoring & Test Prep",
    "college essays": "Tutoring & Test Prep",
    "dyslexia": "Tutoring & Test Prep",
    "adhd": "Tutoring & Test Prep",
    "iep": "Tutoring & Test Prep",
    "learning support": "Tutoring & Test Prep",
    "dyscalculia": "Tutoring & Test Prep",
    "executive function": "Tutoring & Test Prep",
    "economics": "Tutoring & Test Prep",
    "history": "Tutoring & Test Prep",
    "social studies": "Tutoring & Test Prep",
    "robotics": "Tutoring & Test Prep",
    "game design": "Tutoring & Test Prep",
    "web development": "Tutoring & Test Prep",
    "ai": "Tutoring & Test Prep",
    "machine learning": "Tutoring & Test Prep",
    "speed reading": "Tutoring & Test Prep",
    "storytime": "Tutoring & Test Prep",
    "essay": "Tutoring & Test Prep",
    "scratch": "Tutoring & Test Prep",
    # ── Music ─────────────────────────────────────────────────────
    "music": "Music",
    "piano": "Music",
    "keyboard": "Music",
    "guitar": "Music",
    "violin": "Music",
    "voice": "Music",
    "singing": "Music",
    "vocal": "Music",
    "drums": "Music",
    "percussion": "Music",
    "bass": "Music",
    "saxophone": "Music",
    "trumpet": "Music",
    "flute": "Music",
    "clarinet": "Music",
    "cello": "Music",
    "ukulele": "Music",
    "banjo": "Music",
    "mandolin": "Music",
    "music theory": "Music",
    "music production": "Music",
    "composition": "Music",
    "songwriting": "Music",
    "djing": "Music",
    "dj": "Music",
    "recorder": "Music",
    "viola": "Music",
    "trombone": "Music",
    "oboe": "Music",
    "bassoon": "Music",
    "harp": "Music",
    "accordion": "Music",
    "tuba": "Music",
    "french horn": "Music",
    "double bass": "Music",
    "music lessons": "Music",
    "instrument": "Music",
    # ── Dance ─────────────────────────────────────────────────────
    "dance": "Dance",
    "dancing": "Dance",
    "ballet": "Dance",
    "jazz dance": "Dance",
    "hip hop": "Dance",
    "hip-hop": "Dance",
    "tap": "Dance",
    "contemporary": "Dance",
    "modern dance": "Dance",
    "ballroom": "Dance",
    "salsa": "Dance",
    "bachata": "Dance",
    "swing": "Dance",
    "tango": "Dance",
    "acro": "Dance",
    "acrobatics": "Dance",
    "dance fitness": "Dance",
    "pointe": "Dance",
    "lyrical": "Dance",
    "breakdance": "Dance",
    "breaking": "Dance",
    "barre": "Dance",
    "zumba": "Dance",
    "choreography": "Dance",
    "wedding dance": "Dance",
    "first dance": "Dance",
    "bollywood": "Dance",
    "flamenco": "Dance",
    "irish dance": "Dance",
    "k-pop": "Dance",
    "kpop": "Dance",
    # ── Languages ─────────────────────────────────────────────────
    "language": "Languages",
    "spanish": "Languages",
    "french": "Languages",
    "mandarin": "Languages",
    "chinese": "Languages",
    "italian": "Languages",
    "german": "Languages",
    "portuguese": "Languages",
    "japanese": "Languages",
    "korean": "Languages",
    "russian": "Languages",
    "arabic": "Languages",
    "hebrew": "Languages",
    "hindi": "Languages",
    "polish": "Languages",
    "asl": "Languages",
    "sign language": "Languages",
    "esl": "Languages",
    "english as second": "Languages",
    "greek": "Languages",
    "cantonese": "Languages",
    "bengali": "Languages",
    "haitian creole": "Languages",
    "urdu": "Languages",
    # ── Sports & Fitness ──────────────────────────────────────────
    "sports": "Sports & Fitness",
    "fitness": "Sports & Fitness",
    "tennis": "Sports & Fitness",
    "swimming": "Sports & Fitness",
    "basketball": "Sports & Fitness",
    "soccer": "Sports & Fitness",
    "baseball": "Sports & Fitness",
    "softball": "Sports & Fitness",
    "volleyball": "Sports & Fitness",
    "football": "Sports & Fitness",
    "golf": "Sports & Fitness",
    "yoga": "Sports & Fitness",
    "pilates": "Sports & Fitness",
    "martial arts": "Sports & Fitness",
    "karate": "Sports & Fitness",
    "judo": "Sports & Fitness",
    "jiu jitsu": "Sports & Fitness",
    "jiu-jitsu": "Sports & Fitness",
    "bjj": "Sports & Fitness",
    "taekwondo": "Sports & Fitness",
    "boxing": "Sports & Fitness",
    "kickboxing": "Sports & Fitness",
    "muay thai": "Sports & Fitness",
    "mma": "Sports & Fitness",
    "wrestling": "Sports & Fitness",
    "gymnastics": "Sports & Fitness",
    "fencing": "Sports & Fitness",
    "running": "Sports & Fitness",
    "archery": "Sports & Fitness",
    "squash": "Sports & Fitness",
    "hockey": "Sports & Fitness",
    "lacrosse": "Sports & Fitness",
    "skating": "Sports & Fitness",
    "ice skating": "Sports & Fitness",
    "figure skating": "Sports & Fitness",
    "rock climbing": "Sports & Fitness",
    "personal training": "Sports & Fitness",
    "strength training": "Sports & Fitness",
    "weight training": "Sports & Fitness",
    "isr": "Sports & Fitness",
    "water safety": "Sports & Fitness",
    "martial": "Sports & Fitness",
    "chess": "Sports & Fitness",
    "pickleball": "Sports & Fitness",
    "krav maga": "Sports & Fitness",
    "tai chi": "Sports & Fitness",
    "skateboarding": "Sports & Fitness",
    "cheerleading": "Sports & Fitness",
    # ── Arts ──────────────────────────────────────────────────────
    "art": "Arts",
    "arts": "Arts",
    "drawing": "Arts",
    "painting": "Arts",
    "sculpture": "Arts",
    "ceramics": "Arts",
    "pottery": "Arts",
    "photography": "Arts",
    "digital art": "Arts",
    "graphic design": "Arts",
    "illustration": "Arts",
    "calligraphy": "Arts",
    "sketching": "Arts",
    "watercolor": "Arts",
    "oil painting": "Arts",
    "acrylic": "Arts",
    "knitting": "Arts",
    "crochet": "Arts",
    "crocheting": "Arts",
    "embroidery": "Arts",
    "sewing": "Arts",
    "jewelry making": "Arts",
    "woodworking": "Arts",
    "acting": "Arts",
    "fashion": "Arts",
    "fashion design": "Arts",
    "filmmaking": "Arts",
    "cartooning": "Arts",
    "candle making": "Arts",
    "floral design": "Arts",
    "crafts": "Arts",
    # ── Hobbies & Life Skills ─────────────────────────────────────
    "cooking": "Hobbies & Life Skills",
    "baking": "Hobbies & Life Skills",
    "magic": "Hobbies & Life Skills",
    "wine tasting": "Hobbies & Life Skills",
    "mixology": "Hobbies & Life Skills",
    "cocktails": "Hobbies & Life Skills",
    "pet training": "Hobbies & Life Skills",
    "dog training": "Hobbies & Life Skills",
    "public speaking": "Hobbies & Life Skills",
    "life skills": "Hobbies & Life Skills",
    "meditation": "Hobbies & Life Skills",
    "mindfulness": "Hobbies & Life Skills",
    "improv": "Hobbies & Life Skills",
    "etiquette": "Hobbies & Life Skills",
    "tarot": "Hobbies & Life Skills",
    "astrology": "Hobbies & Life Skills",
    "reiki": "Hobbies & Life Skills",
    "driving": "Hobbies & Life Skills",
    "makeup": "Hobbies & Life Skills",
    "nail art": "Hobbies & Life Skills",
    "styling": "Hobbies & Life Skills",
    "life coaching": "Hobbies & Life Skills",
    "career coaching": "Hobbies & Life Skills",
    "breathwork": "Hobbies & Life Skills",
}

# Maps keyword → subcategory name (service_subcategories.name)
SUBCATEGORY_KEYWORDS: Dict[str, str] = {
    # ── Tutoring & Test Prep ──────────────────────────────────────
    "algebra": "Math",
    "calculus": "Math",
    "geometry": "Math",
    "trigonometry": "Math",
    "statistics": "Math",
    "math": "Math",
    "arithmetic": "Math",
    "sat": "Test Prep",
    "act": "Test Prep",
    "shsat": "Test Prep",
    "ssat": "Test Prep",
    "isee": "Test Prep",
    "gre": "Test Prep",
    "gmat": "Test Prep",
    "lsat": "Test Prep",
    "mcat": "Test Prep",
    "psat": "Test Prep",
    "regents": "Test Prep",
    "ged": "Test Prep",
    "ielts": "Test Prep",
    "toefl": "Test Prep",
    "test prep": "Test Prep",
    "reading": "Reading",
    "phonics": "Reading",
    "speed reading": "Reading",
    "storytime": "Reading",
    "writing": "English",
    "grammar": "English",
    "essay": "English",
    "college essays": "English",
    "biology": "Science",
    "chemistry": "Science",
    "physics": "Science",
    "environmental science": "Science",
    "science": "Science",
    "economics": "Economics",
    "history": "History & Social Studies",
    "social studies": "History & Social Studies",
    "coding": "Coding & STEM",
    "python": "Coding & STEM",
    "javascript": "Coding & STEM",
    "web development": "Coding & STEM",
    "game design": "Coding & STEM",
    "robotics": "Coding & STEM",
    "ai": "Coding & STEM",
    "machine learning": "Coding & STEM",
    "stem": "Coding & STEM",
    "scratch": "Coding & STEM",
    "dyslexia": "Learning Support",
    "adhd": "Learning Support",
    "iep": "Learning Support",
    "learning support": "Learning Support",
    "dyscalculia": "Learning Support",
    "executive function": "Learning Support",
    "homework": "Homework Help",
    "homework help": "Homework Help",
    # ── Music ─────────────────────────────────────────────────────
    "piano": "Piano",
    "keyboard": "Piano",
    "accordion": "Piano",
    "guitar": "Guitar",
    "bass": "Guitar",
    "voice": "Voice & Singing",
    "singing": "Voice & Singing",
    "vocal": "Voice & Singing",
    "violin": "Violin",
    "drums": "Drums & Percussion",
    "percussion": "Drums & Percussion",
    "ukulele": "Ukulele",
    "banjo": "Ukulele",
    "mandolin": "Ukulele",
    "cello": "Cello",
    "viola": "Orchestral Strings",
    "harp": "Orchestral Strings",
    "double bass": "Orchestral Strings",
    "flute": "Woodwinds",
    "clarinet": "Woodwinds",
    "saxophone": "Woodwinds",
    "oboe": "Woodwinds",
    "bassoon": "Woodwinds",
    "recorder": "Woodwinds",
    "trumpet": "Brass",
    "trombone": "Brass",
    "french horn": "Brass",
    "tuba": "Brass",
    "music theory": "Music Theory",
    "music production": "Music Production",
    "djing": "Music Production",
    "dj": "Music Production",
    "songwriting": "Music Production",
    "composition": "Music Production",
    # ── Dance ─────────────────────────────────────────────────────
    "ballet": "Ballet",
    "jazz dance": "Jazz & Contemporary",
    "contemporary": "Jazz & Contemporary",
    "modern dance": "Jazz & Contemporary",
    "lyrical": "Jazz & Contemporary",
    "hip hop": "Hip Hop",
    "hip-hop": "Hip Hop",
    "breakdance": "Hip Hop",
    "breaking": "Hip Hop",
    "k-pop": "Hip Hop",
    "kpop": "Hip Hop",
    "ballroom": "Ballroom & Latin",
    "salsa": "Ballroom & Latin",
    "bachata": "Ballroom & Latin",
    "swing": "Ballroom & Latin",
    "tango": "Ballroom & Latin",
    "wedding dance": "Ballroom & Latin",
    "first dance": "Ballroom & Latin",
    "latin dance": "Ballroom & Latin",
    "tap": "Tap",
    "acro": "Acro",
    "acrobatics": "Acro",
    "kids dance": "Kids Dance",
    "bollywood": "Cultural & Folk",
    "flamenco": "Cultural & Folk",
    "irish dance": "Cultural & Folk",
    "african dance": "Cultural & Folk",
    "folk dance": "Cultural & Folk",
    "dance fitness": "Dance Fitness",
    "zumba": "Dance Fitness",
    "barre": "Dance Fitness",
    # ── Languages ─────────────────────────────────────────────────
    "spanish": "Spanish",
    "french": "French",
    "mandarin": "Chinese",
    "chinese": "Chinese",
    "cantonese": "Chinese",
    "japanese": "Japanese",
    "korean": "Korean",
    "italian": "Italian",
    "german": "German",
    "russian": "Russian",
    "arabic": "Arabic",
    "hebrew": "Hebrew",
    "asl": "Sign Language",
    "sign language": "Sign Language",
    "esl": "English (ESL/EFL)",
    "english as second": "English (ESL/EFL)",
    "portuguese": "Other Languages",
    "hindi": "Other Languages",
    "urdu": "Other Languages",
    "polish": "Other Languages",
    "greek": "Other Languages",
    "bengali": "Other Languages",
    "haitian creole": "Other Languages",
    # ── Sports & Fitness ──────────────────────────────────────────
    "tennis": "Tennis",
    "swimming": "Swimming",
    "isr": "Swimming",
    "water safety": "Swimming",
    "basketball": "Basketball",
    "soccer": "Soccer",
    "yoga": "Yoga & Pilates",
    "pilates": "Yoga & Pilates",
    "martial arts": "Martial Arts",
    "karate": "Martial Arts",
    "judo": "Martial Arts",
    "jiu jitsu": "Martial Arts",
    "jiu-jitsu": "Martial Arts",
    "bjj": "Martial Arts",
    "taekwondo": "Martial Arts",
    "boxing": "Martial Arts",
    "kickboxing": "Martial Arts",
    "muay thai": "Martial Arts",
    "mma": "Martial Arts",
    "wrestling": "Martial Arts",
    "krav maga": "Martial Arts",
    "tai chi": "Martial Arts",
    "gymnastics": "Gymnastics",
    "personal training": "Personal Training",
    "strength training": "Personal Training",
    "weight training": "Personal Training",
    "pickleball": "Pickleball",
    "chess": "Chess",
    "golf": "More Sports",
    "baseball": "More Sports",
    "softball": "More Sports",
    "volleyball": "More Sports",
    "football": "More Sports",
    "lacrosse": "More Sports",
    "running": "More Sports",
    "fencing": "More Sports",
    "archery": "More Sports",
    "ice skating": "More Sports",
    "figure skating": "More Sports",
    "skating": "More Sports",
    "rock climbing": "More Sports",
    "squash": "More Sports",
    "hockey": "More Sports",
    "skateboarding": "More Sports",
    "cheerleading": "More Sports",
    # ── Arts ──────────────────────────────────────────────────────
    "drawing": "Drawing",
    "sketching": "Drawing",
    "illustration": "Drawing",
    "cartooning": "Drawing",
    "painting": "Painting",
    "watercolor": "Painting",
    "oil painting": "Painting",
    "acrylic": "Painting",
    "kids art": "Kids Art",
    "pottery": "Pottery",
    "ceramics": "Pottery",
    "sculpture": "Pottery",
    "photography": "Photography",
    "acting": "Acting",
    "theater": "Acting",
    "theatre": "Acting",
    "fashion design": "Fashion Design",
    "fashion": "Fashion Design",
    "filmmaking": "Filmmaking",
    "film": "Filmmaking",
    "digital art": "Graphic Design",
    "graphic design": "Graphic Design",
    "calligraphy": "Calligraphy",
    "lettering": "Calligraphy",
    "sewing": "Sewing & Knitting",
    "knitting": "Sewing & Knitting",
    "crochet": "Sewing & Knitting",
    "crocheting": "Sewing & Knitting",
    "embroidery": "Sewing & Knitting",
    "jewelry making": "Crafts & Making",
    "woodworking": "Crafts & Making",
    "candle making": "Crafts & Making",
    "floral design": "Crafts & Making",
    "crafts": "Crafts & Making",
    # ── Hobbies & Life Skills ─────────────────────────────────────
    "cooking": "Food & Drink",
    "baking": "Food & Drink",
    "mixology": "Food & Drink",
    "wine tasting": "Food & Drink",
    "coffee": "Food & Drink",
    "sushi": "Food & Drink",
    "pasta": "Food & Drink",
    "cocktails": "Food & Drink",
    "dog training": "Dog Training",
    "pet training": "Dog Training",
    "improv": "Improv",
    "public speaking": "Life & Career Coaching",
    "life coaching": "Life & Career Coaching",
    "career coaching": "Life & Career Coaching",
    "interview prep": "Life & Career Coaching",
    "makeup": "Makeup & Styling",
    "nail art": "Makeup & Styling",
    "styling": "Makeup & Styling",
    "etiquette": "Etiquette",
    "table manners": "Etiquette",
    "meditation": "Mindfulness & Wellness",
    "mindfulness": "Mindfulness & Wellness",
    "breathwork": "Mindfulness & Wellness",
    "tarot": "Spiritual",
    "astrology": "Spiritual",
    "reiki": "Spiritual",
    "magic": "Magic",
    "driving": "Driving",
}

# Maps keyword → exact service_catalog.name (most specific level)
SERVICE_KEYWORDS: Dict[str, str] = {
    # ── Tutoring & Test Prep ──────────────────────────────────────
    "sat": "SAT",
    "act": "ACT",
    "psat": "PSAT",
    "shsat": "SHSAT",
    "ssat": "SSAT",
    "isee": "ISEE",
    "gre": "GRE",
    "gmat": "GMAT",
    "lsat": "LSAT",
    "mcat": "MCAT",
    "toefl": "TOEFL",
    "ielts": "IELTS",
    "regents": "Regents",
    "ged": "GED",
    "algebra": "Algebra",
    "calculus": "Calculus",
    "geometry": "Geometry",
    "trigonometry": "Trigonometry",
    "statistics": "Statistics",
    "biology": "Biology",
    "chemistry": "Chemistry",
    "physics": "Physics",
    "environmental science": "Environmental Science",
    "python": "Python",
    "javascript": "JavaScript",
    "robotics": "Robotics",
    "game design": "Game Design",
    "web development": "Web Development",
    "dyslexia": "Dyslexia",
    "dyscalculia": "Dyscalculia",
    # ── Music ─────────────────────────────────────────────────────
    "piano": "Piano",
    "guitar": "Guitar",
    "bass": "Bass",
    "violin": "Violin",
    "cello": "Cello",
    "drums": "Drums & Percussion",
    "ukulele": "Ukulele",
    "banjo": "Banjo",
    "mandolin": "Mandolin",
    "flute": "Flute",
    "clarinet": "Clarinet",
    "saxophone": "Saxophone",
    "oboe": "Oboe",
    "bassoon": "Bassoon",
    "recorder": "Recorder",
    "trumpet": "Trumpet",
    "trombone": "Trombone",
    "french horn": "French Horn",
    "tuba": "Tuba",
    "viola": "Viola",
    "harp": "Harp",
    "double bass": "Double Bass",
    "accordion": "Accordion",
    "keyboard": "Keyboard",
    "djing": "DJing",
    "dj": "DJing",
    "songwriting": "Songwriting",
    "composition": "Composition",
    # ── Dance ─────────────────────────────────────────────────────
    "ballet": "Ballet",
    "salsa": "Salsa",
    "bachata": "Bachata",
    "tango": "Tango",
    "wedding dance": "Wedding Dance",
    "breaking": "Breaking",
    "k-pop": "K-pop",
    "kpop": "K-pop",
    "zumba": "Zumba",
    "barre": "Barre",
    "tap": "Tap",
    "bollywood": "Bollywood",
    "flamenco": "Flamenco",
    "acro": "Acro",
    # ── Languages ─────────────────────────────────────────────────
    "spanish": "Spanish",
    "french": "French",
    "mandarin": "Mandarin",
    "cantonese": "Cantonese",
    "japanese": "Japanese",
    "korean": "Korean",
    "italian": "Italian",
    "german": "German",
    "russian": "Russian",
    "arabic": "Arabic",
    "hebrew": "Hebrew",
    "asl": "Sign Language",
    "sign language": "Sign Language",
    "portuguese": "Portuguese",
    "bengali": "Bengali",
    "polish": "Polish",
    "greek": "Greek",
    # ── Sports & Fitness ──────────────────────────────────────────
    "karate": "Karate",
    "judo": "Judo",
    "bjj": "Jiu-Jitsu",
    "jiu jitsu": "Jiu-Jitsu",
    "jiu-jitsu": "Jiu-Jitsu",
    "taekwondo": "Taekwondo",
    "boxing": "Boxing",
    "muay thai": "Muay Thai",
    "mma": "MMA",
    "wrestling": "Wrestling",
    "krav maga": "Krav Maga",
    "tai chi": "Tai Chi",
    "tennis": "Tennis",
    "swimming": "Swimming",
    "basketball": "Basketball",
    "soccer": "Soccer",
    "golf": "Golf",
    "baseball": "Baseball",
    "volleyball": "Volleyball",
    "gymnastics": "Gymnastics",
    "fencing": "Fencing",
    "archery": "Archery",
    "yoga": "Yoga",
    "pilates": "Pilates",
    "pickleball": "Pickleball",
    "chess": "Chess",
    "hockey": "Hockey",
    "lacrosse": "Lacrosse",
    "squash": "Squash",
    "rock climbing": "Rock Climbing",
    "ice skating": "Ice Skating",
    "figure skating": "Figure Skating",
    "skateboarding": "Skateboarding",
    # ── Arts ──────────────────────────────────────────────────────
    "photography": "Photography",
    "pottery": "Pottery",
    "calligraphy": "Calligraphy",
    "acting": "Acting",
    "filmmaking": "Filmmaking",
    "watercolor": "Watercolor",
    "embroidery": "Embroidery",
    "jewelry making": "Jewelry Making",
    "woodworking": "Woodworking",
    "candle making": "Candle Making",
    # ── Hobbies & Life Skills ─────────────────────────────────────
    "baking": "Baking",
    "magic": "Magic",
    "improv": "Improv",
    "tarot": "Tarot",
    "astrology": "Astrology",
    "reiki": "Reiki",
    "driving": "Driving",
    "meditation": "Meditation",
    "makeup": "Makeup",
}
