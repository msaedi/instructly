#!/usr/bin/env python3
"""
Seed the 3-level taxonomy: Categories → Subcategories → Services + Filters.

This script is IDEMPOTENT — running it twice produces no duplicates.
It deletes and re-creates all taxonomy data (clean break from old seed).

Usage:
    # Default (INT database):
    python scripts/seed_data/seed_taxonomy.py

    # Staging:
    USE_STG_DATABASE=true python scripts/seed_data/seed_taxonomy.py

    # Custom DB URL:
    python scripts/seed_data/seed_taxonomy.py --db-url postgresql://...
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

import ulid

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


def _ulid() -> str:
    return str(ulid.ULID())


# ════════════════════════════════════════════════════════════════════
# CATEGORY DATA
# ════════════════════════════════════════════════════════════════════

CATEGORIES = [
    {"name": "Tutoring & Test Prep", "icon_name": "book-open", "display_order": 1},
    {"name": "Music", "icon_name": "music", "display_order": 2},
    {"name": "Dance", "icon_name": "disc", "display_order": 3},
    {"name": "Languages", "icon_name": "globe", "display_order": 4},
    {"name": "Sports & Fitness", "icon_name": "trophy", "display_order": 5},
    {"name": "Arts", "icon_name": "palette", "display_order": 6},
    {"name": "Hobbies & Life Skills", "icon_name": "sparkles", "display_order": 7},
]


# ════════════════════════════════════════════════════════════════════
# SUBCATEGORY + SERVICE DATA
# ════════════════════════════════════════════════════════════════════
# Format: { "Category Name": [ (subcategory_name, order, [services...]), ... ] }

TAXONOMY: dict[str, list[tuple[str, int, list[str]]]] = {
    "Tutoring & Test Prep": [
        ("Math", 1, ["Math", "Math Through Play", "Algebra", "Geometry", "Trigonometry", "Calculus", "Statistics"]),
        ("Reading", 2, ["Reading", "Phonics", "Storytime", "Speed Reading"]),
        ("Test Prep", 3, ["SAT", "ACT", "PSAT", "GRE", "GMAT", "LSAT", "MCAT", "TOEFL", "IELTS", "SHSAT", "SSAT", "ISEE", "Regents", "GED"]),
        ("English", 4, ["English", "Grammar", "Writing", "College Essays"]),
        ("Science", 5, ["Biology", "Chemistry", "Physics", "Environmental Science"]),
        ("Coding & STEM", 6, ["STEM for Littles", "Kids Coding (Scratch)", "Game Design", "Robotics", "Python", "JavaScript", "Web Development", "AI & Machine Learning"]),
        ("Learning Support", 7, ["Executive Function", "Dyslexia", "Dyscalculia", "ADHD", "IEP Support"]),
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
        ("Other Languages", 13, ["Portuguese", "Bengali", "Haitian Creole", "Hindi/Urdu", "Polish", "Greek"]),
    ],
    "Sports & Fitness": [
        ("Swimming", 1, ["Swimming", "ISR (Infant Self-Rescue)"]),
        ("Martial Arts", 2, ["Karate", "Taekwondo", "Jiu-Jitsu", "Judo", "Wrestling", "Boxing", "Muay Thai", "Krav Maga", "MMA", "Tai Chi"]),
        ("Tennis", 3, ["Tennis"]),
        ("Gymnastics", 4, ["Gymnastics"]),
        ("Personal Training", 5, ["Personal Training"]),
        ("Yoga & Pilates", 6, ["Yoga", "Pilates", "Partner Yoga"]),
        ("Basketball", 7, ["Basketball"]),
        ("Soccer", 8, ["Soccer"]),
        ("Pickleball", 9, ["Pickleball"]),
        ("Chess", 10, ["Chess"]),
        ("More Sports", 11, ["Golf", "Baseball", "Softball", "Football", "Volleyball", "Lacrosse", "Running", "Ice Skating", "Figure Skating", "Hockey", "Skateboarding", "Rock Climbing", "Squash", "Fencing", "Archery", "Bike Riding", "Cheerleading"]),
    ],
    "Arts": [
        ("Drawing", 1, ["Drawing", "Illustration", "Cartooning"]),
        ("Painting", 2, ["Watercolor", "Oil", "Acrylic", "Paint & Sip"]),
        ("Kids Art", 3, ["Sensory Art", "Messy Art", "Kids Scribble", "Grown Up & Me Art", "Make & Take", "Craft Homework", "Clay Play", "Beading", "Little Builders"]),
        ("Pottery", 4, ["Pottery"]),
        ("Photography", 5, ["Photography"]),
        ("Acting", 6, ["Acting"]),
        ("Fashion Design", 7, ["Fashion Design"]),
        ("Filmmaking", 8, ["Filmmaking"]),
        ("Graphic Design", 9, ["Graphic Design"]),
        ("Calligraphy", 10, ["Calligraphy"]),
        ("Sewing & Knitting", 11, ["Knitting", "Crocheting", "Embroidery", "Sewing"]),
        ("Crafts & Making", 12, ["Jewelry Making", "Woodworking", "Candle Making", "Floral Design"]),
    ],
    "Hobbies & Life Skills": [
        ("Food & Drink", 1, ["Pasta Making", "Sushi Making", "Knife Skills", "Cuisines", "Baking", "Cake Decorating", "Mixology", "Coffee Tasting", "Latte Art", "Wine Tasting", "Cooking for Littles"]),
        ("Dog Training", 2, ["Dog Training"]),
        ("Improv", 3, ["Improv"]),
        ("Life & Career Coaching", 4, ["Life Coaching", "Career Coaching", "Interview Prep", "Public Speaking", "Parenting Coaching", "Spiritual Coaching", "Newborn Sleep Coaching", "Dating Coaching", "Accountability Partner"]),
        ("Makeup & Styling", 5, ["Makeup", "Styling", "Nail Art"]),
        ("Etiquette", 6, ["Kids Table Manners", "Business Etiquette"]),
        ("Mindfulness & Wellness", 7, ["Meditation", "Breathwork", "Infant Massage", "Couples Massage"]),
        ("Spiritual", 8, ["Tarot", "Astrology", "Reiki"]),
        ("Magic", 9, ["Magic"]),
        ("Driving", 10, ["Driving"]),
    ],
}


# ════════════════════════════════════════════════════════════════════
# ELIGIBLE AGE GROUP OVERRIDES
# ════════════════════════════════════════════════════════════════════
# Default is {"toddler", "kids", "teens", "adults"} — only list exceptions.

DEFAULT_AGE_GROUPS = ["toddler", "kids", "teens", "adults"]

AGE_GROUP_OVERRIDES: dict[str, list[str]] = {
    # Adults only
    "Wine Tasting": ["adults"],
    "Mixology": ["adults"],
    "Paint & Sip": ["adults"],
    "Dating Coaching": ["adults"],
    "Couples Massage": ["adults"],
    "Partner Yoga": ["adults"],
    "Life Coaching": ["adults"],
    "Career Coaching": ["adults"],
    "Spiritual Coaching": ["adults"],
    "Newborn Sleep Coaching": ["adults"],
    "Infant Massage": ["adults"],
    "Parenting Coaching": ["adults"],
    "Accountability Partner": ["adults"],
    "Business Etiquette": ["adults"],
    "Reiki": ["adults"],
    "GRE": ["adults"],
    "GMAT": ["adults"],
    "LSAT": ["adults"],
    "MCAT": ["adults"],
    # Teens + Adults
    "Driving": ["teens", "adults"],
    "Coffee Tasting": ["teens", "adults"],
    "Interview Prep": ["teens", "adults"],
    "Public Speaking": ["teens", "adults"],
    "Tarot": ["teens", "adults"],
    "Astrology": ["teens", "adults"],
    "SAT": ["teens", "adults"],
    "ACT": ["teens", "adults"],
    "PSAT": ["teens", "adults"],
    "TOEFL": ["teens", "adults"],
    "IELTS": ["teens", "adults"],
    "Regents": ["teens", "adults"],
    "GED": ["teens", "adults"],
    "College Essays": ["teens", "adults"],
    # Kids + Teens
    "SHSAT": ["kids", "teens"],
    "SSAT": ["kids", "teens"],
    "ISEE": ["kids", "teens"],
    "Kids Coding (Scratch)": ["kids", "teens"],
    "Kids Table Manners": ["kids", "teens"],
    # Toddler + Kids
    "STEM for Littles": ["toddler", "kids"],
    "Math Through Play": ["toddler", "kids"],
    "Storytime": ["toddler", "kids"],
    "Phonics": ["toddler", "kids"],
    "Sensory Art": ["toddler", "kids"],
    "Messy Art": ["toddler", "kids"],
    "Kids Scribble": ["toddler", "kids"],
    "Grown Up & Me Art": ["toddler", "kids"],
    "Grown Up & Me Dance": ["toddler", "kids"],
    "Developmental Movement": ["toddler", "kids"],
    "Clay Play": ["toddler", "kids"],
    "Make & Take": ["toddler", "kids"],
    "Craft Homework": ["toddler", "kids"],
    "Beading": ["toddler", "kids"],
    "Little Builders": ["toddler", "kids"],
    "Cooking for Littles": ["toddler", "kids"],
    # Toddler only
    "ISR (Infant Self-Rescue)": ["toddler"],
}


# ════════════════════════════════════════════════════════════════════
# FILTER DEFINITIONS
# ════════════════════════════════════════════════════════════════════

FILTER_DEFINITIONS = [
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
        ("one_time_session", "One-time Session"),
        ("ongoing", "Ongoing"),
        ("intensive_prep", "Intensive Prep"),
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
# SUBCATEGORY ↔ FILTER MAPPINGS
# ════════════════════════════════════════════════════════════════════
# Format: { "Category > Subcategory": { "filter_key": [option_values] or ALL } }

SUBCATEGORY_FILTER_MAP: dict[str, dict[str, Any]] = {
    # ── TUTORING & TEST PREP ──
    "Tutoring & Test Prep > Math": {
        "grade_level": ALL,
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment", "remedial", "college_prep"],
        "format": ["one_time_session", "ongoing", "intensive_prep"],
    },
    "Tutoring & Test Prep > Reading": {
        "grade_level": ["pre_k", "elementary", "middle_school", "high_school"],
        "goal": ["homework_help", "enrichment", "remedial", "learning_differences"],
        "format": ["one_time_session", "ongoing"],
    },
    "Tutoring & Test Prep > Test Prep": {
        "grade_level": ["middle_school", "high_school", "college", "adult"],
        "goal": ["test_prep", "college_prep"],
        "format": ["one_time_session", "ongoing", "intensive_prep"],
    },
    "Tutoring & Test Prep > English": {
        "grade_level": ALL,
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment", "remedial", "college_prep"],
        "format": ["one_time_session", "ongoing", "intensive_prep"],
    },
    "Tutoring & Test Prep > Science": {
        "grade_level": ["middle_school", "high_school", "college"],
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment", "remedial", "college_prep"],
        "format": ["one_time_session", "ongoing", "intensive_prep"],
    },
    "Tutoring & Test Prep > Coding & STEM": {
        "grade_level": ALL,
        "goal": ["enrichment", "college_prep", "career_prep"],
        "format": ["one_time_session", "ongoing"],
    },
    "Tutoring & Test Prep > Learning Support": {
        "grade_level": ["pre_k", "elementary", "middle_school", "high_school"],
        "goal": ["remedial", "learning_differences"],
        "format": ["ongoing"],
        "specialization": ["general", "dyslexia_reading", "adhd", "dyscalculia", "iep_support", "executive_function"],
    },
    "Tutoring & Test Prep > Homework Help": {
        "grade_level": ["elementary", "middle_school", "high_school"],
        "format": ["one_time_session", "ongoing"],
    },
    "Tutoring & Test Prep > History & Social Studies": {
        "grade_level": ["middle_school", "high_school", "college"],
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment"],
        "format": ["one_time_session", "ongoing"],
    },
    "Tutoring & Test Prep > Economics": {
        "grade_level": ["high_school", "college"],
        "course_level": ALL,
        "goal": ["homework_help", "test_prep", "enrichment"],
        "format": ["one_time_session", "ongoing"],
    },
    # ── DANCE ──
    "Dance > Ballet": {
        "style": ["classical", "contemporary"],
        "goal": ["recreation", "performance", "competition", "audition_prep"],
    },
    "Dance > Jazz & Contemporary": {
        "style": ["contemporary"],
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
        "style": ["contemporary"],
        "goal": ["recreation", "performance", "competition"],
    },
    "Dance > Kids Dance": {
        "goal": ["recreation"],
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
        "specialization": ["technical"],
    },
    "Languages > Hebrew": {
        "focus": ALL,
        "learner_type": ALL,
    },
    "Languages > German": {
        "focus": ALL,
        "learner_type": ALL,
        "specialization": ["technical"],
    },
    "Languages > Sign Language": {
        "focus": ["conversational", "academic"],
        "learner_type": ["new_learner"],
        "specialization": ["medical"],
    },
    "Languages > Other Languages": {
        "focus": ["conversational", "academic", "travel"],
        "learner_type": ALL,
    },
    # ── SPORTS & FITNESS ──
    "Sports & Fitness > Swimming": {
        "goal": ["recreation", "fitness", "competition"],
        "format": ["individual"],
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
    "Sports & Fitness > Personal Training": {
        "goal": ["fitness"],
        "format": ["individual"],
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
        "format": ["individual"],
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
    "Arts > Kids Art": {
        "goal": ["hobby"],
    },
    "Arts > Pottery": {
        "medium": ["clay"],
        "goal": ["hobby", "portfolio"],
    },
    "Arts > Photography": {
        "medium": ["digital"],
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Acting": {
        "goal": ["hobby", "performance", "audition_prep", "professional"],
    },
    "Arts > Fashion Design": {
        "medium": ["fabric"],
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Filmmaking": {
        "medium": ["digital"],
        "goal": ["hobby", "portfolio", "professional"],
    },
    "Arts > Graphic Design": {
        "medium": ["digital"],
        "goal": ["hobby", "portfolio", "professional", "career_prep"],
    },
    "Arts > Calligraphy": {
        "goal": ["hobby"],
    },
    "Arts > Sewing & Knitting": {
        "medium": ["fabric"],
        "goal": ["hobby"],
    },
    "Arts > Crafts & Making": {
        "goal": ["hobby"],
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
        "format": ["ongoing"],
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
    "Hobbies & Life Skills > Spiritual": {
        "goal": ["hobby"],
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Magic": {
        "goal": ["hobby", "performance"],
        "format": ["workshop", "ongoing"],
    },
    "Hobbies & Life Skills > Driving": {
        "format": ["ongoing"],
    },
}


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
        for cat in CATEGORIES:
            cat_id = _ulid()
            cat_name_to_id[cat["name"]] = cat_id
            session.execute(
                text("""
                    INSERT INTO service_categories (id, name, display_order, icon_name, created_at)
                    VALUES (:id, :name, :display_order, :icon_name, NOW())
                """),
                {
                    "id": cat_id,
                    "name": cat["name"],
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
            for sub_name, sub_order, services in subcats:
                sub_id = _ulid()
                sub_key = f"{cat_name} > {sub_name}"
                sub_key_to_id[sub_key] = sub_id

                session.execute(
                    text("""
                        INSERT INTO service_subcategories (id, category_id, name, display_order, created_at)
                        VALUES (:id, :category_id, :name, :display_order, NOW())
                    """),
                    {
                        "id": sub_id,
                        "category_id": cat_id,
                        "name": sub_name,
                        "display_order": sub_order,
                    },
                )
                stats["subcategories"] += 1

                for svc_name in services:
                    svc_id = _ulid()
                    svc_display_order += 1
                    age_groups = AGE_GROUP_OVERRIDES.get(svc_name, DEFAULT_AGE_GROUPS)
                    svc_slug = slugify(svc_name)

                    session.execute(
                        text("""
                            INSERT INTO service_catalog
                                (id, subcategory_id, name, slug, eligible_age_groups,
                                 display_order, is_active, created_at)
                            VALUES
                                (:id, :subcategory_id, :name, :slug, :eligible_age_groups,
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
            fd_id = _ulid()
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
                opt_id = _ulid()
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
                sf_id = _ulid()
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

                    sfo_id = _ulid()
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
        print("=" * 60)

        # Verify expected counts
        expected = {
            "categories": 7,
            "subcategories": 77,
            "services": 224,
            "filter_definitions": 9,
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
