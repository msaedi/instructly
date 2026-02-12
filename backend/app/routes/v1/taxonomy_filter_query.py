"""Helpers for parsing taxonomy filter query parameters."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.repositories.taxonomy_filter_repository import (
    MAX_FILTER_KEYS as MAX_CONTENT_FILTER_KEYS,
    MAX_FILTER_VALUES_PER_KEY as MAX_CONTENT_FILTER_VALUES_PER_KEY,
)

ALLOWED_SKILL_LEVELS = {"beginner", "intermediate", "advanced"}

logger = logging.getLogger(__name__)


def _parse_csv_values(raw_value: Optional[str]) -> List[str]:
    """Parse comma-separated values into normalized, unique tokens."""
    if raw_value is None or not isinstance(raw_value, str):
        return []

    values: List[str] = []
    seen: set[str] = set()
    for token in raw_value.split(","):
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            continue
        # `content_filters` uses `|` and `:` as structural delimiters; seeded
        # taxonomy filter option values are slug-like tokens and must not
        # include either character.
        if "|" in normalized or ":" in normalized:
            delimiter = "|" if "|" in normalized else ":"
            raise ValueError(
                f"Filter value '{normalized}' contains reserved delimiter character ('{delimiter}')"
            )
        seen.add(normalized)
        values.append(normalized)
    return values


def _validate_skill_levels(skill_levels: List[str]) -> None:
    invalid_skill_levels = sorted(
        level for level in skill_levels if level not in ALLOWED_SKILL_LEVELS
    )
    if invalid_skill_levels:
        raise ValueError(
            "Invalid skill_level value(s): "
            f"{', '.join(invalid_skill_levels)}. Allowed: beginner, intermediate, advanced"
        )


def _validate_content_filter_bounds(filters: Dict[str, List[str]]) -> None:
    if len(filters) > MAX_CONTENT_FILTER_KEYS:
        raise ValueError(f"content_filters supports at most {MAX_CONTENT_FILTER_KEYS} keys")

    for key, values in filters.items():
        if len(values) > MAX_CONTENT_FILTER_VALUES_PER_KEY:
            raise ValueError(
                f"content_filters key '{key}' supports at most "
                f"{MAX_CONTENT_FILTER_VALUES_PER_KEY} values"
            )


def _parse_content_filters(content_filters: Optional[str]) -> Dict[str, List[str]]:
    """Parse key/value content filters into taxonomy filter selections."""
    parsed_filters: Dict[str, List[str]] = {}
    if content_filters is None or not isinstance(content_filters, str):
        return parsed_filters

    for segment in content_filters.split("|"):
        normalized_segment = segment.strip()
        if not normalized_segment:
            continue
        if ":" not in normalized_segment:
            logger.warning(
                "Rejecting malformed content_filters segment without ':'",
                extra={"segment": normalized_segment},
            )
            raise ValueError(
                f"Malformed content_filters segment '{normalized_segment}'. Expected format 'key:value1,value2'"
            )

        key_raw, values_raw = normalized_segment.split(":", 1)
        key = key_raw.strip().lower()
        if not key:
            logger.warning("Rejecting malformed content_filters segment with empty key")
            raise ValueError(
                f"Malformed content_filters segment '{normalized_segment}'. Key cannot be empty"
            )

        values = _parse_csv_values(values_raw)
        if not values:
            logger.warning(
                "Rejecting malformed content_filters segment with empty values",
                extra={"key": key},
            )
            raise ValueError(
                f"Malformed content_filters segment '{normalized_segment}'. At least one value is required"
            )

        existing_values = parsed_filters.setdefault(key, [])
        existing_seen = set(existing_values)
        for value in values:
            if value in existing_seen:
                continue
            existing_values.append(value)
            existing_seen.add(value)

    _validate_content_filter_bounds(parsed_filters)
    return parsed_filters


def parse_taxonomy_filter_query_params(
    *,
    skill_level: Optional[str],
    content_filters: Optional[str],
) -> Tuple[Dict[str, List[str]], List[str]]:
    """Parse route query params into repository-ready taxonomy filter selections.

    Returns:
        tuple[filters, explicit_skill_levels]
    """
    taxonomy_filter_selections = _parse_content_filters(content_filters)

    if "skill_level" in taxonomy_filter_selections:
        _validate_skill_levels(taxonomy_filter_selections["skill_level"])

    explicit_skill_levels = _parse_csv_values(skill_level)
    _validate_skill_levels(explicit_skill_levels)

    # Explicit skill_level query parameter takes precedence over any embedded
    # skill_level present in content_filters.
    if explicit_skill_levels:
        taxonomy_filter_selections["skill_level"] = explicit_skill_levels

    _validate_content_filter_bounds(taxonomy_filter_selections)
    return taxonomy_filter_selections, explicit_skill_levels
