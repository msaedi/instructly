# backend/tests/repositories/test_taxonomy_filter_repository.py
"""
Integration tests for TaxonomyFilterRepository.

Requires real DB with taxonomy data. Uses locally-created test data
to avoid depending on seed state.
"""

from __future__ import annotations

from types import SimpleNamespace

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
    def test_single_value_match(self, db, taxonomy_data, test_instructor):
        """Instructor with matching filter value is returned."""
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

    def test_or_within_key_semantics(self, db, taxonomy_data, test_instructor):
        """Instructor tagged with only 'elementary' IS returned when querying
        ['elementary', 'middle'] — OR-within-key, not AND."""
        profile = db.query(InstructorProfile).filter(
            InstructorProfile.user_id == test_instructor.id
        ).first()
        assert profile is not None

        svc = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=taxonomy_data["service"].id,
            hourly_rate=55.0,
            duration_options=[60],
            is_active=True,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )
        db.add(svc)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        results = repo.find_instructors_by_filters(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["elementary", "middle"]},
        )

        assert any(r.id == svc.id for r in results), (
            "Instructor with ['elementary'] should match query ['elementary', 'middle'] (OR semantics)"
        )

    def test_no_match(self, db, taxonomy_data):
        """Returns empty when filter value does not exist in any instructor's selections."""
        repo = TaxonomyFilterRepository(db)
        results = repo.find_instructors_by_filters(
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["nonexistent_value_xyz"]},
        )
        assert results == []

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

    def test_inactive_services_excluded(self, db, taxonomy_data, test_instructor):
        """Inactive instructor services are excluded by default."""
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor.id)
            .first()
        )
        assert profile is not None

        inactive_svc = InstructorService(
            instructor_profile_id=profile.id,
            service_catalog_id=taxonomy_data["service"].id,
            hourly_rate=50.0,
            duration_options=[60],
            is_active=False,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )
        db.add(inactive_svc)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        matching = repo.find_matching_service_ids(
            service_ids=[inactive_svc.id],
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )

        assert inactive_svc.id not in matching

    def test_empty_service_ids_returns_empty(self, db, taxonomy_data):
        """Empty service_ids list returns empty set."""
        repo = TaxonomyFilterRepository(db)
        matching = repo.find_matching_service_ids(
            service_ids=[],
            subcategory_id=taxonomy_data["sub_with_filters"].id,
            filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        )

        assert matching == set()


class TestValidateFilterOptionInvariants:
    """D1: Tests for validate_filter_option_invariants."""

    def test_valid_options_pass(self, db, taxonomy_data):
        """Well-formed taxonomy data produces no violations."""
        repo = TaxonomyFilterRepository(db)
        violations = repo.validate_filter_option_invariants(taxonomy_data["sub_with_filters"].id)
        assert violations == []

    def test_nonexistent_subcategory_returns_empty(self, db):
        """Nonexistent subcategory produces no violations (no filters to check)."""
        repo = TaxonomyFilterRepository(db)
        violations = repo.validate_filter_option_invariants("01NONEXISTENT0000000000000")
        assert violations == []

    def test_cross_wired_option_detected(self, db, taxonomy_data):
        """Option from wrong FilterDefinition triggers a violation."""
        uid = _uid()

        # Create a second, unrelated filter definition with its own option
        fd_other = FilterDefinition(
            key=f"tfr_other_{uid}", display_name="Other Filter", filter_type="multi_select"
        )
        db.add(fd_other)
        db.flush()

        fo_wrong = FilterOption(
            filter_definition_id=fd_other.id, value=f"wrong_{uid}", display_name="Wrong", display_order=0
        )
        db.add(fo_wrong)
        db.flush()

        # Link the wrong option to the existing subcategory filter (grade_level)
        sf = taxonomy_data["subcategory_filter"]
        sfo_bad = SubcategoryFilterOption(
            subcategory_filter_id=sf.id, filter_option_id=fo_wrong.id, display_order=99
        )
        db.add(sfo_bad)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        violations = repo.validate_filter_option_invariants(taxonomy_data["sub_with_filters"].id)
        assert len(violations) == 1
        assert "does not match" in violations[0]


