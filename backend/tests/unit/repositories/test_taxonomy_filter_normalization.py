# backend/tests/unit/repositories/test_taxonomy_filter_normalization.py
"""
Unit tests for TaxonomyFilterRepository static/private helper methods.

These are pure functions with no DB dependency — test normalization,
matching, and coercion logic.
"""

import pytest

pytestmark = pytest.mark.unit

from app.repositories.taxonomy_filter_repository import (
    MAX_FILTER_KEYS,
    MAX_FILTER_VALUE_LENGTH,
    MAX_FILTER_VALUES_PER_KEY,
    TaxonomyFilterRepository,
)

# ── _coerce_values ───────────────────────────────────────────


class TestCoerceValues:
    def test_none_returns_empty_list(self):
        assert TaxonomyFilterRepository._coerce_values(None) == []

    def test_list_passthrough(self):
        assert TaxonomyFilterRepository._coerce_values(["a", "b"]) == ["a", "b"]

    def test_tuple_to_list(self):
        assert TaxonomyFilterRepository._coerce_values(("a", "b")) == ["a", "b"]

    def test_set_to_list(self):
        result = TaxonomyFilterRepository._coerce_values({"a"})
        assert isinstance(result, list)
        assert result == ["a"]

    def test_scalar_wrapped(self):
        assert TaxonomyFilterRepository._coerce_values("beginner") == ["beginner"]

    def test_int_scalar_wrapped(self):
        assert TaxonomyFilterRepository._coerce_values(42) == [42]


# ── _normalize_filter_selections ─────────────────────────────


class TestNormalizeFilterSelections:
    @pytest.fixture
    def repo(self):
        """Create a TaxonomyFilterRepository without a real DB session.

        _normalize_filter_selections is a bound method that only uses self
        for _coerce_values (a static method), so we can pass None.
        """
        return TaxonomyFilterRepository.__new__(TaxonomyFilterRepository)

    def test_passthrough_already_normalized(self, repo):
        result = repo._normalize_filter_selections({"skill_level": ["beginner"]})
        assert result == {"skill_level": ["beginner"]}

    def test_lowercased(self, repo):
        result = repo._normalize_filter_selections({"Skill_Level": ["Beginner", "ADVANCED"]})
        assert result == {"skill_level": ["beginner", "advanced"]}

    def test_whitespace_stripped(self, repo):
        result = repo._normalize_filter_selections({"  goal  ": ["  fitness  "]})
        assert result == {"goal": ["fitness"]}

    def test_empty_keys_skipped(self, repo):
        result = repo._normalize_filter_selections({"": ["value"], "goal": ["fitness"]})
        assert result == {"goal": ["fitness"]}

    def test_empty_values_skipped(self, repo):
        result = repo._normalize_filter_selections({"goal": ["", "  ", "fitness"]})
        assert result == {"goal": ["fitness"]}

    def test_duplicate_values_deduplicated(self, repo):
        result = repo._normalize_filter_selections({"goal": ["fitness", "FITNESS", "Fitness"]})
        assert result == {"goal": ["fitness"]}

    def test_none_input_returns_empty(self, repo):
        assert repo._normalize_filter_selections(None) == {}

    def test_empty_dict_returns_empty(self, repo):
        assert repo._normalize_filter_selections({}) == {}

    def test_key_cardinality_cap(self, repo):
        filters = {f"key{i}": ["v"] for i in range(MAX_FILTER_KEYS + 5)}
        result = repo._normalize_filter_selections(filters)
        assert len(result) == MAX_FILTER_KEYS

    def test_value_cardinality_cap(self, repo):
        values = [f"v{i}" for i in range(MAX_FILTER_VALUES_PER_KEY + 5)]
        result = repo._normalize_filter_selections({"key": values})
        assert len(result["key"]) == MAX_FILTER_VALUES_PER_KEY

    def test_value_length_cap(self, repo):
        long_value = "x" * (MAX_FILTER_VALUE_LENGTH + 1)
        result = repo._normalize_filter_selections({"key": [long_value, "ok"]})
        assert result == {"key": ["ok"]}

    def test_keys_with_only_empty_values_excluded(self, repo):
        result = repo._normalize_filter_selections({"key": ["", "  "]})
        assert result == {}


# ── _matches_filter_selections ───────────────────────────────


class TestMatchesFilterSelections:
    def test_empty_requested_matches_anything(self):
        assert TaxonomyFilterRepository._matches_filter_selections(
            selections={"goal": ["fitness"]},
            requested={},
        )

    def test_or_within_key(self):
        """Any matching value within a key is sufficient."""
        assert TaxonomyFilterRepository._matches_filter_selections(
            selections={"skill_level": ["beginner"]},
            requested={"skill_level": ["beginner", "intermediate"]},
        )

    def test_and_across_keys(self):
        """All requested keys must match."""
        assert not TaxonomyFilterRepository._matches_filter_selections(
            selections={"skill_level": ["beginner"]},
            requested={"skill_level": ["beginner"], "goal": ["fitness"]},
        )

    def test_no_match_within_key(self):
        assert not TaxonomyFilterRepository._matches_filter_selections(
            selections={"skill_level": ["advanced"]},
            requested={"skill_level": ["beginner"]},
        )

    def test_case_insensitive(self):
        assert TaxonomyFilterRepository._matches_filter_selections(
            selections={"skill_level": ["Beginner"]},
            requested={"skill_level": ["beginner"]},
        )

    def test_missing_key_no_match(self):
        assert not TaxonomyFilterRepository._matches_filter_selections(
            selections={},
            requested={"skill_level": ["beginner"]},
        )

    def test_non_list_value_returns_false(self):
        assert not TaxonomyFilterRepository._matches_filter_selections(
            selections={"skill_level": "beginner"},  # type: ignore[arg-type]
            requested={"skill_level": ["beginner"]},
        )
