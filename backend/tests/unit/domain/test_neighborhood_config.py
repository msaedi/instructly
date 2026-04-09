"""Unit tests for neighborhood_config display mappings and key generation."""

from __future__ import annotations

from app.domain.neighborhood_config import NEIGHBORHOOD_MAPPING, generate_display_key


def test_bedford_stuyvesant_display_mapping_uses_separator() -> None:
    assert NEIGHBORHOOD_MAPPING[("Brooklyn", "Bedford-Stuyvesant (East)")] == "Bedford / Stuyvesant"
    assert NEIGHBORHOOD_MAPPING[("Brooklyn", "Bedford-Stuyvesant (West)")] == "Bedford / Stuyvesant"


def test_bedford_stuyvesant_display_key_stays_stable() -> None:
    assert (
        generate_display_key("nyc", "Brooklyn", "Bedford / Stuyvesant")
        == "nyc-brooklyn-bedford-stuyvesant"
    )
