# backend/tests/unit/routes/test_taxonomy_filter_query.py
"""
Unit tests for taxonomy filter query parameter parsing helpers.

These are pure functions with no DB dependency — test edge cases
for input parsing, validation, and normalization.
"""

import pytest

pytestmark = pytest.mark.unit

from app.routes.v1.taxonomy_filter_query import (
    MAX_CONTENT_FILTER_KEYS,
    MAX_CONTENT_FILTER_VALUES_PER_KEY,
    _parse_content_filters,
    _parse_csv_values,
    _validate_content_filter_bounds,
    _validate_skill_levels,
    parse_taxonomy_filter_query_params,
)

# ── _parse_csv_values ────────────────────────────────────────


class TestParseCsvValues:
    def test_basic_split(self):
        assert _parse_csv_values("beginner,intermediate") == ["beginner", "intermediate"]

    def test_whitespace_stripped(self):
        assert _parse_csv_values("  beginner , intermediate  ") == ["beginner", "intermediate"]

    def test_lowercased(self):
        assert _parse_csv_values("Beginner,ADVANCED") == ["beginner", "advanced"]

    def test_duplicates_removed(self):
        assert _parse_csv_values("beginner,beginner,advanced") == ["beginner", "advanced"]

    def test_empty_tokens_skipped(self):
        assert _parse_csv_values(",,,beginner,,") == ["beginner"]

    def test_whitespace_only_tokens_skipped(self):
        assert _parse_csv_values("  ,  , beginner") == ["beginner"]

    def test_none_returns_empty(self):
        assert _parse_csv_values(None) == []

    def test_empty_string_returns_empty(self):
        assert _parse_csv_values("") == []

    def test_single_value(self):
        assert _parse_csv_values("advanced") == ["advanced"]

    def test_value_with_reserved_pipe_raises(self):
        with pytest.raises(ValueError, match="reserved delimiter character"):
            _parse_csv_values("has|pipe")

    def test_value_with_reserved_colon_raises(self):
        with pytest.raises(ValueError, match="reserved delimiter character"):
            _parse_csv_values("has:colon")


# ── _validate_skill_levels ───────────────────────────────────


class TestValidateSkillLevels:
    def test_valid_levels_pass(self):
        _validate_skill_levels(["beginner", "intermediate", "advanced"])

    def test_empty_list_passes(self):
        _validate_skill_levels([])

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="Invalid skill_level"):
            _validate_skill_levels(["expert"])

    def test_mixed_valid_invalid_raises(self):
        with pytest.raises(ValueError, match="expert"):
            _validate_skill_levels(["beginner", "expert"])


# ── _validate_content_filter_bounds ──────────────────────────


class TestValidateContentFilterBounds:
    def test_within_bounds_passes(self):
        _validate_content_filter_bounds({"key1": ["v1"], "key2": ["v2"]})

    def test_empty_passes(self):
        _validate_content_filter_bounds({})

    def test_too_many_keys_raises(self):
        filters = {f"key{i}": ["v"] for i in range(MAX_CONTENT_FILTER_KEYS + 1)}
        with pytest.raises(ValueError, match="at most"):
            _validate_content_filter_bounds(filters)

    def test_exact_key_limit_passes(self):
        filters = {f"key{i}": ["v"] for i in range(MAX_CONTENT_FILTER_KEYS)}
        _validate_content_filter_bounds(filters)

    def test_too_many_values_per_key_raises(self):
        filters = {"key": [f"v{i}" for i in range(MAX_CONTENT_FILTER_VALUES_PER_KEY + 1)]}
        with pytest.raises(ValueError, match="at most"):
            _validate_content_filter_bounds(filters)

    def test_exact_value_limit_passes(self):
        filters = {"key": [f"v{i}" for i in range(MAX_CONTENT_FILTER_VALUES_PER_KEY)]}
        _validate_content_filter_bounds(filters)


# ── _parse_content_filters ───────────────────────────────────


class TestParseContentFilters:
    def test_basic_parsing(self):
        result = _parse_content_filters("goal:fitness,flexibility|style:modern")
        assert result == {"goal": ["fitness", "flexibility"], "style": ["modern"]}

    def test_none_returns_empty(self):
        assert _parse_content_filters(None) == {}

    def test_empty_string_returns_empty(self):
        assert _parse_content_filters("") == {}

    def test_malformed_no_colon_raises(self):
        with pytest.raises(ValueError, match="Malformed"):
            _parse_content_filters("no_colon_here")

    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="Key cannot be empty"):
            _parse_content_filters(":value1")

    def test_empty_values_raises(self):
        with pytest.raises(ValueError, match="At least one value"):
            _parse_content_filters("key:")

    def test_deduplication_across_segments(self):
        result = _parse_content_filters("goal:fitness|goal:fitness,strength")
        assert result == {"goal": ["fitness", "strength"]}

    def test_value_with_colon_raises(self):
        with pytest.raises(ValueError, match="reserved delimiter character"):
            _parse_content_filters("note:has:colons")

    def test_whitespace_in_segments(self):
        result = _parse_content_filters(" goal : fitness , flexibility ")
        assert result == {"goal": ["fitness", "flexibility"]}

    def test_empty_segments_between_pipes(self):
        result = _parse_content_filters("goal:fitness||style:modern")
        assert result == {"goal": ["fitness"], "style": ["modern"]}

    def test_keys_lowercased(self):
        result = _parse_content_filters("Goal:fitness")
        assert "goal" in result


# ── parse_taxonomy_filter_query_params ───────────────────────


class TestParseTaxonomyFilterQueryParams:
    def test_skill_level_only(self):
        filters, levels = parse_taxonomy_filter_query_params(
            skill_level="beginner,intermediate",
            content_filters=None,
        )
        assert filters == {"skill_level": ["beginner", "intermediate"]}
        assert levels == ["beginner", "intermediate"]

    def test_content_filters_only(self):
        filters, levels = parse_taxonomy_filter_query_params(
            skill_level=None,
            content_filters="goal:fitness",
        )
        assert filters == {"goal": ["fitness"]}
        assert levels == []

    def test_skill_level_overrides_content_filters(self):
        """Explicit skill_level param takes precedence over skill_level in content_filters."""
        filters, levels = parse_taxonomy_filter_query_params(
            skill_level="advanced",
            content_filters="skill_level:beginner|goal:fitness",
        )
        assert filters["skill_level"] == ["advanced"]
        assert filters["goal"] == ["fitness"]
        assert levels == ["advanced"]

    def test_both_none(self):
        filters, levels = parse_taxonomy_filter_query_params(
            skill_level=None,
            content_filters=None,
        )
        assert filters == {}
        assert levels == []

    def test_invalid_skill_level_raises(self):
        with pytest.raises(ValueError, match="Invalid skill_level"):
            parse_taxonomy_filter_query_params(
                skill_level="expert",
                content_filters=None,
            )
