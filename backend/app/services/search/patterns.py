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
    # ── Music ─────────────────────────────────────────────────────
    "music": "Music",
    "piano": "Music",
    "guitar": "Music",
    "violin": "Music",
    "voice": "Music",
    "singing": "Music",
    "vocal": "Music",
    "drums": "Music",
    "bass": "Music",
    "saxophone": "Music",
    "trumpet": "Music",
    "flute": "Music",
    "clarinet": "Music",
    "cello": "Music",
    "ukulele": "Music",
    "music theory": "Music",
    "music production": "Music",
    "composition": "Music",
    "songwriting": "Music",
    "djing": "Music",
    "dj": "Music",
    "recorder": "Music",
    "harmonica": "Music",
    "banjo": "Music",
    "viola": "Music",
    "trombone": "Music",
    "oboe": "Music",
    "harp": "Music",
    "accordion": "Music",
    "organ": "Music",
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
    "choreography": "Dance",
    "wedding dance": "Dance",
    "first dance": "Dance",
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
    "latin": "Languages",
    "turkish": "Languages",
    "dutch": "Languages",
    "persian": "Languages",
    "farsi": "Languages",
    "swahili": "Languages",
    "urdu": "Languages",
    "vietnamese": "Languages",
    "tagalog": "Languages",
    "cantonese": "Languages",
    # ── Sports & Fitness ──────────────────────────────────────────
    "sports": "Sports & Fitness",
    "fitness": "Sports & Fitness",
    "tennis": "Sports & Fitness",
    "swimming": "Sports & Fitness",
    "basketball": "Sports & Fitness",
    "soccer": "Sports & Fitness",
    "baseball": "Sports & Fitness",
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
    "track": "Sports & Fitness",
    "running": "Sports & Fitness",
    "cross country": "Sports & Fitness",
    "archery": "Sports & Fitness",
    "table tennis": "Sports & Fitness",
    "ping pong": "Sports & Fitness",
    "badminton": "Sports & Fitness",
    "squash": "Sports & Fitness",
    "racquetball": "Sports & Fitness",
    "hockey": "Sports & Fitness",
    "lacrosse": "Sports & Fitness",
    "skating": "Sports & Fitness",
    "ice skating": "Sports & Fitness",
    "rock climbing": "Sports & Fitness",
    "personal training": "Sports & Fitness",
    "strength training": "Sports & Fitness",
    "weight training": "Sports & Fitness",
    "isr": "Sports & Fitness",
    "water safety": "Sports & Fitness",
    "martial": "Sports & Fitness",
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
    "animation": "Arts",
    "sketching": "Arts",
    "watercolor": "Arts",
    "oil painting": "Arts",
    "acrylic": "Arts",
    "printmaking": "Arts",
    "mixed media": "Arts",
    "collage": "Arts",
    "fiber arts": "Arts",
    "weaving": "Arts",
    "knitting": "Arts",
    "crochet": "Arts",
    "quilting": "Arts",
    "stained glass": "Arts",
    "jewelry making": "Arts",
    "metalwork": "Arts",
    "woodworking": "Arts",
    # ── Hobbies & Life Skills ─────────────────────────────────────
    "cooking": "Hobbies & Life Skills",
    "baking": "Hobbies & Life Skills",
    "chess": "Hobbies & Life Skills",
    "magic": "Hobbies & Life Skills",
    "gardening": "Hobbies & Life Skills",
    "sewing": "Hobbies & Life Skills",
    "wine tasting": "Hobbies & Life Skills",
    "mixology": "Hobbies & Life Skills",
    "cocktails": "Hobbies & Life Skills",
    "pet training": "Hobbies & Life Skills",
    "dog training": "Hobbies & Life Skills",
    "public speaking": "Hobbies & Life Skills",
    "presentation": "Hobbies & Life Skills",
    "debate": "Hobbies & Life Skills",
    "first aid": "Hobbies & Life Skills",
    "cpr": "Hobbies & Life Skills",
    "survival": "Hobbies & Life Skills",
    "life skills": "Hobbies & Life Skills",
    "home repair": "Hobbies & Life Skills",
    "financial literacy": "Hobbies & Life Skills",
    "meditation": "Hobbies & Life Skills",
    "mindfulness": "Hobbies & Life Skills",
    "diy": "Hobbies & Life Skills",
    "crafts": "Hobbies & Life Skills",
    "origami": "Hobbies & Life Skills",
    "candle making": "Hobbies & Life Skills",
    "soap making": "Hobbies & Life Skills",
    "floral arrangement": "Hobbies & Life Skills",
    "flower": "Hobbies & Life Skills",
    "beekeeping": "Hobbies & Life Skills",
    "mushroom foraging": "Hobbies & Life Skills",
    "fermentation": "Hobbies & Life Skills",
}

