# backend/app/services/search/typo_correction.py
"""
SymSpell-based typo correction for search queries.

Provides fast, accurate typo correction using the SymSpell algorithm.
Includes domain-specific terms for music, tutoring, sports, and NYC locations.
"""
from functools import lru_cache
import logging
import os
from typing import Optional, Tuple

from symspellpy import SymSpell, Verbosity

logger = logging.getLogger(__name__)

# Singleton instance
_symspell: Optional[SymSpell] = None


def get_symspell() -> SymSpell:
    """Get or create SymSpell instance with dictionary loaded."""
    global _symspell
    if _symspell is None:
        _symspell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)

        # Try to load frequency dictionary from symspellpy package
        try:
            from importlib.resources import files

            dict_path = str(files("symspellpy").joinpath("frequency_dictionary_en_82_765.txt"))
            if os.path.exists(dict_path):
                _symspell.load_dictionary(dict_path, term_index=0, count_index=1)
                logger.info(f"Loaded SymSpell dictionary from {dict_path}")
            else:
                logger.warning("SymSpell dictionary not found, using domain terms only")
        except Exception as e:
            logger.warning(f"Failed to load SymSpell dictionary: {e}")

        # Load custom domain terms
        _load_domain_dictionary(_symspell)

    return _symspell


def _load_domain_dictionary(sym: SymSpell) -> None:
    """Add domain-specific terms with very high frequency to override general English."""
    # Use frequencies higher than common English words (which max around 100M)
    # to ensure domain terms are always preferred for typo correction
    HIGH_FREQ = 200_000_000  # Higher than any common English word
    MED_FREQ = 150_000_000
    LOW_FREQ = 100_000_000

    domain_terms = [
        # Music instruments and lessons - highest priority
        ("piano", HIGH_FREQ),
        ("guitar", HIGH_FREQ),
        ("violin", HIGH_FREQ),
        ("drums", HIGH_FREQ),
        ("saxophone", MED_FREQ),
        ("cello", MED_FREQ),
        ("flute", MED_FREQ),
        ("trumpet", MED_FREQ),
        ("ukulele", MED_FREQ),
        ("vocals", MED_FREQ),
        ("singing", HIGH_FREQ),
        ("voice", MED_FREQ),
        ("bass", MED_FREQ),
        ("clarinet", LOW_FREQ),
        ("trombone", LOW_FREQ),
        ("harmonica", LOW_FREQ),
        # Tutoring subjects
        ("tutoring", HIGH_FREQ),
        ("tutor", HIGH_FREQ),
        ("math", HIGH_FREQ),
        ("mathematics", MED_FREQ),
        ("algebra", MED_FREQ),
        ("calculus", MED_FREQ),
        ("geometry", MED_FREQ),
        ("trigonometry", LOW_FREQ),
        ("statistics", LOW_FREQ),
        ("physics", MED_FREQ),
        ("chemistry", MED_FREQ),
        ("biology", MED_FREQ),
        ("science", MED_FREQ),
        ("english", HIGH_FREQ),
        ("writing", HIGH_FREQ),
        ("reading", HIGH_FREQ),
        ("essay", MED_FREQ),
        ("grammar", LOW_FREQ),
        ("literature", LOW_FREQ),
        ("history", MED_FREQ),
        ("economics", LOW_FREQ),
        # Test prep
        ("sat", HIGH_FREQ),
        ("act", MED_FREQ),
        ("gre", MED_FREQ),
        ("gmat", MED_FREQ),
        ("lsat", MED_FREQ),
        ("mcat", MED_FREQ),
        ("shsat", LOW_FREQ),
        # Languages
        ("spanish", HIGH_FREQ),
        ("french", HIGH_FREQ),
        ("mandarin", MED_FREQ),
        ("chinese", HIGH_FREQ),
        ("japanese", MED_FREQ),
        ("korean", MED_FREQ),
        ("german", MED_FREQ),
        ("italian", MED_FREQ),
        ("portuguese", LOW_FREQ),
        ("russian", LOW_FREQ),
        ("arabic", LOW_FREQ),
        ("hebrew", LOW_FREQ),
        # Sports and fitness
        ("tennis", HIGH_FREQ),
        ("swimming", HIGH_FREQ),
        ("yoga", HIGH_FREQ),
        ("pilates", MED_FREQ),
        ("basketball", MED_FREQ),
        ("soccer", MED_FREQ),
        ("golf", MED_FREQ),
        ("boxing", LOW_FREQ),
        ("martial", LOW_FREQ),
        ("karate", LOW_FREQ),
        ("taekwondo", LOW_FREQ),
        ("judo", LOW_FREQ),
        ("fencing", LOW_FREQ),
        # Arts
        ("painting", MED_FREQ),
        ("drawing", MED_FREQ),
        ("photography", MED_FREQ),
        ("pottery", LOW_FREQ),
        ("sculpting", LOW_FREQ),
        ("dance", MED_FREQ),
        ("ballet", LOW_FREQ),
        # Kids/age groups
        ("toddler", MED_FREQ),
        ("toddlers", MED_FREQ),
        ("preschool", MED_FREQ),
        ("kindergarten", MED_FREQ),
        ("kids", HIGH_FREQ),
        ("children", MED_FREQ),
        ("beginner", MED_FREQ),
        ("beginners", MED_FREQ),
        ("advanced", LOW_FREQ),
        ("intermediate", LOW_FREQ),
        # NYC boroughs
        ("manhattan", HIGH_FREQ),
        ("brooklyn", HIGH_FREQ),
        ("queens", HIGH_FREQ),
        ("bronx", HIGH_FREQ),
        ("staten", MED_FREQ),
        # NYC neighborhoods
        ("williamsburg", MED_FREQ),
        ("bushwick", LOW_FREQ),
        ("astoria", LOW_FREQ),
        ("harlem", MED_FREQ),
        ("chelsea", MED_FREQ),
        ("soho", LOW_FREQ),
        ("tribeca", LOW_FREQ),
        ("greenpoint", LOW_FREQ),
        ("flushing", LOW_FREQ),
        ("midtown", MED_FREQ),
        # Common lesson-related words
        ("lessons", HIGH_FREQ),
        ("lesson", HIGH_FREQ),
        ("classes", MED_FREQ),
        ("class", MED_FREQ),
        ("instructor", MED_FREQ),
        ("teacher", MED_FREQ),
        ("coach", MED_FREQ),
        ("private", MED_FREQ),
        ("online", MED_FREQ),
        ("virtual", LOW_FREQ),
        ("affordable", MED_FREQ),
        ("cheap", LOW_FREQ),
        ("budget", LOW_FREQ),
        ("expensive", LOW_FREQ),
        ("premium", LOW_FREQ),
    ]

    for term, freq in domain_terms:
        # Create entry with high frequency to prioritize domain terms
        sym.create_dictionary_entry(term, freq)

    logger.info(f"Loaded {len(domain_terms)} domain-specific terms")


