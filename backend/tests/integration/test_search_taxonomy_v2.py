# backend/tests/integration/test_search_taxonomy_v2.py
"""
Integration tests for search keyword dictionaries against seeded INT database.

Verifies that SUBCATEGORY_KEYWORDS and SERVICE_KEYWORDS values match actual
database rows inserted by seed_taxonomy.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.services.search.patterns import (
    CATEGORY_KEYWORDS,
    SERVICE_KEYWORDS,
    SUBCATEGORY_KEYWORDS,
)


@pytest.mark.integration
class TestKeywordSeedAlignment:
    """All keyword dict values must exist as actual DB rows."""

    def test_all_subcategory_keyword_values_exist_in_db(self, db: Session) -> None:
        """Every SUBCATEGORY_KEYWORDS value must be a real subcategory name."""
        db_names = {
            row[0]
            for row in db.query(ServiceSubcategory.name)
            .filter(ServiceSubcategory.is_active.is_(True))
            .all()
        }
        keyword_values = set(SUBCATEGORY_KEYWORDS.values())
        missing = keyword_values - db_names
        assert missing == set(), (
            f"SUBCATEGORY_KEYWORDS values not found in DB: {missing}"
        )

    def test_all_service_keyword_values_exist_in_db(self, db: Session) -> None:
        """Every SERVICE_KEYWORDS value must be a real service_catalog name."""
        db_names = {
            row[0]
            for row in db.query(ServiceCatalog.name)
            .filter(ServiceCatalog.is_active.is_(True))
            .all()
        }
        keyword_values = set(SERVICE_KEYWORDS.values())
        missing = keyword_values - db_names
        assert missing == set(), (
            f"SERVICE_KEYWORDS values not found in DB: {missing}"
        )

    def test_all_category_keyword_values_exist_in_db(self, db: Session) -> None:
        """Every CATEGORY_KEYWORDS value must be a real category name."""
        db_names = {
            row[0] for row in db.query(ServiceCategory.name).all()
        }
        keyword_values = set(CATEGORY_KEYWORDS.values())
        missing = keyword_values - db_names
        assert missing == set(), (
            f"CATEGORY_KEYWORDS values not found in DB: {missing}"
        )


@pytest.mark.integration
class TestSeededTaxonomyHierarchy:
    """Verify keyword hierarchy consistency against actual DB relationships."""

    def test_subcategory_to_category_mapping(self, db: Session) -> None:
        """Subcategory keyword values should belong to the category that
        the corresponding CATEGORY_KEYWORDS entry points to."""
        # Build DB lookup: subcategory_name -> category_name
        rows = (
            db.query(ServiceSubcategory.name, ServiceCategory.name)
            .join(
                ServiceCategory,
                ServiceSubcategory.category_id == ServiceCategory.id,
            )
            .all()
        )
        sub_to_cat: dict[str, str] = {sub_name: cat_name for sub_name, cat_name in rows}

        mismatches = []
        for kw, sub_name in SUBCATEGORY_KEYWORDS.items():
            cat_from_kw = CATEGORY_KEYWORDS.get(kw)
            if cat_from_kw is None:
                continue
            cat_from_db = sub_to_cat.get(sub_name)
            if cat_from_db and cat_from_kw != cat_from_db:
                mismatches.append(
                    f"'{kw}': subcategory '{sub_name}' is in DB category "
                    f"'{cat_from_db}', but CATEGORY_KEYWORDS says '{cat_from_kw}'"
                )
        assert mismatches == [], (
            "Hierarchy mismatches:\n" + "\n".join(mismatches)
        )

    def test_service_to_category_mapping(self, db: Session) -> None:
        """Service keyword values should belong to the category that
        the corresponding CATEGORY_KEYWORDS entry points to."""
        # Build DB lookup: service_name -> category_name
        rows = (
            db.query(ServiceCatalog.name, ServiceCategory.name)
            .join(
                ServiceSubcategory,
                ServiceCatalog.subcategory_id == ServiceSubcategory.id,
            )
            .join(
                ServiceCategory,
                ServiceSubcategory.category_id == ServiceCategory.id,
            )
            .all()
        )
        svc_to_cat: dict[str, str] = {svc_name: cat_name for svc_name, cat_name in rows}

        mismatches = []
        for kw, svc_name in SERVICE_KEYWORDS.items():
            cat_from_kw = CATEGORY_KEYWORDS.get(kw)
            if cat_from_kw is None:
                continue
            cat_from_db = svc_to_cat.get(svc_name)
            if cat_from_db and cat_from_kw != cat_from_db:
                mismatches.append(
                    f"'{kw}': service '{svc_name}' is in DB category "
                    f"'{cat_from_db}', but CATEGORY_KEYWORDS says '{cat_from_kw}'"
                )
        assert mismatches == [], (
            "Hierarchy mismatches:\n" + "\n".join(mismatches)
        )


@pytest.mark.integration
class TestEndToEndParsing:
    """Test QueryParser.parse() returns correct 3-level hints with seeded data."""

    @staticmethod
    def _parse(db: Session, query: str) -> object:
        from app.services.search.query_parser import QueryParser

        parser = QueryParser(db, user_id=None, region_code="nyc")
        return parser.parse(query)

    def test_piano_lessons_hints(self, db: Session) -> None:
        result = self._parse(db, "piano lessons in brooklyn")
        assert result.category_hint == "Music"
        assert result.subcategory_hint == "Piano"
        assert result.service_hint == "Piano"

    def test_sat_tutor_hints(self, db: Session) -> None:
        result = self._parse(db, "sat tutor")
        assert result.category_hint == "Tutoring & Test Prep"
        assert result.subcategory_hint == "Test Prep"
        assert result.service_hint == "SAT"

    def test_karate_for_kids_hints(self, db: Session) -> None:
        result = self._parse(db, "karate for kids")
        assert result.category_hint == "Sports & Fitness"
        assert result.subcategory_hint == "Martial Arts"
        assert result.service_hint == "Karate"

    def test_chess_lessons_category(self, db: Session) -> None:
        """Chess should be under Sports & Fitness, not Hobbies."""
        result = self._parse(db, "chess lessons")
        assert result.category_hint == "Sports & Fitness"
        assert result.subcategory_hint == "Chess"

    def test_salsa_dance_hints(self, db: Session) -> None:
        result = self._parse(db, "salsa dancing near me")
        assert result.category_hint == "Dance"
        assert result.subcategory_hint == "Ballroom & Latin"
        assert result.service_hint == "Salsa"

    def test_jiu_jitsu_correct_name(self, db: Session) -> None:
        """Should resolve to 'Jiu-Jitsu' not 'Brazilian Jiu-Jitsu'."""
        result = self._parse(db, "bjj classes")
        assert result.service_hint == "Jiu-Jitsu"

    def test_sign_language_hints(self, db: Session) -> None:
        result = self._parse(db, "sign language lessons")
        assert result.category_hint == "Languages"
        assert result.subcategory_hint == "Sign Language"
        assert result.service_hint == "Sign Language"

    def test_drums_correct_name(self, db: Session) -> None:
        """Should resolve to 'Drums & Percussion' not 'Drums'."""
        result = self._parse(db, "drums lessons")
        assert result.service_hint == "Drums & Percussion"
