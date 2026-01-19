"""Additional coverage tests for LocationAlias model."""

from __future__ import annotations

from app.models.location_alias import LocationAlias


def test_location_alias_is_trusted_active() -> None:
    alias = LocationAlias(status="active")
    assert alias.is_trusted is True


def test_location_alias_is_trusted_pending_review() -> None:
    alias = LocationAlias(status="pending_review", confidence=0.9, user_count=5)
    assert alias.is_trusted is True

    alias = LocationAlias(status="pending_review", confidence=0.89, user_count=5)
    assert alias.is_trusted is False


def test_location_alias_is_trusted_other_status() -> None:
    alias = LocationAlias(status="deprecated", confidence=1.0, user_count=10)
    assert alias.is_trusted is False


def test_location_alias_resolution_flags() -> None:
    resolved = LocationAlias(
        status="active",
        region_boundary_id="region",
        requires_clarification=False,
    )
    assert resolved.is_resolved is True
    assert resolved.is_ambiguous is False

    ambiguous = LocationAlias(
        status="active",
        region_boundary_id=None,
        requires_clarification=True,
        candidate_region_ids=["a", "b"],
    )
    assert ambiguous.is_resolved is False
    assert ambiguous.is_ambiguous is True