# Words to skip during correction (prepositions, articles, etc.)
SKIP_WORDS = frozenset(
    {
        "in",
        "at",
        "for",
        "the",
        "and",
        "or",
        "with",
        "near",
        "by",
        "to",
        "a",
        "an",
        "on",
        "of",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "my",
        "me",
        "i",
        "we",
        "us",
        "our",
        "under",
        "over",
        "around",
        "about",
        "from",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "up",
        "down",
        "out",
        "off",
        "this",
        "that",
        "these",
        "those",
        "am",
        "pm",
    }
)


import re as _re

# Pattern to match time tokens like "5pm", "10am", "3:00pm"
TIME_TOKEN_PATTERN = _re.compile(r"^\d{1,2}(:\d{2})?(am|pm)$", _re.IGNORECASE)


def correct_typos(text: str, max_edit_distance: int = 2) -> Tuple[str, bool]:
    """
    Correct typos in search text.

    Args:
        text: Input text to correct
        max_edit_distance: Maximum edit distance for corrections (1 or 2)

    Returns:
        Tuple of (corrected_text, was_corrected)
    """
    if not text or not text.strip():
        return text, False

    sym = get_symspell()
    words = text.lower().split()
    corrected_words = []
    was_corrected = False

    for word in words:
        # Skip short words, numbers, and special tokens
        if len(word) <= 2 or word.isdigit() or word.startswith("$"):
            corrected_words.append(word)
            continue

        # Skip known prepositions/articles
        if word in SKIP_WORDS:
            corrected_words.append(word)
            continue

        # Skip time tokens like "5pm", "10am", "3:00pm"
        if TIME_TOKEN_PATTERN.match(word):
            corrected_words.append(word)
            continue

        # Check for correction
        suggestions = sym.lookup(word, Verbosity.CLOSEST, max_edit_distance=max_edit_distance)

        if suggestions and suggestions[0].distance > 0:
            # Found a correction with actual distance
            corrected_words.append(suggestions[0].term)
            was_corrected = True
            logger.debug(f"Typo corrected: '{word}' -> '{suggestions[0].term}'")
        else:
            corrected_words.append(word)

    return " ".join(corrected_words), was_corrected


def suggest_correction(text: str) -> Optional[str]:
    """
    Get correction suggestion for display to user.

    Returns None if no correction needed.
    """
    corrected, was_corrected = correct_typos(text)
    return corrected if was_corrected else None


@lru_cache(maxsize=1000)
def correct_typos_cached(text: str) -> Tuple[str, bool]:
    """
    Cached version of correct_typos for frequently used queries.

    Args:
        text: Input text to correct

    Returns:
        Tuple of (corrected_text, was_corrected)
    """
    return correct_typos(text)
