"""Unit tests for response_diagnostics.py display-label behavior."""

from __future__ import annotations

from app.services.search.location_resolver import ResolvedLocation
from app.services.search.nl_pipeline.models import PipelineTimer
from app.services.search.nl_pipeline.response_diagnostics import (
    build_location_diagnostics,
    format_location_resolved,
)
from app.services.search.query_parser import ParsedQuery


class TestFormatLocationResolved:
    def test_prefers_display_name_for_candidates(self) -> None:
        location_resolution = ResolvedLocation(
            requires_clarification=True,
            candidates=[
                {
                    "region_name": "Upper East Side-Carnegie Hill",
                    "display_name": "Upper East Side",
                },
                {
                    "region_name": "Upper East Side-Yorkville",
                    "display_name": "Upper East Side",
                },
            ],
        )

        assert format_location_resolved(location_resolution) == "Upper East Side"

    def test_prefix_matching_only_suffix_returns_prefix(self) -> None:
        location_resolution = ResolvedLocation(
            requires_clarification=True,
            candidates=[
                {
                    "region_name": "Upper East Side-Carnegie Hill",
                    "display_name": "Upper East Side (Upper East Side)",
                }
            ],
        )

        assert format_location_resolved(location_resolution) == "Upper East Side"

    def test_falls_back_to_region_name_when_display_name_missing(self) -> None:
        location_resolution = ResolvedLocation(
            requires_clarification=True,
            candidates=[
                {"region_name": "Astoria (Queens)"},
                {"region_name": "Astoria (North)"},
            ],
        )

        assert format_location_resolved(location_resolution) == "Astoria (North, Queens)"


def test_build_location_diagnostics_prefers_display_name_and_dedupes() -> None:
    diagnostics = build_location_diagnostics(
        timer=PipelineTimer(),
        parsed_query=ParsedQuery(
            original_query="piano lessons in ues",
            service_query="piano lessons",
            parsing_mode="regex",
            location_text="ues",
        ),
        location_resolution=ResolvedLocation(
            requires_clarification=True,
            candidates=[
                {
                    "region_name": "Upper East Side-Carnegie Hill",
                    "display_name": "Upper East Side",
                },
                {
                    "region_name": "Upper East Side-Yorkville",
                    "display_name": "Upper East Side",
                },
                {
                    "region_name": "Upper East Side-Lenox Hill-Roosevelt Island",
                    "display_name": "Upper East Side / Roosevelt Island",
                },
            ],
        ),
    )

    assert diagnostics is not None
    assert diagnostics.resolved_regions == [
        "Upper East Side",
        "Upper East Side / Roosevelt Island",
    ]