# Maps keyword → subcategory name (service_subcategories.name)
SUBCATEGORY_KEYWORDS: Dict[str, str] = {
    # Tutoring & Test Prep subcategories
    "algebra": "Math",
    "calculus": "Math",
    "geometry": "Math",
    "trigonometry": "Math",
    "statistics": "Math",
    "math": "Math",
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
    "reading": "Reading & Writing",
    "phonics": "Reading & Writing",
    "writing": "Reading & Writing",
    "grammar": "Reading & Writing",
    "essay": "Reading & Writing",
    "college essays": "Reading & Writing",
    "speed reading": "Reading & Writing",
    "storytime": "Reading & Writing",
    "biology": "Science",
    "chemistry": "Science",
    "physics": "Science",
    "science": "Science",
    "economics": "Social Studies & Humanities",
    "history": "Social Studies & Humanities",
    "social studies": "Social Studies & Humanities",
    "coding": "Computer Science",
    "python": "Computer Science",
    "javascript": "Computer Science",
    "web development": "Computer Science",
    "game design": "Computer Science",
    "robotics": "Computer Science",
    "ai": "Computer Science",
    "machine learning": "Computer Science",
    "stem": "Computer Science",
    "dyslexia": "Learning Support",
    "adhd": "Learning Support",
    "iep": "Learning Support",
    "learning support": "Learning Support",
    "dyscalculia": "Learning Support",
    "executive function": "Learning Support",
    "homework": "Homework Help",
    "homework help": "Homework Help",
    # Music subcategories
    "piano": "Keyboard",
    "organ": "Keyboard",
    "guitar": "Guitar",
    "bass": "Guitar",
    "banjo": "Guitar",
    "ukulele": "Guitar",
    "violin": "Strings",
    "viola": "Strings",
    "cello": "Strings",
    "harp": "Strings",
    "voice": "Voice",
    "singing": "Voice",
    "vocal": "Voice",
    "drums": "Percussion",
    "flute": "Woodwinds",
    "clarinet": "Woodwinds",
    "saxophone": "Woodwinds",
    "oboe": "Woodwinds",
    "recorder": "Woodwinds",
    "harmonica": "Woodwinds",
    "trumpet": "Brass",
    "trombone": "Brass",
    "accordion": "Brass",
    "music theory": "Music Theory & Composition",
    "composition": "Music Theory & Composition",
    "songwriting": "Music Theory & Composition",
    "music production": "Music Production & Technology",
    "djing": "Music Production & Technology",
    "dj": "Music Production & Technology",
    # Dance subcategories
    "ballet": "Ballet",
    "jazz dance": "Jazz",
    "hip hop": "Hip Hop",
    "hip-hop": "Hip Hop",
    "tap": "Tap",
    "contemporary": "Contemporary & Modern",
    "modern dance": "Contemporary & Modern",
    "lyrical": "Contemporary & Modern",
    "ballroom": "Ballroom & Social",
    "salsa": "Ballroom & Social",
    "bachata": "Ballroom & Social",
    "swing": "Ballroom & Social",
    "tango": "Ballroom & Social",
    "wedding dance": "Ballroom & Social",
    "first dance": "Ballroom & Social",
    "breakdance": "Breaking & Street Styles",
    "breaking": "Breaking & Street Styles",
    # Languages subcategories
    "spanish": "Spanish",
    "french": "French",
    "mandarin": "Mandarin Chinese",
    "chinese": "Mandarin Chinese",
    "cantonese": "Mandarin Chinese",
    "japanese": "Japanese",
    "korean": "Korean",
    "italian": "Italian",
    "german": "German",
    "portuguese": "Portuguese",
    "russian": "Russian",
    "arabic": "Arabic",
    "hebrew": "Hebrew",
    "hindi": "Hindi",
    "asl": "ASL & Sign Language",
    "sign language": "ASL & Sign Language",
    "esl": "ESL",
    "english as second": "ESL",
    # Sports & Fitness subcategories
    "tennis": "Tennis",
    "swimming": "Swimming",
    "basketball": "Basketball",
    "soccer": "Soccer",
    "baseball": "Baseball",
    "volleyball": "Volleyball",
    "golf": "Golf",
    "yoga": "Yoga & Pilates",
    "pilates": "Yoga & Pilates",
    "martial arts": "Martial Arts",
    "karate": "Martial Arts",
    "judo": "Martial Arts",
    "jiu jitsu": "Martial Arts",
    "jiu-jitsu": "Martial Arts",
    "bjj": "Martial Arts",
    "taekwondo": "Martial Arts",
    "boxing": "Boxing & Kickboxing",
    "kickboxing": "Boxing & Kickboxing",
    "muay thai": "Boxing & Kickboxing",
    "mma": "Boxing & Kickboxing",
    "wrestling": "Boxing & Kickboxing",
    "gymnastics": "Gymnastics",
    "fencing": "Fencing",
    "personal training": "Personal Training",
    "strength training": "Personal Training",
    "weight training": "Personal Training",
    "isr": "Swimming",
    "water safety": "Swimming",
    "skating": "Ice Skating",
    "ice skating": "Ice Skating",
    "rock climbing": "Rock Climbing",
    # Arts subcategories
    "drawing": "Drawing & Sketching",
    "sketching": "Drawing & Sketching",
    "illustration": "Drawing & Sketching",
    "painting": "Painting",
    "watercolor": "Painting",
    "oil painting": "Painting",
    "acrylic": "Painting",
    "sculpture": "Sculpture & Ceramics",
    "ceramics": "Sculpture & Ceramics",
    "pottery": "Sculpture & Ceramics",
    "photography": "Photography",
    "digital art": "Digital Art & Design",
    "graphic design": "Digital Art & Design",
    "animation": "Digital Art & Design",
    "calligraphy": "Calligraphy & Lettering",
    # Hobbies subcategories
    "cooking": "Cooking & Baking",
    "baking": "Cooking & Baking",
    "chess": "Chess",
    "magic": "Magic",
    "gardening": "Gardening",
    "sewing": "Sewing & Textiles",
    "knitting": "Sewing & Textiles",
    "crochet": "Sewing & Textiles",
    "quilting": "Sewing & Textiles",
    "public speaking": "Public Speaking & Debate",
    "debate": "Public Speaking & Debate",
    "meditation": "Meditation & Mindfulness",
    "mindfulness": "Meditation & Mindfulness",
}

