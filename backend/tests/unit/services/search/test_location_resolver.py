from __future__ import annotations

import pytest
from sqlalchemy import text
from ulid import ULID

from app.models.location_alias import LocationAlias
from app.models.region_boundary import RegionBoundary
from app.services.search.location_resolver import LocationResolver


def _create_region(
    db,
    *,
    region_type: str,
    region_name: str,
    parent_region: str | None = None,
) -> RegionBoundary:
    boundary = RegionBoundary(
        region_type=region_type,
        region_code=str(ULID()),
        region_name=region_name,
        parent_region=parent_region,
        region_metadata={"test": True},
    )
    db.add(boundary)
    db.flush()
    return boundary


class TestLocationResolver:
    def test_exact_match_neighborhood(self, db):
        region_type = "test"
        _create_region(db, region_type=region_type, region_name="Lower East Side", parent_region="Manhattan")

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("Lower East Side")

        assert resolved.kind == "region"
        assert resolved.method == "exact"
        assert resolved.region is not None
        assert resolved.region.region_name == "Lower East Side"

    def test_exact_match_borough(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("Brooklyn")

        assert resolved.kind == "borough"
        assert resolved.method == "exact"
        assert resolved.borough_name == "Brooklyn"

    def test_alias_match_borough_abbreviation(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("bk")

        assert resolved.kind == "borough"
        assert resolved.method == "alias"
        assert resolved.borough_name == "Brooklyn"

    def test_alias_match_via_table(self, db):
        region_type = "test"
        park_slope = _create_region(db, region_type=region_type, region_name="Park Slope", parent_region="Brooklyn")
        db.add(
            LocationAlias(
                alias="the slope",
                region_boundary_id=park_slope.id,
                alias_type="colloquial",
            )
        )
        db.flush()

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("the slope")

        assert resolved.kind == "region"
        assert resolved.method == "alias"
        assert resolved.region is not None
        assert resolved.region.region_name == "Park Slope"

    def test_fuzzy_match(self, db):
        if db.bind.dialect.name != "postgresql":
            pytest.skip("pg_trgm similarity only available in Postgres")

        try:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            db.commit()
        except Exception:
            pytest.skip("pg_trgm extension not available")

        region_type = "test"
        _create_region(db, region_type=region_type, region_name="Lower East Side", parent_region="Manhattan")

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("lower east")

        assert resolved.kind == "region"
        assert resolved.method == "fuzzy"
        assert resolved.region is not None
        assert resolved.region.region_name == "Lower East Side"
        assert resolved.similarity is not None
        assert resolved.similarity > 0

    def test_no_match_returns_none(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("narnia")

        assert resolved.kind == "none"
        assert resolved.method == "none"
        assert resolved.region is None

    def test_empty_input_returns_none(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("")

        assert resolved.kind == "none"
        assert resolved.method == "none"

    def test_whitespace_handling(self, db):
        region_type = "test"
        _create_region(db, region_type=region_type, region_name="Lower East Side", parent_region="Manhattan")

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("  lower   east side  ")

        assert resolved.kind == "region"
        assert resolved.method == "exact"
        assert resolved.region is not None
        assert resolved.region.region_name == "Lower East Side"
