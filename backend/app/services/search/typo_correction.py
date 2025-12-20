"""
Lightweight SymSpell-based typo correction for search queries.

Key constraints:
- Use a small domain-specific dictionary to keep memory low.
- Load at module import time so Gunicorn `preload_app=True` can share pages via COW.
"""

from __future__ import annotations

from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import re
from typing import Optional, Tuple

from symspellpy import SymSpell, Verbosity

logger = logging.getLogger(__name__)

# Optimized settings:
# - Edit distance 1 catches the majority of real-world typos with far less memory than ED=2.
# - Smaller prefix further reduces SymSpell delete-table size.
MAX_EDIT_DISTANCE = 1
PREFIX_LENGTH = 5

# Dictionary path (repo file, not symspellpy's full English dictionary).
DOMAIN_DICTIONARY_PATH = Path(__file__).resolve().parents[3] / "data" / "domain_dictionary.txt"

# Location aliases (single-token) used to protect abbreviations like "ues" and "lic"
# from being "corrected" into unrelated common words.
LOCATION_ALIASES_JSON_PATH = Path(__file__).resolve().parents[3] / "data" / "location_aliases.json"


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

# Pattern to match time tokens like "5pm", "10am", "3:00pm"
TIME_TOKEN_PATTERN = re.compile(r"^\d{1,2}(:\d{2})?(am|pm)$", re.IGNORECASE)

# Strip leading/trailing punctuation for protected-token checks, while keeping inner punctuation.
TOKEN_STRIP_PATTERN = re.compile(r"^[^a-z0-9]+|[^a-z0-9]+$", re.IGNORECASE)


@lru_cache(maxsize=1)
def load_location_alias_tokens() -> frozenset[str]:
    """
    Load single-token location alias strings from `backend/data/location_aliases.json`.

    Used to keep typo-correction protections DRY with the alias seeding source-of-truth.
    """

    try:
        payload = json.loads(LOCATION_ALIASES_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning(
            "location_aliases.json not found at %s; using fallback protected tokens only",
            str(LOCATION_ALIASES_JSON_PATH),
        )
        return frozenset()
    except Exception as exc:
        logger.warning(
            "Failed to load location_aliases.json at %s (%s); using fallback protected tokens only",
            str(LOCATION_ALIASES_JSON_PATH),
            exc,
        )
        return frozenset()

    aliases = payload.get("aliases") or []
    ambiguous_aliases = payload.get("ambiguous_aliases") or []
    if not isinstance(aliases, list) or not isinstance(ambiguous_aliases, list):
        return frozenset()

    tokens: set[str] = set()
    for row in list(aliases) + list(ambiguous_aliases):
        if not isinstance(row, dict):
            continue
        alias = row.get("alias")
        if not alias:
            continue
        normalized = " ".join(str(alias).strip().lower().split())
        if not normalized or " " in normalized:
            continue
        tokens.add(normalized)

    return frozenset(tokens)


FALLBACK_PROTECTED_TOKENS = frozenset({"nyc"})
PROTECTED_TOKENS = load_location_alias_tokens() | FALLBACK_PROTECTED_TOKENS


def _load_fallback_dictionary(sym: SymSpell) -> None:
    # Minimal vocabulary for resiliency if the file isn't present for some reason.
    fallback = [
        ("piano", 1_000_000),
        ("guitar", 1_000_000),
        ("violin", 900_000),
        ("lessons", 1_000_000),
        ("lesson", 900_000),
        ("tutor", 900_000),
        ("tutoring", 800_000),
        ("math", 1_000_000),
        ("swimming", 800_000),
        ("brooklyn", 900_000),
        ("manhattan", 900_000),
    ]
    for term, freq in fallback:
        sym.create_dictionary_entry(term, freq)


def _initialize_symspell() -> Optional[SymSpell]:
    sym = SymSpell(max_dictionary_edit_distance=MAX_EDIT_DISTANCE, prefix_length=PREFIX_LENGTH)

    try:
        if DOMAIN_DICTIONARY_PATH.exists():
            sym.load_dictionary(
                str(DOMAIN_DICTIONARY_PATH),
                term_index=0,
                count_index=1,
                separator=" ",
            )
            logger.info(
                "[SEARCH] Loaded SymSpell domain dictionary (%d words, ED=%d, prefix=%d) from %s",
                len(sym.words),
                MAX_EDIT_DISTANCE,
                PREFIX_LENGTH,
                str(DOMAIN_DICTIONARY_PATH),
            )
        else:
            logger.warning(
                "[SEARCH] Domain dictionary not found at %s; using fallback vocabulary",
                str(DOMAIN_DICTIONARY_PATH),
            )
            _load_fallback_dictionary(sym)
    except Exception as exc:
        logger.warning("[SEARCH] Failed to load SymSpell domain dictionary: %s", exc)
        try:
            _load_fallback_dictionary(sym)
        except Exception:
            return None

    return sym


# -----------------------------------------------------------------------------
# CRITICAL: Load at module import time for copy-on-write sharing.
# This runs once in the Gunicorn master process when `preload_app=True`.
# -----------------------------------------------------------------------------
_symspell: Optional[SymSpell] = None
if os.getenv("PYTEST_CURRENT_TEST") is None:
    _symspell = _initialize_symspell()


def get_symspell() -> Optional[SymSpell]:
    """Return SymSpell instance (lazy-init if skipped at import time)."""
    global _symspell
    if _symspell is None:
        _symspell = _initialize_symspell()
    return _symspell


def correct_typos(text: str, max_edit_distance: int = MAX_EDIT_DISTANCE) -> Tuple[str, bool]:
    """
    Correct typos in search text.

    Returns:
        Tuple of (corrected_text, was_corrected)
    """
    if not text or not text.strip():
        return text, False

    sym = get_symspell()
    if sym is None:
        return text, False

    max_edit_distance = max(0, min(int(max_edit_distance), MAX_EDIT_DISTANCE))

    words = text.lower().split()
    corrected_words: list[str] = []
    was_corrected = False

    for word in words:
        core = TOKEN_STRIP_PATTERN.sub("", word)
        if core in PROTECTED_TOKENS:
            corrected_words.append(core)
            continue

        # Skip short words, numbers, and special tokens.
        # Domain dictionaries are intentionally small, so correcting very short tokens (3 chars)
        # is more likely to corrupt meaningful abbreviations ("wed" -> "web", "act" -> "art", etc.).
        if len(word) <= 3 or word.isdigit() or word.startswith("$"):
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

        suggestions = sym.lookup(word, Verbosity.CLOSEST, max_edit_distance=max_edit_distance)
        if suggestions and suggestions[0].distance > 0:
            corrected_words.append(suggestions[0].term)
            was_corrected = True
        else:
            corrected_words.append(word)

    return " ".join(corrected_words), was_corrected


def suggest_correction(text: str) -> Optional[str]:
    """Return suggested corrected query (or None if no correction applied)."""
    corrected, was_corrected = correct_typos(text)
    return corrected if was_corrected else None


@lru_cache(maxsize=1000)
def correct_typos_cached(text: str) -> Tuple[str, bool]:
    """Cached version of correct_typos for frequently used queries."""
    return correct_typos(text)
