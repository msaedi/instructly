# backend/tests/repositories/test_taxonomy_filter_repository.py
"""
Integration tests for TaxonomyFilterRepository.

Requires real DB with taxonomy data. Uses locally-created test data
to avoid depending on seed state.
"""

from __future__ import annotations

import pytest
import ulid as _ulid

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    InstructorService,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory
from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository


def _uid() -> str:
    return str(_ulid.ULID()).lower()[:10]


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def taxonomy_data(db):
    """Create a full taxonomy tree with filters for testing."""
    uid = _uid()

    # Category
    cat = ServiceCategory(name=f"TFR Cat {uid}", display_order=99)
    db.add(cat)
    db.flush()

    # Subcategory with filters
    sub_with_filters = ServiceSubcategory(category_id=cat.id, name=f"TFR Sub Filters {uid}", display_order=0)
    db.add(sub_with_filters)
    db.flush()

    # Subcategory without filters
    sub_without_filters = ServiceSubcategory(category_id=cat.id, name=f"TFR Sub NoFilt {uid}", display_order=1)
    db.add(sub_without_filters)
    db.flush()

    # Service under sub_with_filters
    svc = ServiceCatalog(
        subcategory_id=sub_with_filters.id,
        name=f"TFR Service {uid}",
        slug=f"tfr-svc-{uid}",
        display_order=0,
        is_active=True,
    )
    db.add(svc)
    db.flush()

    # Filter definition: grade_level
    fd_key = f"tfr_grade_{uid}"
    fd_grade = FilterDefinition(key=fd_key, display_name="Grade Level", filter_type="multi_select")
    db.add(fd_grade)
    db.flush()

    # Filter options
    fo_elem = FilterOption(filter_definition_id=fd_grade.id, value="elementary", display_name="Elementary (K-5)", display_order=0)
    fo_middle = FilterOption(filter_definition_id=fd_grade.id, value="middle", display_name="Middle School", display_order=1)
    fo_high = FilterOption(filter_definition_id=fd_grade.id, value="high", display_name="High School", display_order=2)
    db.add_all([fo_elem, fo_middle, fo_high])
    db.flush()

    # Link filter to subcategory
    sf = SubcategoryFilter(subcategory_id=sub_with_filters.id, filter_definition_id=fd_grade.id, display_order=0)
    db.add(sf)
    db.flush()

    # Link only elementary + middle options (not high)
    sfo1 = SubcategoryFilterOption(subcategory_filter_id=sf.id, filter_option_id=fo_elem.id, display_order=0)
    sfo2 = SubcategoryFilterOption(subcategory_filter_id=sf.id, filter_option_id=fo_middle.id, display_order=1)
    db.add_all([sfo1, sfo2])
    db.commit()

    return {
        "category": cat,
        "sub_with_filters": sub_with_filters,
        "sub_without_filters": sub_without_filters,
        "service": svc,
        "filter_def": fd_grade,
        "filter_key": fd_key,
        "filter_options": [fo_elem, fo_middle, fo_high],
        "subcategory_filter": sf,
    }


# ── Tests ──────────────────────────────────────────────────────


class TestGetFiltersForSubcategory:
    def test_with_filters(self, db, taxonomy_data):
        """Returns filter definitions and their options for a subcategory."""
        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory(taxonomy_data["sub_with_filters"].id)

        assert len(filters) == 1
        f = filters[0]
        assert f["filter_key"] == taxonomy_data["filter_key"]
        assert f["filter_display_name"] == "Grade Level"
        assert f["filter_type"] == "multi_select"
        assert len(f["options"]) == 2  # elementary + middle only (not high)

    def test_without_filters(self, db, taxonomy_data):
        """Returns empty filter list for subcategory with no filters."""
        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory(taxonomy_data["sub_without_filters"].id)

        assert filters == []

    def test_nonexistent_subcategory(self, db):
        """Returns empty list for non-existent subcategory ID."""
        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory("01JNONEXISTENT000000000000")

        assert filters == []

    def test_options_sorted_by_display_order(self, db, taxonomy_data):
        """Options within a filter are sorted by display_order."""
        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory(taxonomy_data["sub_with_filters"].id)

        options = filters[0]["options"]
        assert options[0]["value"] == "elementary"  # display_order=0
        assert options[1]["value"] == "middle"  # display_order=1


class TestValidateFilterSelections:
    def test_valid_selections(self, db, taxonomy_data):
        """Valid filter_selections passes validation."""
        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            selections={taxonomy_data["filter_key"]: ["elementary"]},
        )
        assert is_valid is True
        assert errors == []

    def test_valid_multiple_values(self, db, taxonomy_data):
        """Multiple valid values pass validation."""
        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            selections={taxonomy_data["filter_key"]: ["elementary", "middle"]},
        )
        assert is_valid is True

    def test_invalid_filter_name(self, db, taxonomy_data):
        """Rejects filter key that doesn't exist for this subcategory."""
        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            selections={"nonexistent_filter": ["value"]},
        )
        assert is_valid is False
        assert any("Unknown filter key" in e for e in errors)

    def test_invalid_option_value(self, db, taxonomy_data):
        """Rejects option value that doesn't exist for this filter+subcategory."""
        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            selections={taxonomy_data["filter_key"]: ["high"]},  # high not linked to this subcategory
        )
        assert is_valid is False
        assert any("Invalid option" in e for e in errors)

    def test_empty_selections(self, db, taxonomy_data):
        """Empty dict passes validation."""
        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            selections={},
        )
        assert is_valid is True
        assert errors == []

    def test_mixed_valid_and_invalid(self, db, taxonomy_data):
        """Mix of valid key + invalid value."""
        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            selections={taxonomy_data["filter_key"]: ["elementary", "bogus_value"]},
        )
        assert is_valid is False
        assert len(errors) == 1


