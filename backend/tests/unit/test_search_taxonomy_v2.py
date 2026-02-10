# backend/tests/unit/test_search_taxonomy_v2.py
"""
Unit tests for search keyword dictionaries aligned to taxonomy v2.

Tests verify that CATEGORY_KEYWORDS, SUBCATEGORY_KEYWORDS, and SERVICE_KEYWORDS
in patterns.py are consistent with the canonical seed data in seed_taxonomy.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re

import pytest

from app.services.search.patterns import (
    CATEGORY_KEYWORDS,
    SERVICE_KEYWORDS,
    SUBCATEGORY_KEYWORDS,
)

# Import canonical seed data via importlib (scripts/ is not a Python package)
_seed_path = Path(__file__).parent.parent.parent / "scripts" / "seed_data" / "seed_taxonomy.py"
_spec = importlib.util.spec_from_file_location("seed_taxonomy", _seed_path)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
CATEGORIES: list[dict[str, object]] = _mod.CATEGORIES
TAXONOMY: dict[str, list[tuple[str, int, list[str]]]] = _mod.TAXONOMY


# ════════════════════════════════════════════════════════════════════
# Helpers — derive sets of valid names from seed_taxonomy.py
# ════════════════════════════════════════════════════════════════════

SEED_CATEGORY_NAMES = {c["name"] for c in CATEGORIES}

SEED_SUBCATEGORY_NAMES: set[str] = set()
SEED_SERVICE_NAMES: set[str] = set()
SEED_SUBCATEGORY_TO_CATEGORY: dict[str, str] = {}

for _cat_name, _subcats in TAXONOMY.items():
    for _sub_name, _order, _services in _subcats:
        SEED_SUBCATEGORY_NAMES.add(_sub_name)
        SEED_SUBCATEGORY_TO_CATEGORY[_sub_name] = _cat_name
        for _svc in _services:
            SEED_SERVICE_NAMES.add(_svc)


# ════════════════════════════════════════════════════════════════════
# TestCategoryKeywordCoverage
# ════════════════════════════════════════════════════════════════════


class TestCategoryKeywordCoverage:
    """Every category keyword value must be a real category name."""

    def test_all_values_are_valid_categories(self) -> None:
        invalid = {v for v in CATEGORY_KEYWORDS.values() if v not in SEED_CATEGORY_NAMES}
        assert invalid == set(), f"Phantom categories in CATEGORY_KEYWORDS: {invalid}"

    def test_every_category_has_at_least_one_keyword(self) -> None:
        covered = set(CATEGORY_KEYWORDS.values())
        missing = SEED_CATEGORY_NAMES - covered
        assert missing == set(), f"Categories with zero keywords: {missing}"

    def test_keyword_keys_are_lowercase(self) -> None:
        bad = [k for k in CATEGORY_KEYWORDS if k != k.lower()]
        assert bad == [], f"Non-lowercase keys: {bad}"


# ════════════════════════════════════════════════════════════════════
# TestSubcategoryKeywordCoverage
# ════════════════════════════════════════════════════════════════════


class TestSubcategoryKeywordCoverage:
    """Every subcategory keyword value must be a real subcategory name."""

    def test_all_values_are_valid_subcategories(self) -> None:
        invalid = {v for v in SUBCATEGORY_KEYWORDS.values() if v not in SEED_SUBCATEGORY_NAMES}
        assert invalid == set(), f"Phantom subcategories in SUBCATEGORY_KEYWORDS: {invalid}"

    def test_high_traffic_subcategories_have_keywords(self) -> None:
        """At least the most popular subcategories should have keyword coverage."""
        must_cover = {
            "Math",
            "Test Prep",
            "Reading",
            "English",
            "Science",
            "Coding & STEM",
            "Piano",
            "Guitar",
            "Voice & Singing",
            "Violin",
            "Drums & Percussion",
            "Ballet",
            "Hip Hop",
            "Ballroom & Latin",
            "Spanish",
            "French",
            "Chinese",
            "Sign Language",
            "English (ESL/EFL)",
            "Swimming",
            "Martial Arts",
            "Tennis",
            "Yoga & Pilates",
            "Personal Training",
            "Chess",
            "Drawing",
            "Painting",
            "Photography",
            "Acting",
            "Graphic Design",
            "Food & Drink",
            "Mindfulness & Wellness",
        }
        covered = set(SUBCATEGORY_KEYWORDS.values())
        missing = must_cover - covered
        assert missing == set(), f"High-traffic subcategories missing keywords: {missing}"

    def test_keyword_keys_are_lowercase(self) -> None:
        bad = [k for k in SUBCATEGORY_KEYWORDS if k != k.lower()]
        assert bad == [], f"Non-lowercase keys: {bad}"


# ════════════════════════════════════════════════════════════════════
# TestServiceKeywordCoverage
# ════════════════════════════════════════════════════════════════════


class TestServiceKeywordCoverage:
    """Every service keyword value must be a real service name from seed."""

    def test_all_values_are_valid_services(self) -> None:
        invalid = {v for v in SERVICE_KEYWORDS.values() if v not in SEED_SERVICE_NAMES}
        assert invalid == set(), f"Phantom services in SERVICE_KEYWORDS: {invalid}"

    def test_high_traffic_services_have_keywords(self) -> None:
        """Key services that users frequently search for must be covered."""
        must_cover = {
            "SAT",
            "ACT",
            "Piano",
            "Guitar",
            "Violin",
            "Drums & Percussion",
            "Ballet",
            "Salsa",
            "Karate",
            "Jiu-Jitsu",
            "Tennis",
            "Swimming",
            "Yoga",
            "Chess",
            "Spanish",
            "French",
            "Mandarin",
            "Photography",
            "Pottery",
            "Sign Language",
            "Algebra",
            "Biology",
            "Python",
        }
        covered = set(SERVICE_KEYWORDS.values())
        missing = must_cover - covered
        assert missing == set(), f"High-traffic services missing keywords: {missing}"

    def test_keyword_keys_are_lowercase(self) -> None:
        bad = [k for k in SERVICE_KEYWORDS if k != k.lower()]
        assert bad == [], f"Non-lowercase keys: {bad}"

    def test_test_prep_services_use_correct_names(self) -> None:
        """Test prep services should be 'SAT' not 'SAT Prep' etc."""
        test_prep_keywords = ["sat", "act", "gre", "gmat", "lsat", "mcat"]
        for kw in test_prep_keywords:
            svc_name = SERVICE_KEYWORDS.get(kw)
            assert svc_name is not None, f"Missing service keyword: {kw}"
            assert "Prep" not in svc_name, (
                f"Service '{svc_name}' for keyword '{kw}' should not contain "
                f"'Prep' - seed uses bare exam name"
            )

    def test_martial_arts_jiu_jitsu_name(self) -> None:
        """Jiu-Jitsu should be 'Jiu-Jitsu' not 'Brazilian Jiu-Jitsu'."""
        for kw in ("bjj", "jiu jitsu", "jiu-jitsu"):
            assert SERVICE_KEYWORDS[kw] == "Jiu-Jitsu"


# ════════════════════════════════════════════════════════════════════
# TestCrossDictConsistency
# ════════════════════════════════════════════════════════════════════


class TestCrossDictConsistency:
    """Keywords in multiple dicts should have consistent hierarchy."""

    def test_service_keywords_category_consistency(self) -> None:
        """If a keyword is in both SERVICE and CATEGORY, the category should
        be the parent of the service's subcategory."""
        for kw, svc_name in SERVICE_KEYWORDS.items():
            cat_name = CATEGORY_KEYWORDS.get(kw)
            if cat_name is None:
                continue
            for cat, subcats in TAXONOMY.items():
                for _sub_name, _order, services in subcats:
                    if svc_name in services:
                        assert cat_name == cat, (
                            f"Keyword '{kw}' maps to service '{svc_name}' in "
                            f"category '{cat}', but CATEGORY_KEYWORDS maps to "
                            f"'{cat_name}'"
                        )

    def test_subcategory_keywords_category_consistency(self) -> None:
        """If a keyword is in both SUBCATEGORY and CATEGORY, the category
        should be the parent of the subcategory."""
        for kw, sub_name in SUBCATEGORY_KEYWORDS.items():
            cat_name = CATEGORY_KEYWORDS.get(kw)
            if cat_name is None:
                continue
            expected_cat = SEED_SUBCATEGORY_TO_CATEGORY.get(sub_name)
            if expected_cat:
                assert cat_name == expected_cat, (
                    f"Keyword '{kw}' maps to subcategory '{sub_name}' in "
                    f"category '{expected_cat}', but CATEGORY_KEYWORDS maps "
                    f"to '{cat_name}'"
                )


