"""Unit tests for neighborhood_helpers.py — display_area_from_region."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.neighborhood_helpers import display_area_from_region


class TestDisplayAreaFromRegion:
    def test_none_region_returns_none(self) -> None:
        assert display_area_from_region(None) is None

    def test_missing_display_name_returns_none(self) -> None:
        """Region with display_key but no display_name → None (line 15)."""
        region = SimpleNamespace(display_key="dk1", display_name=None, parent_region="Manhattan")
        assert display_area_from_region(region) is None

    def test_missing_display_key_returns_none(self) -> None:
        """Region with display_name but no display_key → None."""
        region = SimpleNamespace(display_key=None, display_name="Chelsea", parent_region="Manhattan")
        assert display_area_from_region(region) is None

    def test_valid_region_returns_dict(self) -> None:
        region = SimpleNamespace(display_key="dk1", display_name="Chelsea", parent_region="Manhattan")
        result = display_area_from_region(region)
        assert result == {"display_name": "Chelsea", "display_key": "dk1", "borough": "Manhattan"}

    def test_empty_parent_region_defaults_to_empty_string(self) -> None:
        region = SimpleNamespace(display_key="dk1", display_name="Chelsea", parent_region=None)
        result = display_area_from_region(region)
        assert result is not None
        assert result["borough"] == ""
