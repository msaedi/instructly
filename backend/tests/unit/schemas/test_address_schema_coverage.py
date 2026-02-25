"""Tests for app/schemas/address.py — coverage gaps L32, L65-70, L75."""
from __future__ import annotations

import pytest

from app.schemas.address import AddressCreate, AddressUpdate


def _base_address_data(**overrides: object) -> dict:
    """Minimal valid AddressCreate data."""
    data = {
        "street_line1": "123 Main St",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10001",
        "country_code": "US",
    }
    data.update(overrides)
    return data


@pytest.mark.unit
class TestAddressCreateCoverage:
    """Cover normalize_custom_label and validate_custom_label in AddressCreate."""

    def test_custom_label_none_returns_none(self) -> None:
        """L32: normalize_custom_label returns None when value is None."""
        addr = AddressCreate(**_base_address_data(label="home", custom_label=None))
        assert addr.custom_label is None

    def test_custom_label_whitespace_only_returns_none(self) -> None:
        """Whitespace-only string should normalize to None."""
        addr = AddressCreate(**_base_address_data(label="home", custom_label="   "))
        assert addr.custom_label is None

    def test_custom_label_strips_whitespace(self) -> None:
        addr = AddressCreate(**_base_address_data(label="other", custom_label="  Office  "))
        assert addr.custom_label == "Office"

    def test_custom_label_non_string_raises(self) -> None:
        with pytest.raises(Exception, match="custom_label must be a string"):
            AddressCreate(**_base_address_data(custom_label=123))

    def test_label_other_without_custom_label_raises(self) -> None:
        """L75 equivalent: label='other' with no custom_label."""
        with pytest.raises(Exception, match="custom_label is required"):
            AddressCreate(**_base_address_data(label="other"))

    def test_label_other_with_empty_custom_label_raises(self) -> None:
        """label='other' with empty string custom_label (normalizes to None)."""
        with pytest.raises(Exception, match="custom_label is required"):
            AddressCreate(**_base_address_data(label="other", custom_label=""))

    def test_label_other_with_whitespace_custom_label_raises(self) -> None:
        """label='other' with whitespace-only custom_label (normalizes to None)."""
        with pytest.raises(Exception, match="custom_label is required"):
            AddressCreate(**_base_address_data(label="other", custom_label="   "))

    def test_label_other_with_valid_custom_label_ok(self) -> None:
        addr = AddressCreate(**_base_address_data(label="other", custom_label="Gym"))
        assert addr.custom_label == "Gym"

    def test_label_home_ignores_custom_label(self) -> None:
        """Non-'other' labels don't require custom_label."""
        addr = AddressCreate(**_base_address_data(label="home"))
        assert addr.custom_label is None


@pytest.mark.unit
class TestAddressUpdateCoverage:
    """Cover normalize_custom_label and validate_custom_label in AddressUpdate."""

    def test_custom_label_none_returns_none(self) -> None:
        """L65-66: normalize_custom_label returns None when value is None."""
        addr = AddressUpdate(custom_label=None)
        assert addr.custom_label is None

    def test_custom_label_whitespace_only_returns_none(self) -> None:
        """L69-70: stripped empty → None."""
        addr = AddressUpdate(custom_label="   ")
        assert addr.custom_label is None

    def test_custom_label_strips_whitespace(self) -> None:
        addr = AddressUpdate(label="other", custom_label="  Studio  ")
        assert addr.custom_label == "Studio"

    def test_custom_label_non_string_raises(self) -> None:
        """L67-68: non-string raises ValueError."""
        with pytest.raises(Exception, match="custom_label must be a string"):
            AddressUpdate(custom_label=42)

    def test_label_other_without_custom_label_raises(self) -> None:
        """L74-75: label='other' but custom_label missing."""
        with pytest.raises(Exception, match="custom_label is required"):
            AddressUpdate(label="other")

    def test_label_other_with_empty_custom_label_raises(self) -> None:
        with pytest.raises(Exception, match="custom_label is required"):
            AddressUpdate(label="other", custom_label="")

    def test_label_other_with_whitespace_custom_label_raises(self) -> None:
        with pytest.raises(Exception, match="custom_label is required"):
            AddressUpdate(label="other", custom_label="    ")

    def test_label_other_with_valid_custom_label_ok(self) -> None:
        addr = AddressUpdate(label="other", custom_label="Park")
        assert addr.custom_label == "Park"

    def test_update_no_fields(self) -> None:
        """All optional, so no fields is valid (label is not 'other')."""
        addr = AddressUpdate()
        assert addr.label is None
        assert addr.custom_label is None