def test_find_matching_service_ids_python_fallback_and_inactive_toggle(
    db,
    taxonomy_data,
    test_instructor,
    monkeypatch,
):
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None

    active = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=taxonomy_data["service"].id,
        hourly_rate=45.0,
        duration_options=[60],
        is_active=True,
        filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
    )
    inactive = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=taxonomy_data["service"].id,
        hourly_rate=55.0,
        duration_options=[60],
        is_active=False,
        filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
    )
    db.add_all([active, inactive])
    db.commit()

    repo = TaxonomyFilterRepository(db)
    bind = repo.db.get_bind()
    monkeypatch.setattr(bind.dialect, "name", "sqlite", raising=False)

    matching_default = repo.find_matching_service_ids(
        service_ids=[active.id, inactive.id],
        filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
    )
    matching_with_inactive = repo.find_matching_service_ids(
        service_ids=[active.id, inactive.id],
        filter_selections={taxonomy_data["filter_key"]: ["elementary"]},
        active_only=False,
    )

    assert active.id in matching_default
    assert inactive.id not in matching_default
    assert {active.id, inactive.id}.issubset(matching_with_inactive)


def test_find_instructors_by_filters_allows_inactive_when_requested(
    db,
    taxonomy_data,
    test_instructor,
):
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None

    svc = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=taxonomy_data["service"].id,
        hourly_rate=50.0,
        duration_options=[60],
        is_active=False,
        filter_selections={taxonomy_data["filter_key"]: ["middle"]},
    )
    db.add(svc)
    db.commit()

    repo = TaxonomyFilterRepository(db)
    results = repo.find_instructors_by_filters(
        subcategory_id=taxonomy_data["sub_with_filters"].id,
        filter_selections={taxonomy_data["filter_key"]: ["middle"]},
        active_only=False,
    )
    assert any(row.id == svc.id for row in results)


def test_find_instructors_by_filters_skips_empty_filter_values(monkeypatch):
    query = SimpleNamespace(limit=lambda *_: SimpleNamespace(all=lambda: []))
    query.join = lambda *_args, **_kwargs: query
    query.filter = lambda *_args, **_kwargs: query
    db = SimpleNamespace(query=lambda *_args, **_kwargs: query)
    repo = TaxonomyFilterRepository(db)
    monkeypatch.setattr(repo, "_normalize_filter_selections", lambda _filters: {"grade": []})
    assert repo.find_instructors_by_filters("subcategory", {"grade": ["x"]}) == []


def test_get_filters_and_validators_skip_missing_relations(monkeypatch):
    sf_missing_definition = SimpleNamespace(filter_definition=None, filter_options=[])
    sf_with_missing_option = SimpleNamespace(
        filter_definition=SimpleNamespace(
            id="fd-1",
            key="grade_level",
            display_name="Grade Level",
            filter_type="multi_select",
        ),
        filter_options=[SimpleNamespace(filter_option=None, display_order=0)],
    )
    sf_invariant_missing = SimpleNamespace(filter_definition=None, filter_options=[])
    sf_invariant_missing_option = SimpleNamespace(
        filter_definition=SimpleNamespace(id="fd-2"),
        filter_options=[SimpleNamespace(filter_option=None, id="sfo-1")],
    )

    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_args, **_kwargs):
            return self

        def options(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return self._rows

    rows_per_call = [
        [sf_missing_definition, sf_with_missing_option],
        [sf_missing_definition],
        [sf_invariant_missing, sf_invariant_missing_option],
    ]

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Query(rows_per_call.pop(0))

    repo = TaxonomyFilterRepository(_DB())

    filters = repo.get_filters_for_subcategory("sub")
    assert len(filters) == 1
    assert filters[0]["options"] == []

    valid, errors = repo.validate_filter_selections("sub", {"grade_level": ["x"]})
    assert valid is False
    assert errors

    violations = repo.validate_filter_option_invariants("sub")
    assert violations == []
