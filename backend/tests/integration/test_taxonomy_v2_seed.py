# backend/tests/integration/test_taxonomy_v2_seed.py
"""
Integration tests for the 3-level taxonomy seed script.

Verifies that seed_taxonomy.py populates the correct data:
- 7 categories with slugs/meta
- 77 subcategories with slugs
- 224 services with age groups
- 9 filter definitions, ~70 filter options
- Subcategory-filter junction mappings
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory

# ── Helpers ────────────────────────────────────────────────────


def _load_seeder():
    """Import seed_taxonomy via importlib (scripts/seed_data/ has no __init__.py)."""
    import importlib.util
    import os

    # __file__ is tests/integration/test_*.py → go up 3 levels to backend/
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "seed_taxonomy",
        os.path.join(backend_dir, "scripts", "seed_data", "seed_taxonomy.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.seed_taxonomy


def _seed_once(db: Session) -> None:
    """Run the taxonomy seeder if data is missing."""
    count = db.execute(text("SELECT count(*) FROM service_categories")).scalar()
    if count == 7:
        # Check it's the *new* taxonomy (has slugs)
        has_slugs = db.execute(
            text("SELECT count(*) FROM service_categories WHERE slug IS NOT NULL")
        ).scalar()
        if has_slugs == 7:
            return  # Already seeded with full taxonomy

    # Need to seed — close ORM session, run seeder with its own connection
    db_url = str(db.bind.url)
    db.close()

    seed_taxonomy = _load_seeder()
    seed_taxonomy(db_url=db_url, verbose=False)


# ── 1. Row Counts ────────────────────────────────────────────


class TestRowCounts:
    def test_category_count(self, db: Session):
        _seed_once(db)
        assert db.query(ServiceCategory).count() == 7

    def test_subcategory_count(self, db: Session):
        _seed_once(db)
        assert db.query(ServiceSubcategory).count() == 77

    def test_service_count(self, db: Session):
        _seed_once(db)
        assert db.query(ServiceCatalog).count() == 224

    def test_filter_definition_count(self, db: Session):
        _seed_once(db)
        assert db.query(FilterDefinition).count() == 9

    def test_filter_option_count(self, db: Session):
        _seed_once(db)
        # 6 + 4 + 17 + 7 + 9 + 5 + 8 + 5 + 3 = 64
        count = db.query(FilterOption).count()
        assert count >= 60, f"Expected >=60 filter options, got {count}"


# ── 2. Category Slugs & Meta ─────────────────────────────────


class TestCategorySlugs:
    def test_all_categories_have_slugs(self, db: Session):
        _seed_once(db)
        cats = db.query(ServiceCategory).all()
        for cat in cats:
            assert cat.slug is not None, f"Category '{cat.name}' missing slug"

    def test_known_category_slugs(self, db: Session):
        _seed_once(db)
        expected = {
            "Tutoring & Test Prep": "tutoring",
            "Music": "music",
            "Dance": "dance",
            "Languages": "languages",
            "Sports & Fitness": "sports",
            "Arts": "arts",
            "Hobbies & Life Skills": "hobbies",
        }
        for name, slug in expected.items():
            cat = db.query(ServiceCategory).filter_by(name=name).one()
            assert cat.slug == slug, f"Category '{name}' slug: {cat.slug} != {slug}"

    def test_categories_have_meta_title(self, db: Session):
        _seed_once(db)
        cats = db.query(ServiceCategory).all()
        for cat in cats:
            assert cat.meta_title is not None, f"Category '{cat.name}' missing meta_title"
            assert "InstaInstru" in cat.meta_title


# ── 3. Subcategory Slugs ─────────────────────────────────────


class TestSubcategorySlugs:
    def test_all_subcategories_have_slugs(self, db: Session):
        _seed_once(db)
        subs = db.query(ServiceSubcategory).all()
        for sub in subs:
            assert sub.slug is not None, f"Subcategory '{sub.name}' missing slug"

    def test_piano_slug(self, db: Session):
        _seed_once(db)
        piano = db.query(ServiceSubcategory).filter_by(name="Piano").first()
        assert piano is not None
        assert piano.slug == "piano"


# ── 4. FK Chain Integrity ────────────────────────────────────


class TestFKChain:
    def test_piano_service_walks_to_music(self, db: Session):
        """Piano service → Piano subcategory → Music category."""
        _seed_once(db)
        svc = db.query(ServiceCatalog).filter_by(name="Piano").first()
        assert svc is not None
        sub = db.get(ServiceSubcategory,svc.subcategory_id)
        assert sub is not None
        assert sub.name == "Piano"
        cat = db.get(ServiceCategory,sub.category_id)
        assert cat is not None
        assert cat.name == "Music"

    def test_sat_walks_to_tutoring(self, db: Session):
        """SAT service → Test Prep subcategory → Tutoring & Test Prep category."""
        _seed_once(db)
        svc = db.query(ServiceCatalog).filter_by(name="SAT").first()
        assert svc is not None
        sub = db.get(ServiceSubcategory,svc.subcategory_id)
        assert sub.name == "Test Prep"
        cat = db.get(ServiceCategory,sub.category_id)
        assert cat.name == "Tutoring & Test Prep"

    def test_salsa_walks_to_dance(self, db: Session):
        """Salsa service → Ballroom & Latin subcategory → Dance category."""
        _seed_once(db)
        svc = db.query(ServiceCatalog).filter_by(name="Salsa").first()
        assert svc is not None
        sub = db.get(ServiceSubcategory,svc.subcategory_id)
        assert sub.name == "Ballroom & Latin"
        cat = db.get(ServiceCategory,sub.category_id)
        assert cat.name == "Dance"


# ── 5. Filter Mappings ───────────────────────────────────────


class TestFilterMappings:
    def test_math_has_four_filters(self, db: Session):
        """Math subcategory should have grade_level, course_level, goal, format."""
        _seed_once(db)
        math_sub = db.query(ServiceSubcategory).filter_by(name="Math").first()
        assert math_sub is not None

        sf_rows = (
            db.query(SubcategoryFilter)
            .filter_by(subcategory_id=math_sub.id)
            .all()
        )
        filter_keys = set()
        for sf in sf_rows:
            fd = db.get(FilterDefinition,sf.filter_definition_id)
            filter_keys.add(fd.key)

        assert filter_keys == {"grade_level", "course_level", "goal", "format"}

    def test_math_grade_level_has_all_options(self, db: Session):
        """Math's grade_level filter should have all 6 grade level options."""
        _seed_once(db)
        math_sub = db.query(ServiceSubcategory).filter_by(name="Math").first()
        grade_fd = db.query(FilterDefinition).filter_by(key="grade_level").first()

        sf = (
            db.query(SubcategoryFilter)
            .filter_by(subcategory_id=math_sub.id, filter_definition_id=grade_fd.id)
            .first()
        )
        assert sf is not None

        sfo_count = (
            db.query(SubcategoryFilterOption)
            .filter_by(subcategory_filter_id=sf.id)
            .count()
        )
        assert sfo_count == 6  # All grade levels