# Maps keyword → exact service_catalog.name (most specific level)
SERVICE_KEYWORDS: Dict[str, str] = {
    # Martial arts specifics
    "karate": "Karate",
    "judo": "Judo",
    "bjj": "Brazilian Jiu-Jitsu",
    "jiu jitsu": "Brazilian Jiu-Jitsu",
    "jiu-jitsu": "Brazilian Jiu-Jitsu",
    "taekwondo": "Taekwondo",
    "muay thai": "Muay Thai",
    "wrestling": "Wrestling",
    # Music specifics
    "piano": "Piano",
    "guitar": "Guitar",
    "violin": "Violin",
    "cello": "Cello",
    "drums": "Drums",
    "flute": "Flute",
    "clarinet": "Clarinet",
    "saxophone": "Saxophone",
    "trumpet": "Trumpet",
    "ukulele": "Ukulele",
    "harp": "Harp",
    "viola": "Viola",
    "trombone": "Trombone",
    "oboe": "Oboe",
    "banjo": "Banjo",
    "harmonica": "Harmonica",
    "accordion": "Accordion",
    # Dance specifics
    "ballet": "Ballet",
    "salsa": "Salsa",
    "bachata": "Bachata",
    "tango": "Tango",
    # Sports specifics
    "tennis": "Tennis",
    "swimming": "Swimming",
    "basketball": "Basketball",
    "soccer": "Soccer",
    "baseball": "Baseball",
    "volleyball": "Volleyball",
    "golf": "Golf",
    "fencing": "Fencing",
    "archery": "Archery",
    "boxing": "Boxing",
    "kickboxing": "Kickboxing",
    "yoga": "Yoga",
    "pilates": "Pilates",
    # Languages specifics
    "spanish": "Spanish",
    "french": "French",
    "mandarin": "Mandarin Chinese",
    "japanese": "Japanese",
    "korean": "Korean",
    "italian": "Italian",
    "german": "German",
    "portuguese": "Portuguese",
    "russian": "Russian",
    "arabic": "Arabic",
    "hebrew": "Hebrew",
    "hindi": "Hindi",
    "asl": "ASL",
    # Tutoring specifics
    "sat": "SAT Prep",
    "act": "ACT Prep",
    "shsat": "SHSAT Prep",
    "ssat": "SSAT Prep",
    "gre": "GRE Prep",
    "gmat": "GMAT Prep",
    "lsat": "LSAT Prep",
    "mcat": "MCAT Prep",
    "algebra": "Algebra",
    "calculus": "Calculus",
    "geometry": "Geometry",
    "trigonometry": "Trigonometry",
    "statistics": "Statistics",
    "biology": "Biology",
    "chemistry": "Chemistry",
    "physics": "Physics",
    "python": "Python",
    # Arts specifics
    "photography": "Photography",
    "pottery": "Pottery",
    "calligraphy": "Calligraphy",
    # Hobbies specifics
    "chess": "Chess",
    "cooking": "Cooking",
    "baking": "Baking",
}
