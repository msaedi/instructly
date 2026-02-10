#!/usr/bin/env python3
"""
Seed the 3-level taxonomy: Categories → Subcategories → Services + Filters.

This script performs a deterministic reset seed.
It deletes and re-creates taxonomy data with stable IDs.

Usage:
    # Default (INT database):
    python scripts/seed_data/seed_taxonomy.py

    # Staging:
    USE_STG_DATABASE=true python scripts/seed_data/seed_taxonomy.py

    # Custom DB URL:
    python scripts/seed_data/seed_taxonomy.py --db-url postgresql://...
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
from typing import Any

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ════════════════════════════════════════════════════════════════════
# SLUG HELPER
# ════════════════════════════════════════════════════════════════════


def slugify(name: str) -> str:
    """Convert a display name to a URL-friendly slug."""
    s = name.lower()
    s = s.replace("&", "")
    s = s.replace("/", "-")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def deterministic_id(namespace: str, key: str) -> str:
    """Generate a stable 26-char ULID-like ID from namespace + key."""
    digest = hashlib.sha256(f"{namespace}:{key}".encode("utf-8")).digest()[:16]
    num = int.from_bytes(digest, "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(CROCKFORD_ALPHABET[num & 31])
        num >>= 5
    return "".join(reversed(chars))


# ════════════════════════════════════════════════════════════════════
# CATEGORY DATA
# ════════════════════════════════════════════════════════════════════

CATEGORIES = [
    {
        "name": "Tutoring & Test Prep",
        "slug": "tutoring",
        "subtitle": "Academic STEM Tech",
        "description": "Find expert tutors and test prep instructors in NYC",
        "icon_name": "book-open",
        "display_order": 1,
    },
    {
        "name": "Music",
        "slug": "music",
        "subtitle": "Instrument Voice Theory",
        "description": "Private music lessons with verified NYC instructors",
        "icon_name": "music",
        "display_order": 2,
    },
    {
        "name": "Dance",
        "slug": "dance",
        "subtitle": "Ballet Latin Street",
        "description": "Dance classes and private lessons across NYC",
        "icon_name": "disc",
        "display_order": 3,
    },
    {
        "name": "Languages",
        "slug": "languages",
        "subtitle": "World Languages ESL",
        "description": "Language lessons with native and fluent speakers in NYC",
        "icon_name": "globe",
        "display_order": 4,
    },
    {
        "name": "Sports & Fitness",
        "slug": "sports",
        "subtitle": "Coaching Training Athletics",
        "description": "Sports coaching and personal training in NYC",
        "icon_name": "trophy",
        "display_order": 5,
    },
    {
        "name": "Arts",
        "slug": "arts",
        "subtitle": "Visual Performing Applied",
        "description": "Art classes, workshops, and creative instruction in NYC",
        "icon_name": "palette",
        "display_order": 6,
    },
    {
        "name": "Hobbies & Life Skills",
        "slug": "hobbies",
        "subtitle": "Cooking Coaching Wellness",
        "description": "Life skills coaching, culinary classes, and more in NYC",
        "icon_name": "sparkles",
        "display_order": 7,
    },
]


# ════════════════════════════════════════════════════════════════════
# SUBCATEGORY + SERVICE DATA
# ════════════════════════════════════════════════════════════════════
# Format: { "Category Name": [ (subcategory_name, order, [services...]), ... ] }

TAXONOMY: dict[str, list[tuple[str, int, list[str]]]] = {
    "Tutoring & Test Prep": [
        (
            "Math",
            1,
            [
                "Math",
                "Math Through Play",
                "Algebra",
                "Geometry",
                "Trigonometry",
                "Calculus",
                "Statistics",
            ],
        ),
        ("Reading", 2, ["Reading", "Phonics", "Storytime", "Speed Reading"]),
        (
            "Test Prep",
            3,
            [
                "SAT",
                "ACT",
                "PSAT",
                "GRE",
                "GMAT",
                "LSAT",
                "MCAT",
                "TOEFL",
                "IELTS",
                "SHSAT",
                "SSAT",
                "ISEE",
                "Regents",
                "GED",
            ],
        ),
        ("English", 4, ["English", "Grammar", "Writing", "College Essays"]),
        ("Science", 5, ["Biology", "Chemistry", "Physics", "Environmental Science"]),
        (
            "Coding & STEM",
            6,
            [
                "STEM for Littles",
                "Kids Coding (Scratch)",
                "Game Design",
                "Robotics",
                "Python",
                "JavaScript",
                "Web Development",
                "AI & Machine Learning",
            ],
        ),
        (
            "Learning Support",
            7,
            ["Executive Function", "Dyslexia", "Dyscalculia", "ADHD", "IEP Support"],
        ),
        ("Homework Help", 8, ["Homework Help"]),
        ("History & Social Studies", 9, ["History & Social Studies"]),
        ("Economics", 10, ["Economics"]),
    ],
    "Music": [
        ("Piano", 1, ["Piano", "Keyboard", "Accordion"]),
        ("Guitar", 2, ["Guitar", "Bass"]),
        ("Voice & Singing", 3, ["Voice & Singing"]),
        ("Violin", 4, ["Violin"]),
        ("Drums & Percussion", 5, ["Drums & Percussion"]),
        ("Ukulele", 6, ["Ukulele", "Banjo", "Mandolin"]),
        ("Cello", 7, ["Cello"]),
        ("Orchestral Strings", 8, ["Viola", "Double Bass", "Harp"]),
        ("Woodwinds", 9, ["Flute", "Clarinet", "Saxophone", "Oboe", "Bassoon", "Recorder"]),
        ("Brass", 10, ["Trumpet", "Trombone", "French Horn", "Tuba"]),
        ("Music Theory", 11, ["Music Theory"]),
        ("Music Production", 12, ["Music Production", "DJing", "Songwriting", "Composition"]),
    ],
    "Dance": [
        ("Ballet", 1, ["Ballet"]),
        ("Jazz & Contemporary", 2, ["Jazz & Contemporary"]),
        ("Hip Hop", 3, ["Hip Hop", "Breaking", "K-pop"]),
        ("Ballroom & Latin", 4, ["Salsa", "Bachata", "Tango", "Swing", "Wedding Dance"]),
        ("Tap", 5, ["Tap"]),
        ("Acro", 6, ["Acro"]),
        ("Kids Dance", 7, ["Grown Up & Me Dance", "Developmental Movement"]),
        ("Cultural & Folk", 8, ["Irish", "Bollywood", "African", "Flamenco"]),
        ("Dance Fitness", 9, ["Zumba", "Barre"]),
    ],
    "Languages": [
        ("Spanish", 1, ["Spanish"]),
        ("English (ESL/EFL)", 2, ["English (ESL/EFL)"]),
        ("Chinese", 3, ["Mandarin", "Cantonese"]),
        ("Russian", 4, ["Russian"]),
        ("Arabic", 5, ["Arabic"]),
        ("French", 6, ["French"]),
        ("Korean", 7, ["Korean"]),
        ("Italian", 8, ["Italian"]),
        ("Japanese", 9, ["Japanese"]),
        ("Hebrew", 10, ["Hebrew"]),
        ("German", 11, ["German"]),
        ("Sign Language", 12, ["Sign Language"]),
        (
            "Other Languages",
            13,
            ["Portuguese", "Bengali", "Haitian Creole", "Hindi/Urdu", "Polish", "Greek"],
        ),
    ],
    "Sports & Fitness": [
        ("Swimming", 1, ["Swimming", "ISR (Infant Self-Rescue)"]),
        (
            "Martial Arts",
            2,
            [
                "Karate",
                "Taekwondo",
                "Jiu-Jitsu",
                "Judo",
                "Wrestling",
                "Boxing",
                "Muay Thai",
                "Krav Maga",
                "MMA",
                "Tai Chi",
            ],
        ),
        ("Tennis", 3, ["Tennis"]),
        ("Gymnastics", 4, ["Gymnastics"]),
        ("Personal Training", 5, ["Personal Training"]),
        ("Yoga & Pilates", 6, ["Yoga", "Pilates", "Partner Yoga"]),
        ("Basketball", 7, ["Basketball"]),
        ("Soccer", 8, ["Soccer"]),
        ("Pickleball", 9, ["Pickleball"]),
        ("Chess", 10, ["Chess"]),
        (
            "More Sports",
            11,
            [
                "Golf",
                "Baseball",
                "Softball",
                "Football",
                "Volleyball",
                "Lacrosse",
                "Running",
                "Ice Skating",
                "Figure Skating",
                "Hockey",
                "Skateboarding",
                "Rock Climbing",
                "Squash",
                "Fencing",
                "Archery",
                "Bike Riding",
                "Cheerleading",
            ],
        ),
    ],
    "Arts": [
        ("Drawing", 1, ["Drawing", "Illustration", "Cartooning"]),
        ("Painting", 2, ["Watercolor", "Oil", "Acrylic", "Paint & Sip"]),
        (
            "Kids Art",
            3,
            [
                "Sensory Art",
                "Messy Art",
                "Kids Scribble",
                "Grown Up & Me Art",
                "Make & Take",
                "Craft Homework",
                "Clay Play",
                "Beading",
                "Little Builders",
            ],
        ),
        ("Pottery", 4, ["Pottery"]),
        ("Photography", 5, ["Photography"]),
        ("Acting", 6, ["Acting"]),
        ("Fashion Design", 7, ["Fashion Design"]),
        ("Filmmaking", 8, ["Filmmaking"]),
        ("Graphic Design", 9, ["Graphic Design"]),
        ("Calligraphy", 10, ["Calligraphy"]),
        ("Sewing & Knitting", 11, ["Knitting", "Crocheting", "Embroidery", "Sewing"]),
        (
            "Crafts & Making",
            12,
            ["Jewelry Making", "Woodworking", "Candle Making", "Floral Design"],
        ),
    ],
    "Hobbies & Life Skills": [
        (
            "Food & Drink",
            1,
            [
                "Pasta Making",
                "Sushi Making",
                "Knife Skills",
                "Cuisines",
                "Baking",
                "Cake Decorating",
                "Mixology",
                "Coffee Tasting",
                "Latte Art",
                "Wine Tasting",
                "Cooking for Littles",
            ],
        ),
        ("Dog Training", 2, ["Dog Training"]),
        ("Improv", 3, ["Improv"]),
        (
            "Life & Career Coaching",
            4,
            [
                "Life Coaching",
                "Career Coaching",
                "Interview Prep",
                "Public Speaking",
                "Parenting Coaching",
                "Spiritual Coaching",
                "Newborn Sleep Coaching",
                "Dating Coaching",
                "Accountability Partner",
            ],
        ),
        ("Makeup & Styling", 5, ["Makeup", "Styling", "Nail Art"]),
        ("Etiquette", 6, ["Kids Table Manners", "Business Etiquette"]),
        (
            "Mindfulness & Wellness",
            7,
            ["Meditation", "Breathwork", "Infant Massage", "Couples Massage"],
        ),
        ("Spiritual", 8, ["Tarot", "Astrology", "Reiki"]),
        ("Magic", 9, ["Magic"]),
        ("Driving", 10, ["Driving"]),
    ],
}


# ════════════════════════════════════════════════════════════════════
# ELIGIBLE AGE GROUP OVERRIDES
# ════════════════════════════════════════════════════════════════════
# Default is {"kids", "teens", "adults"} — only list exceptions.

DEFAULT_AGE_GROUPS = ["kids", "teens", "adults"]

AGE_GROUP_OVERRIDES: dict[str, list[str]] = {
    # ── Toddler + Kids + Teens + Adults (Suzuki / early-start universal) ── 6 services
    "Piano": ["toddler", "kids", "teens", "adults"],
    "Violin": ["toddler", "kids", "teens", "adults"],
    "Ballet": ["toddler", "kids", "teens", "adults"],
    "Sign Language": ["toddler", "kids", "teens", "adults"],
    "Swimming": ["toddler", "kids", "teens", "adults"],
    "Gymnastics": ["toddler", "kids", "teens", "adults"],
    # ── Toddler + Kids ── 14 services
    "Math Through Play": ["toddler", "kids"],
    "Phonics": ["toddler", "kids"],
    "Storytime": ["toddler", "kids"],
    "STEM for Littles": ["toddler", "kids"],
    "Grown Up & Me Dance": ["toddler", "kids"],
    "Developmental Movement": ["toddler", "kids"],
    "Sensory Art": ["toddler", "kids"],
    "Messy Art": ["toddler", "kids"],
    "Kids Scribble": ["toddler", "kids"],
    "Grown Up & Me Art": ["toddler", "kids"],
    "Clay Play": ["toddler", "kids"],
    "Little Builders": ["toddler", "kids"],
    "Cooking for Littles": ["toddler", "kids"],
    "Kids Table Manners": ["toddler", "kids"],
    # ── Toddler only ── 2 services
    "ISR (Infant Self-Rescue)": ["toddler"],
    "Infant Massage": ["toddler"],
    # ── Kids only ── 4 services
    "Kids Coding (Scratch)": ["kids"],
    "Make & Take": ["kids"],
    "Craft Homework": ["kids"],
    "Beading": ["kids"],
    # ── Kids + Teens ── 9 services
    "SHSAT": ["kids", "teens"],
    "SSAT": ["kids", "teens"],
    "ISEE": ["kids", "teens"],
    "Executive Function": ["kids", "teens"],
    "Dyslexia": ["kids", "teens"],
    "Dyscalculia": ["kids", "teens"],
    "ADHD": ["kids", "teens"],
    "IEP Support": ["kids", "teens"],
    "Homework Help": ["kids", "teens"],
    # ── Teens only ── 5 services
    "SAT": ["teens"],
    "ACT": ["teens"],
    "PSAT": ["teens"],
    "Regents": ["teens"],
    "College Essays": ["teens"],
    # ── Teens + Adults ── 59 services
    "Trigonometry": ["teens", "adults"],
    "Calculus": ["teens", "adults"],
    "Statistics": ["teens", "adults"],
    "TOEFL": ["teens", "adults"],
    "IELTS": ["teens", "adults"],
    "GED": ["teens", "adults"],
    "Biology": ["teens", "adults"],
    "Chemistry": ["teens", "adults"],
    "Physics": ["teens", "adults"],
    "Environmental Science": ["teens", "adults"],
    "History & Social Studies": ["teens", "adults"],
    "Economics": ["teens", "adults"],
    "Python": ["teens", "adults"],
    "JavaScript": ["teens", "adults"],
    "Web Development": ["teens", "adults"],
    "AI & Machine Learning": ["teens", "adults"],
    "Bass": ["teens", "adults"],
    "Double Bass": ["teens", "adults"],
    "Bassoon": ["teens", "adults"],
    "Tuba": ["teens", "adults"],
    "Music Production": ["teens", "adults"],
    "DJing": ["teens", "adults"],
    "Songwriting": ["teens", "adults"],
    "Composition": ["teens", "adults"],
    "Salsa": ["teens", "adults"],
    "Bachata": ["teens", "adults"],
    "Swing": ["teens", "adults"],
    "Flamenco": ["teens", "adults"],
    "Zumba": ["teens", "adults"],
    "Boxing": ["teens", "adults"],
    "Muay Thai": ["teens", "adults"],
    "Krav Maga": ["teens", "adults"],
    "MMA": ["teens", "adults"],
    "Tai Chi": ["teens", "adults"],
    "Personal Training": ["teens", "adults"],
    "Pilates": ["teens", "adults"],
    "Partner Yoga": ["teens", "adults"],
    "Running": ["teens", "adults"],
    "Illustration": ["teens", "adults"],
    "Oil": ["teens", "adults"],
    "Photography": ["teens", "adults"],
    "Fashion Design": ["teens", "adults"],
    "Filmmaking": ["teens", "adults"],
    "Graphic Design": ["teens", "adults"],
    "Calligraphy": ["teens", "adults"],
    "Woodworking": ["teens", "adults"],
    "Candle Making": ["teens", "adults"],
    "Floral Design": ["teens", "adults"],
    "Sushi Making": ["teens", "adults"],
    "Knife Skills": ["teens", "adults"],
    "Cuisines": ["teens", "adults"],
    "Interview Prep": ["teens", "adults"],
    "Public Speaking": ["teens", "adults"],
    "Makeup": ["teens", "adults"],
    "Styling": ["teens", "adults"],
    "Nail Art": ["teens", "adults"],
    "Meditation": ["teens", "adults"],
    "Breathwork": ["teens", "adults"],
    "Driving": ["teens", "adults"],
    # ── Adults only ── 24 services
    "GRE": ["adults"],
    "GMAT": ["adults"],
    "LSAT": ["adults"],
    "MCAT": ["adults"],
    "Tango": ["adults"],
    "Wedding Dance": ["adults"],
    "Barre": ["adults"],
    "Paint & Sip": ["adults"],
    "Mixology": ["adults"],
    "Coffee Tasting": ["adults"],
    "Latte Art": ["adults"],
    "Wine Tasting": ["adults"],
    "Life Coaching": ["adults"],
    "Career Coaching": ["adults"],
    "Parenting Coaching": ["adults"],
    "Spiritual Coaching": ["adults"],
    "Newborn Sleep Coaching": ["adults"],
    "Dating Coaching": ["adults"],
    "Accountability Partner": ["adults"],
    "Business Etiquette": ["adults"],
    "Couples Massage": ["adults"],
    "Tarot": ["adults"],
    "Astrology": ["adults"],
    "Reiki": ["adults"],
}


# ════════════════════════════════════════════════════════════════════
# FILTER DEFINITIONS
# ════════════════════════════════════════════════════════════════════

FILTER_DEFINITIONS = [
    {"key": "skill_level", "display_name": "Skill Level", "filter_type": "multi_select"},
    {"key": "grade_level", "display_name": "Grade Level", "filter_type": "multi_select"},
    {"key": "course_level", "display_name": "Course Level", "filter_type": "multi_select"},
    {"key": "goal", "display_name": "Goal", "filter_type": "multi_select"},
    {"key": "format", "display_name": "Format", "filter_type": "multi_select"},
    {"key": "specialization", "display_name": "Specialization", "filter_type": "multi_select"},
    {"key": "style", "display_name": "Style", "filter_type": "multi_select"},
    {"key": "medium", "display_name": "Medium", "filter_type": "multi_select"},
    {"key": "focus", "display_name": "Focus", "filter_type": "multi_select"},
    {"key": "learner_type", "display_name": "Learner Type", "filter_type": "multi_select"},
]

FILTER_OPTIONS: dict[str, list[tuple[str, str]]] = {
    "skill_level": [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ],
    "grade_level": [
        ("pre_k", "Pre-K"),
        ("elementary", "Elementary (K-5)"),
        ("middle_school", "Middle School (6-8)"),
        ("high_school", "High School (9-12)"),
        ("college", "College"),
        ("adult", "Adult"),
    ],
    "course_level": [
        ("regular", "Regular"),
        ("honors", "Honors"),
        ("ap", "AP"),
        ("ib", "IB"),
    ],
    "goal": [
        ("homework_help", "Homework Help"),
        ("test_prep", "Test Prep"),
        ("enrichment", "Enrichment"),
        ("remedial", "Remedial"),
        ("college_prep", "College Prep"),
        ("learning_differences", "Learning Differences"),
        ("recreation", "Recreation"),
        ("fitness", "Fitness"),
        ("competition", "Competition"),
        ("self_defense", "Self-Defense"),
        ("performance", "Performance"),
        ("wedding", "Wedding"),
        ("hobby", "Hobby"),
        ("portfolio", "Portfolio"),
        ("professional", "Professional"),
        ("career_prep", "Career Prep"),
        ("audition_prep", "Audition Prep"),
    ],
    "format": [
        ("one_time", "One-time"),
        ("ongoing", "Ongoing"),
        ("intensive", "Intensive"),
        ("individual", "Individual"),
        ("small_group", "Small Group"),
        ("team", "Team"),
        ("workshop", "Workshop"),
    ],
    "specialization": [
        ("general", "General"),
        ("dyslexia_reading", "Dyslexia/Reading"),
        ("adhd", "ADHD"),
        ("dyscalculia", "Dyscalculia"),
        ("iep_support", "IEP Support"),
        ("executive_function", "Executive Function"),
        ("medical", "Medical"),
        ("legal", "Legal"),
        ("technical", "Technical"),
    ],
    "style": [
        ("classical", "Classical"),
        ("contemporary", "Contemporary"),
        ("street", "Street"),
        ("social", "Social"),
        ("competition", "Competition"),
    ],
    "medium": [
        ("pencil", "Pencil"),
        ("charcoal", "Charcoal"),
        ("digital", "Digital"),
        ("watercolor", "Watercolor"),
        ("oil", "Oil"),
        ("acrylic", "Acrylic"),
        ("clay", "Clay"),
        ("fabric", "Fabric"),
    ],
    "focus": [
        ("conversational", "Conversational"),
        ("business", "Business"),
        ("academic", "Academic"),
        ("travel", "Travel"),
        ("test_prep", "Test Prep"),
    ],
    "learner_type": [
        ("new_learner", "New Learner"),
        ("heritage_speaker", "Heritage Speaker"),
        ("school_support", "School Support"),
    ],
}

# "ALL" sentinel — means all options for that filter
ALL = "ALL"

# ════════════════════════════════════════════════════════════════════
# SUBCATEGORY ↔ FILTER MAPPINGS (NON-SKILL-LEVEL FILTERS)
# ════════════════════════════════════════════════════════════════════
# Format: { "Category > Subcategory": { "filter_key": [option_values] or ALL } }

BASE_SUBCATEGORY_FILTER_MAP: dict[str, dict[str, Any]] = {
    # ── TUTORING & TEST PREP ──
    "Tutoring & Test Prep > Math": {
        "grade_level": ALL,
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment", "remedial", "college_prep"],
        "format": ["one_time", "ongoing", "intensive"],
    },
    "Tutoring & Test Prep > Reading": {
        "grade_level": ["pre_k", "elementary", "middle_school", "high_school"],
        "goal": ["homework_help", "enrichment", "remedial", "learning_differences"],
        "format": ["one_time", "ongoing"],
    },
    "Tutoring & Test Prep > Test Prep": {
        "grade_level": ["middle_school", "high_school", "college", "adult"],
        "goal": ["test_prep", "college_prep"],
        "format": ["one_time", "ongoing", "intensive"],
    },
    "Tutoring & Test Prep > English": {
        "grade_level": ALL,
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment", "remedial", "college_prep"],
        "format": ["one_time", "ongoing", "intensive"],
    },
    "Tutoring & Test Prep > Science": {
        "grade_level": ["middle_school", "high_school", "college"],
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment", "remedial", "college_prep"],
        "format": ["one_time", "ongoing", "intensive"],
    },
    "Tutoring & Test Prep > Coding & STEM": {
        "grade_level": ALL,
        "goal": ["enrichment", "college_prep", "career_prep"],
        "format": ["one_time", "ongoing"],
    },
    "Tutoring & Test Prep > Learning Support": {
        "grade_level": ["pre_k", "elementary", "middle_school", "high_school"],
        "goal": ["remedial", "learning_differences"],
        "specialization": [
            "general",
            "dyslexia_reading",
            "adhd",
            "dyscalculia",
            "iep_support",
            "executive_function",
        ],
    },
    "Tutoring & Test Prep > Homework Help": {
        "grade_level": ["elementary", "middle_school", "high_school"],
        "format": ["one_time", "ongoing"],
    },
    "Tutoring & Test Prep > History & Social Studies": {
        "grade_level": ["middle_school", "high_school", "college"],
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment"],
        "format": ["one_time", "ongoing"],
    },
    "Tutoring & Test Prep > Economics": {
        "grade_level": ["high_school", "college"],
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment"],
        "format": ["one_time", "ongoing"],
    },
    # ── MUSIC ──
    "Music > Piano": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Guitar": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Voice & Singing": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Violin": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Drums & Percussion": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Ukulele": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Cello": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Orchestral Strings": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Woodwinds": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Brass": {
        "goal": ["hobby", "performance", "competition", "audition_prep"],
    },
    "Music > Music Theory": {
        "goal": ["hobby", "audition_prep", "college_prep"],
    },
    "Music > Music Production": {
        "goal": ["hobby", "professional", "career_prep"],
    },
    # ── DANCE ──
    "Dance > Ballet": {
        "style": ["classical", "contemporary"],
        "goal": ["recreation", "performance", "competition", "audition_prep"],
    },
    "Dance > Jazz & Contemporary": {
        "goal": ["recreation", "performance", "competition", "audition_prep"],
    },
    "Dance > Hip Hop": {
        "style": ["street", "contemporary"],
        "goal": ["recreation", "performance", "competition"],
    },
    "Dance > Ballroom & Latin": {
        "style": ["social", "competition"],
        "goal": ["recreation", "performance", "competition", "wedding"],
    },
    "Dance > Tap": {
        "style": ["classical", "contemporary"],
        "goal": ["recreation", "performance", "competition"],
    },
    "Dance > Acro": {
        "goal": ["recreation", "performance", "competition"],
    },
    "Dance > Cultural & Folk": {
        "goal": ["recreation", "performance"],
    },
    "Dance > Dance Fitness": {
        "goal": ["recreation", "fitness"],
    },
    # ── LANGUAGES ──
    "Languages > Spanish": {
        "focus": ALL,
        "learner_type": ALL,
        "specialization": ["medical", "legal", "technical"],
    },
    "Languages > English (ESL/EFL)": {
        "focus": ALL,
        "learner_type": ["new_learner", "school_support"],
        "specialization": ["medical", "legal", "technical"],
    },
    "Languages > Chinese": {
        "focus": ALL,
        "learner_type": ALL,
        "specialization": ["medical", "legal", "technical"],
    },
    "Languages > Russian": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > Arabic": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > French": {
        "focus": ALL,
        "learner_type": ALL,
        "specialization": ["medical", "legal"],
    },
    "Languages > Korean": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > Italian": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > Japanese": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > Hebrew": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > German": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > Sign Language": {
        "focus": ["conversational", "academic"],
    },
    "Languages > Other Languages": {
        "focus": ["conversational", "academic", "travel"],
        "learner_type": ALL,
    },
    # ── SPORTS & FITNESS ──
    "Sports & Fitness > Swimming": {
        "goal": ["recreation", "fitness", "competition"],
    },
    "Sports & Fitness > Martial Arts": {
        "goal": ["recreation", "fitness", "competition", "self_defense"],
        "format": ["individual", "small_group"],
    },
    "Sports & Fitness > Tennis": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual", "small_group"],
    },
    "Sports & Fitness > Gymnastics": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual", "small_group"],
    },
    "Sports & Fitness > Yoga & Pilates": {
        "goal": ["recreation", "fitness"],
        "format": ["individual", "small_group"],
    },
    "Sports & Fitness > Basketball": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual", "small_group", "team"],
    },
    "Sports & Fitness > Soccer": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual", "small_group", "team"],
    },
    "Sports & Fitness > Pickleball": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual", "small_group"],
    },
    "Sports & Fitness > Chess": {
        "goal": ["recreation", "competition"],
    },
    "Sports & Fitness > More Sports": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual", "small_group", "team"],
    },
    # ── ARTS ──
    "Arts > Drawing": {
        "medium": ["pencil", "charcoal", "digital"],
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Painting": {
        "medium": ["watercolor", "oil", "acrylic"],
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Pottery": {
        "goal": ["hobby", "portfolio"],
    },
    "Arts > Photography": {
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Acting": {
        "goal": ["hobby", "performance", "audition_prep", "professional"],
    },
    "Arts > Fashion Design": {
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Filmmaking": {
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Graphic Design": {
        "goal": ["hobby", "portfolio", "professional", "career_prep"],
    },
    # ── HOBBIES & LIFE SKILLS ──
    "Hobbies & Life Skills > Food & Drink": {
        "goal": ["hobby", "professional"],
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Dog Training": {
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Improv": {
        "goal": ["hobby", "performance", "professional"],
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Life & Career Coaching": {
        "goal": ["career_prep", "professional"],
    },
    "Hobbies & Life Skills > Makeup & Styling": {
        "goal": ["hobby", "professional"],
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Etiquette": {
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Mindfulness & Wellness": {
        "goal": ["recreation", "hobby"],
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Spiritual": {"format": ["workshop", "ongoing"]},
    "Hobbies & Life Skills > Magic": {
        "goal": ["hobby", "performance"],
        "format": ["workshop", "ongoing"],
    },
}


def _build_subcategory_filter_map() -> dict[str, dict[str, Any]]:
    """
    Apply universal `skill_level` to all subcategories.

    Any subcategory not explicitly listed in BASE_SUBCATEGORY_FILTER_MAP will
    receive `skill_level` only.
    """
    result: dict[str, dict[str, Any]] = {}
    for category_name, subcategories in TAXONOMY.items():
        for subcategory_name, _order, _services in subcategories:
            sub_key = f"{category_name} > {subcategory_name}"
            additional_filters = BASE_SUBCATEGORY_FILTER_MAP.get(sub_key, {})
            result[sub_key] = {"skill_level": ALL, **additional_filters}
    return result


SUBCATEGORY_FILTER_MAP: dict[str, dict[str, Any]] = _build_subcategory_filter_map()


# ════════════════════════════════════════════════════════════════════
# SEED FUNCTION
# ════════════════════════════════════════════════════════════════════


def seed_taxonomy(db_url: str | None = None, verbose: bool = True) -> dict[str, int]:
    """
    Seed the complete 3-level taxonomy.

    Returns dict with counts for verification.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.core.config import settings

    if db_url is None:
        db_url = settings.database_url
        if verbose:
            print(f"Using database: {db_url[:40]}...")

    engine = create_engine(db_url)

    stats = {
        "categories": 0,
        "subcategories": 0,
        "services": 0,
        "filter_definitions": 0,
        "filter_options": 0,
        "subcategory_filters": 0,
        "subcategory_filter_options": 0,
        "instructor_slugs": 0,
    }

    with Session(engine) as session:
        # ── Clean existing data (reverse FK order) ──
        if verbose:
            print("\n🗑  Clearing existing taxonomy data...")

        session.execute(text("DELETE FROM subcategory_filter_options"))
        session.execute(text("DELETE FROM subcategory_filters"))
        session.execute(text("DELETE FROM filter_options"))
        session.execute(text("DELETE FROM filter_definitions"))
        # Clear services before subcategories (FK)
        session.execute(text("DELETE FROM service_analytics"))
        session.execute(text("DELETE FROM service_catalog"))
        session.execute(text("DELETE FROM service_subcategories"))
        session.execute(text("DELETE FROM service_categories"))
        session.flush()

        # ── 1. Insert categories ──
        if verbose:
            print("\n📂 Seeding categories...")

        cat_name_to_id: dict[str, str] = {}
        cat_name_to_slug: dict[str, str] = {}
        for cat in CATEGORIES:
            cat_slug = cat["slug"]
            cat_id = deterministic_id("category", cat_slug)
            cat_name_to_id[cat["name"]] = cat_id
            cat_name_to_slug[cat["name"]] = cat_slug
            meta_title = f"{cat['name']} | InstaInstru"
            session.execute(
                text("""
                    INSERT INTO service_categories
                        (id, name, slug, subtitle, description, meta_title, meta_description,
                         display_order, icon_name, created_at)
                    VALUES
                        (:id, :name, :slug, :subtitle, :description, :meta_title, :meta_description,
                         :display_order, :icon_name, NOW())
                """),
                {
                    "id": cat_id,
                    "name": cat["name"],
                    "slug": cat["slug"],
                    "subtitle": cat.get("subtitle", ""),
                    "description": cat.get("description", ""),
                    "meta_title": meta_title,
                    "meta_description": cat.get("description", ""),
                    "display_order": cat["display_order"],
                    "icon_name": cat["icon_name"],
                },
            )
            stats["categories"] += 1
            if verbose:
                print(f"  + {cat['name']}")

        # ── 2. Insert subcategories + services ──
        if verbose:
            print("\n📁 Seeding subcategories & services...")

        sub_key_to_id: dict[str, str] = {}  # "Category > Subcategory" → id
        svc_display_order = 0

        for cat_name, subcats in TAXONOMY.items():
            cat_id = cat_name_to_id[cat_name]
            cat_slug = cat_name_to_slug[cat_name]
            for sub_name, sub_order, services in subcats:
                sub_slug = slugify(sub_name)
                sub_id = deterministic_id("subcategory", f"{cat_slug}:{sub_slug}")
                sub_key = f"{cat_name} > {sub_name}"
                sub_key_to_id[sub_key] = sub_id

                session.execute(
                    text("""
                        INSERT INTO service_subcategories
                            (id, category_id, slug, name, display_order, is_active, created_at)
                        VALUES (:id, :category_id, :slug, :name, :display_order, true, NOW())
                    """),
                    {
                        "id": sub_id,
                        "category_id": cat_id,
                        "slug": sub_slug,
                        "name": sub_name,
                        "display_order": sub_order,
                    },
                )
                stats["subcategories"] += 1

                for svc_name in services:
                    svc_slug = slugify(svc_name)
                    svc_id = deterministic_id("service", f"{cat_slug}:{sub_slug}:{svc_slug}")
                    svc_display_order += 1
                    age_groups = AGE_GROUP_OVERRIDES.get(svc_name, DEFAULT_AGE_GROUPS)

                    session.execute(
                        text("""
                            INSERT INTO service_catalog
                                (id, subcategory_id, name, slug, eligible_age_groups,
                                 default_duration_minutes, online_capable,
                                 display_order, is_active, created_at)
                            VALUES
                                (:id, :subcategory_id, :name, :slug, :eligible_age_groups,
                                 60, true,
                                 :display_order, true, NOW())
                        """),
                        {
                            "id": svc_id,
                            "subcategory_id": sub_id,
                            "name": svc_name,
                            "slug": svc_slug,
                            "eligible_age_groups": age_groups,
                            "display_order": svc_display_order,
                        },
                    )
                    stats["services"] += 1

                if verbose:
                    print(f"  + {cat_name} > {sub_name} ({len(services)} services)")

        # ── 3. Insert filter definitions ──
        if verbose:
            print("\n🔧 Seeding filter definitions...")

        filter_key_to_id: dict[str, str] = {}
        for fd in FILTER_DEFINITIONS:
            fd_id = deterministic_id("filter", fd["key"])
            filter_key_to_id[fd["key"]] = fd_id
            session.execute(
                text("""
                    INSERT INTO filter_definitions (id, key, display_name, filter_type, created_at)
                    VALUES (:id, :key, :display_name, :filter_type, NOW())
                """),
                {
                    "id": fd_id,
                    "key": fd["key"],
                    "display_name": fd["display_name"],
                    "filter_type": fd["filter_type"],
                },
            )
            stats["filter_definitions"] += 1
            if verbose:
                print(f"  + {fd['key']} ({fd['filter_type']})")

        # ── 4. Insert filter options ──
        if verbose:
            print("\n🏷  Seeding filter options...")

        # filter_key → { option_value → option_id }
        option_lookup: dict[str, dict[str, str]] = {}

        for filter_key, options in FILTER_OPTIONS.items():
            fd_id = filter_key_to_id[filter_key]
            option_lookup[filter_key] = {}
            for order, (value, display_name) in enumerate(options):
                opt_id = deterministic_id("option", f"{filter_key}:{value}")
                option_lookup[filter_key][value] = opt_id
                session.execute(
                    text("""
                        INSERT INTO filter_options
                            (id, filter_definition_id, value, display_name, display_order, created_at)
                        VALUES (:id, :fd_id, :value, :display_name, :display_order, NOW())
                    """),
                    {
                        "id": opt_id,
                        "fd_id": fd_id,
                        "value": value,
                        "display_name": display_name,
                        "display_order": order,
                    },
                )
                stats["filter_options"] += 1

            if verbose:
                print(f"  + {filter_key}: {len(options)} options")

        # ── 5. Insert subcategory ↔ filter mappings ──
        if verbose:
            print("\n🔗 Seeding subcategory-filter mappings...")

        for sub_key, filters in SUBCATEGORY_FILTER_MAP.items():
            sub_id = sub_key_to_id.get(sub_key)
            if not sub_id:
                print(f"  ⚠ Subcategory key not found: {sub_key}")
                continue

            filter_order = 0
            for filter_key, option_values in filters.items():
                fd_id = filter_key_to_id.get(filter_key)
                if not fd_id:
                    print(f"  ⚠ Filter key not found: {filter_key}")
                    continue

                # Create subcategory_filters row
                sf_id = deterministic_id("subcategory_filter", f"{sub_id}:{filter_key}")
                session.execute(
                    text("""
                        INSERT INTO subcategory_filters
                            (id, subcategory_id, filter_definition_id, display_order)
                        VALUES (:id, :sub_id, :fd_id, :display_order)
                    """),
                    {
                        "id": sf_id,
                        "sub_id": sub_id,
                        "fd_id": fd_id,
                        "display_order": filter_order,
                    },
                )
                stats["subcategory_filters"] += 1
                filter_order += 1

                # Resolve option values
                if option_values == ALL:
                    resolved_values = list(option_lookup.get(filter_key, {}).keys())
                else:
                    resolved_values = option_values

                # Create subcategory_filter_options rows
                opt_order = 0
                for opt_value in resolved_values:
                    opt_id = option_lookup.get(filter_key, {}).get(opt_value)
                    if not opt_id:
                        print(f"  ⚠ Option not found: {filter_key}.{opt_value}")
                        continue

                    sfo_id = deterministic_id(
                        "subcategory_filter_option",
                        f"{sf_id}:{opt_value}",
                    )
                    session.execute(
                        text("""
                            INSERT INTO subcategory_filter_options
                                (id, subcategory_filter_id, filter_option_id, display_order)
                            VALUES (:id, :sf_id, :opt_id, :display_order)
                        """),
                        {
                            "id": sfo_id,
                            "sf_id": sf_id,
                            "opt_id": opt_id,
                            "display_order": opt_order,
                        },
                    )
                    stats["subcategory_filter_options"] += 1
                    opt_order += 1

            if verbose:
                n_filters = len(filters)
                print(f"  + {sub_key}: {n_filters} filters")

        # ── 6. Generate instructor profile slugs ──
        if verbose:
            print("\n👤 Generating instructor profile slugs...")

        # Fetch instructor profiles missing slugs
        rows = session.execute(
            text("""
                SELECT ip.id, u.first_name, u.last_name
                FROM instructor_profiles ip
                JOIN users u ON u.id = ip.user_id
                WHERE ip.slug IS NULL
            """)
        ).fetchall()

        for row in rows:
            ip_id, first_name, last_name = row
            display_name = f"{first_name or ''} {last_name or ''}".strip()
            if display_name:
                name_part = slugify(display_name)
                id_part = ip_id[:8].lower()
                slug = f"{name_part}-{id_part}"
            else:
                slug = f"instructor-{ip_id[:8].lower()}"

            session.execute(
                text("UPDATE instructor_profiles SET slug = :slug WHERE id = :id"),
                {"slug": slug, "id": ip_id},
            )
            stats["instructor_slugs"] += 1

        if verbose and stats["instructor_slugs"]:
            print(f"  + Updated {stats['instructor_slugs']} instructor slugs")
        elif verbose:
            print("  (no instructor profiles need slugs)")

        session.commit()

    # ── Summary ──
    if verbose:
        print("\n" + "=" * 60)
        print("📊 TAXONOMY SEEDING SUMMARY")
        print("=" * 60)
        print(f"  Categories:               {stats['categories']}")
        print(f"  Subcategories:            {stats['subcategories']}")
        print(f"  Services:                 {stats['services']}")
        print(f"  Filter Definitions:       {stats['filter_definitions']}")
        print(f"  Filter Options:           {stats['filter_options']}")
        print(f"  Subcategory Filters:      {stats['subcategory_filters']}")
        print(f"  Subcategory Filter Opts:  {stats['subcategory_filter_options']}")
        print(f"  Instructor Slugs:         {stats['instructor_slugs']}")
        print("=" * 60)

        # Verify expected counts
        expected = {
            "categories": 7,
            "subcategories": 77,
            "services": 224,
            "filter_definitions": 10,
        }
        all_ok = True
        for key, expected_count in expected.items():
            actual = stats[key]
            status = "✅" if actual == expected_count else "❌"
            if actual != expected_count:
                all_ok = False
                print(f"  {status} {key}: expected {expected_count}, got {actual}")

        if all_ok:
            print("\n✅ All counts match expected values!")
        else:
            print("\n❌ Some counts don't match — check data above!")

    return stats


# ════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ════════════════════════════════════════════════════════════════════


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Seed 3-level taxonomy data")
    parser.add_argument("--db-url", help="Database URL (overrides environment)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    args = parser.parse_args()

    print("🚀 Starting taxonomy seeding...")
    stats = seed_taxonomy(db_url=args.db_url, verbose=not args.quiet)
    print("✅ Taxonomy seeding complete!")

    return 0 if stats["categories"] == 7 and stats["services"] == 224 else 1


if __name__ == "__main__":
    sys.exit(main())