# ── 6. Music Has No Filters ──────────────────────────────────


class TestMusicNoFilters:
    def test_piano_subcategory_has_no_filters(self, db: Session):
        _seed_once(db)
        piano_sub = db.query(ServiceSubcategory).filter_by(name="Piano").first()
        assert piano_sub is not None

        sf_count = (
            db.query(SubcategoryFilter)
            .filter_by(subcategory_id=piano_sub.id)
            .count()
        )
        assert sf_count == 0, "Music subcategories should have no filter mappings"


# ── 7. Age Group Exceptions ──────────────────────────────────


class TestAgeGroups:
    def test_gre_adults_only(self, db: Session):
        _seed_once(db)
        gre = db.query(ServiceCatalog).filter_by(name="GRE").first()
        assert gre is not None
        assert sorted(gre.eligible_age_groups) == ["adults"]

    def test_sat_teens_adults(self, db: Session):
        _seed_once(db)
        sat = db.query(ServiceCatalog).filter_by(name="SAT").first()
        assert sat is not None
        assert sorted(sat.eligible_age_groups) == ["adults", "teens"]

    def test_piano_all_ages(self, db: Session):
        _seed_once(db)
        piano = db.query(ServiceCatalog).filter_by(name="Piano").first()
        assert piano is not None
        assert sorted(piano.eligible_age_groups) == ["adults", "kids", "teens", "toddler"]

    def test_isr_toddler_only(self, db: Session):
        _seed_once(db)
        isr = db.query(ServiceCatalog).filter_by(name="ISR (Infant Self-Rescue)").first()
        assert isr is not None
        assert sorted(isr.eligible_age_groups) == ["toddler"]


# ── 8. Idempotency ───────────────────────────────────────────


class TestIdempotency:
    def test_seed_twice_same_counts(self, db: Session):
        """Running seed twice should produce identical counts."""
        _seed_once(db)

        # Record counts
        cat_count_1 = db.query(ServiceCategory).count()
        sub_count_1 = db.query(ServiceSubcategory).count()
        svc_count_1 = db.query(ServiceCatalog).count()

        # Re-seed (force by running directly)
        db_url = str(db.bind.url)
        db.close()

        seed_taxonomy = _load_seeder()
        seed_taxonomy(db_url=db_url, verbose=False)

        # Reconnect and check
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SA_Session

        engine = create_engine(db_url)
        with SA_Session(engine) as session:
            assert session.query(ServiceCategory).count() == cat_count_1
            assert session.query(ServiceSubcategory).count() == sub_count_1
            assert session.query(ServiceCatalog).count() == svc_count_1


# ── 9. Subcategory Counts per Category ───────────────────────


class TestSubcategoryDistribution:
    def test_tutoring_has_10_subcategories(self, db: Session):
        _seed_once(db)
        cat = db.query(ServiceCategory).filter_by(name="Tutoring & Test Prep").first()
        count = db.query(ServiceSubcategory).filter_by(category_id=cat.id).count()
        assert count == 10

    def test_music_has_12_subcategories(self, db: Session):
        _seed_once(db)
        cat = db.query(ServiceCategory).filter_by(name="Music").first()
        count = db.query(ServiceSubcategory).filter_by(category_id=cat.id).count()
        assert count == 12

    def test_dance_has_9_subcategories(self, db: Session):
        _seed_once(db)
        cat = db.query(ServiceCategory).filter_by(name="Dance").first()
        count = db.query(ServiceSubcategory).filter_by(category_id=cat.id).count()
        assert count == 9
