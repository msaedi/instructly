"""Helpers for neighborhood display-layer serialization."""

from __future__ import annotations


def display_area_from_region(region: object) -> dict[str, str] | None:
    """Return public display-layer service-area metadata for a region row."""
    if region is None:
        return None

    display_name = getattr(region, "display_name", None)
    display_key = getattr(region, "display_key", None)
    borough = getattr(region, "parent_region", None) or ""
    if not display_name or not display_key:
        return None

    return {
        "display_name": str(display_name),
        "display_key": str(display_key),
        "borough": str(borough),
    }