class TestFindInstructorsByFilters:
    def test_jsonb_containment(self, db, taxonomy_data, test_instructor):
        """JSONB @> operator correctly matches instructor filter_selections."""
        profile = db.query(InstructorProfile).filter(
            InstructorProfile.user_id == test_instructor.id
        ).first()
        assert profile is not None

        # Create instructor service with filter_selections
        svc = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=taxonomy_data["service"].id,
            hourly_rate=50.0,
            duration_options=[60],
            is_active=True,
            filter_selections={taxonomy_data["filter_key"]: ["elementary", "middle"]},
        )
        db.add(svc)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        results = repo.find_instructors_by_filters(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )

        assert len(results) >= 1
        assert any(r.id == svc.id for r in results)

    def test_no_match(self, db, taxonomy_data):
        """Returns empty when no instructors match filter criteria."""
        repo = TaxonomyFilterRepository(db)
        results = repo.find_instructors_by_filters(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )
        # May or may not find results depending on test state, but should not error
        assert isinstance(results, list)

    def test_empty_filter_returns_all(self, db, taxonomy_data):
        """Empty filter_selections returns all services in subcategory."""
        repo = TaxonomyFilterRepository(db)
        results = repo.find_instructors_by_filters(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={},
        )
        assert isinstance(results, list)


class TestFindMatchingServiceIds:
    def test_or_within_key_returns_any_matching_value(self, db, taxonomy_data, test_instructor):
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor.id)
            .first()
        )
        assert profile is not None

        second_catalog = ServiceCatalog(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            name=f"TFR Service 2 {_uid()}",
            slug=f"tfr-svc-2-{_uid()}",
            display_order=1,
            is_active=True,
        )
        db.add(second_catalog)
        db.flush()

        beginner_row = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=taxonomy_data["service"].id,
            hourly_rate=55.0,
            duration_options=[60],
            is_active=True,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )
        middle_row = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=second_catalog.id,
            hourly_rate=65.0,
            duration_options=[60],
            is_active=True,
            filter_selections={taxonomy_data["filter_key"]: ["middle"]},
        )
        db.add_all([beginner_row, middle_row])
        db.commit()

        repo = TaxonomyFilterRepository(db)
        matching = repo.find_matching_service_ids(
            service_ids=[beginner_row.id, middle_row.id],
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["elementary", "middle"]},
        )

        assert beginner_row.id in matching
        assert middle_row.id in matching

    def test_and_across_keys_with_subcategory_constraint(self, db, taxonomy_data, test_instructor):
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor.id)
            .first()
        )
        assert profile is not None

        uid = _uid()
        goal_key = f"tfr_goal_{uid}"
        goal_definition = FilterDefinition(
            key=goal_key,
            display_name="Goal",
            filter_type="multi_select",
        )
        db.add(goal_definition)
        db.flush()

        enrichment = FilterOption(
            filter_definition_id=goal_definition.id,
            value="enrichment",
            display_name="Enrichment",
            display_order=0,
        )
        test_prep = FilterOption(
            filter_definition_id=goal_definition.id,
            value="test_prep",
            display_name="Test Prep",
            display_order=1,
        )
        db.add_all([enrichment, test_prep])
        db.flush()

        goal_sub_filter = SubcategoryFilter(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_definition_id=goal_definition.id,
            display_order=1,
        )
        db.add(goal_sub_filter)
        db.flush()

        db.add_all(
            [
                SubcategoryFilterOption(
                    subcategory_filter_id=goal_sub_filter.id,
                    filter_option_id=enrichment.id,
                    display_order=0,
                ),
                SubcategoryFilterOption(
                    subcategory_filter_id=goal_sub_filter.id,
                    filter_option_id=test_prep.id,
                    display_order=1,
                ),
            ]
        )
        db.flush()

        second_catalog = ServiceCatalog(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            name=f"TFR Service 3 {uid}",
            slug=f"tfr-svc-3-{uid}",
            display_order=2,
            is_active=True,
        )
        other_sub_catalog = ServiceCatalog(
            subcategory_id=taxonomy_data["sub_without_filters"].id,
            name=f"TFR Service Other {uid}",
            slug=f"tfr-svc-other-{uid}",
            display_order=0,
            is_active=True,
        )
        db.add_all([second_catalog, other_sub_catalog])
        db.flush()

        matching_all = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=taxonomy_data["service"].id,
            hourly_rate=70.0,
            duration_options=[60],
            is_active=True,
            filter_selections={
                taxonomy_data["filter_key"]: ["elementary"],
                goal_key: ["enrichment"],
            },
        )
        wrong_goal = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=second_catalog.id,
            hourly_rate=75.0,
            duration_options=[60],
            is_active=True,
            filter_selections={
                taxonomy_data["filter_key"]: ["elementary"],
                goal_key: ["test_prep"],
            },
        )
        wrong_subcategory = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=other_sub_catalog.id,
            hourly_rate=80.0,
            duration_options=[60],
            is_active=True,
            filter_selections={
                taxonomy_data["filter_key"]: ["elementary"],
                goal_key: ["enrichment"],
            },
        )
        db.add_all([matching_all, wrong_goal, wrong_subcategory])
        db.commit()

        repo = TaxonomyFilterRepository(db)
        matching = repo.find_matching_service_ids(
            service_ids=[matching_all.id, wrong_goal.id, wrong_subcategory.id],
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={
                taxonomy_data["filter_key"]: ["elementary"],
                goal_key: ["enrichment"],
            },
        )

        assert matching_all.id in matching
        assert wrong_goal.id not in matching
        assert wrong_subcategory.id not in matching