# ════════════════════════════════════════════════════════════════════
# TestTaxonomyDetection — representative queries
# ════════════════════════════════════════════════════════════════════


class TestTaxonomyDetection:
    """Test that keyword lookup resolves queries to correct hints."""

    @staticmethod
    def _detect(query: str) -> dict[str, str | None]:
        """Run keyword detection against a query string (mirrors _detect_taxonomy)."""
        q = query.lower()

        def _contains_keyword(text: str, keyword: str) -> bool:
            return re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE) is not None

        result: dict[str, str | None] = {
            "category_hint": None,
            "subcategory_hint": None,
            "service_hint": None,
        }
        # Most-specific-first: SERVICE -> SUBCATEGORY -> CATEGORY
        for kw, svc in sorted(SERVICE_KEYWORDS.items(), key=lambda x: -len(x[0])):
            if _contains_keyword(q, kw):
                result["service_hint"] = svc
                break
        for kw, sub in sorted(SUBCATEGORY_KEYWORDS.items(), key=lambda x: -len(x[0])):
            if _contains_keyword(q, kw):
                result["subcategory_hint"] = sub
                break
        for kw, cat in sorted(CATEGORY_KEYWORDS.items(), key=lambda x: -len(x[0])):
            if _contains_keyword(q, kw):
                result["category_hint"] = cat
                break
        return result

    @pytest.mark.parametrize(
        "query,expected_service,expected_subcategory,expected_category",
        [
            ("piano lessons", "Piano", "Piano", "Music"),
            ("sat tutor", "SAT", "Test Prep", "Tutoring & Test Prep"),
            ("karate for kids", "Karate", "Martial Arts", "Sports & Fitness"),
            ("salsa dancing", "Salsa", "Ballroom & Latin", "Dance"),
            ("spanish lessons", "Spanish", "Spanish", "Languages"),
            ("yoga near me", "Yoga", "Yoga & Pilates", "Sports & Fitness"),
            ("chess lessons", "Chess", "Chess", "Sports & Fitness"),
            ("drums teacher", "Drums & Percussion", "Drums & Percussion", "Music"),
            ("photography class", "Photography", "Photography", "Arts"),
            ("jiu-jitsu", "Jiu-Jitsu", "Martial Arts", "Sports & Fitness"),
            ("baking class", "Baking", "Food & Drink", "Hobbies & Life Skills"),
            (
                "sign language tutor",
                "Sign Language",
                "Sign Language",
                "Languages",
            ),
            ("zumba class", "Zumba", "Dance Fitness", "Dance"),
            (
                "pickleball lessons",
                "Pickleball",
                "Pickleball",
                "Sports & Fitness",
            ),
            ("krav maga", "Krav Maga", "Martial Arts", "Sports & Fitness"),
        ],
    )
    def test_keyword_detection(
        self,
        query: str,
        expected_service: str | None,
        expected_subcategory: str | None,
        expected_category: str | None,
    ) -> None:
        result = self._detect(query)
        assert result["service_hint"] == expected_service, (
            f"Query '{query}': expected service '{expected_service}', "
            f"got '{result['service_hint']}'"
        )
        assert result["subcategory_hint"] == expected_subcategory, (
            f"Query '{query}': expected subcategory '{expected_subcategory}', "
            f"got '{result['subcategory_hint']}'"
        )
        assert result["category_hint"] == expected_category, (
            f"Query '{query}': expected category '{expected_category}', "
            f"got '{result['category_hint']}'"
        )

    @pytest.mark.parametrize(
        "query,unexpected_hint_type,unexpected_value",
        [
            ("starting point for lessons", "category_hint", "Arts"),
            ("satisfaction guaranteed tutoring", "service_hint", "SAT"),
        ],
    )
    def test_detection_uses_word_boundaries(
        self,
        query: str,
        unexpected_hint_type: str,
        unexpected_value: str,
    ) -> None:
        result = self._detect(query)
        assert result[unexpected_hint_type] != unexpected_value
