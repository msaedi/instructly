from __future__ import annotations

import pytest
from sqlalchemy import text
from ulid import ULID

from app.models.location_alias import LocationAlias
from app.models.region_boundary import RegionBoundary
from app.services.search.location_resolver import LocationResolver, ResolutionTier


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
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.EXACT
        assert resolved.region_name == "Lower East Side"
        assert resolved.borough == "Manhattan"

    def test_exact_match_borough(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("Brooklyn")

        assert resolved.kind == "borough"
        assert resolved.method == "exact"
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.EXACT
        assert resolved.borough == "Brooklyn"

    def test_alias_match_borough_abbreviation(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("bk")

        assert resolved.kind == "borough"
        assert resolved.method == "alias"
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.ALIAS
        assert resolved.borough == "Brooklyn"

    def test_alias_match_via_table(self, db):
        region_type = "test"
        park_slope = _create_region(db, region_type=region_type, region_name="Park Slope", parent_region="Brooklyn")
        db.add(
            LocationAlias(
                alias_normalized="the slope",
                region_boundary_id=park_slope.id,
                alias_type="colloquial",
                status="active",
                confidence=1.0,
                user_count=1,
            )
        )
        db.flush()

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("the slope")

        assert resolved.kind == "region"
        assert resolved.method == "alias"
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.ALIAS
        assert resolved.region_name == "Park Slope"
        assert resolved.borough == "Brooklyn"

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
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.FUZZY
        assert resolved.region_name == "Lower East Side"
        assert resolved.confidence > 0

    def test_substring_match_resolves_single_region(self, db):
        region_type = "test"
        _create_region(
            db,
            region_type=region_type,
            region_name="Upper East Side-Carnegie Hill",
            parent_region="Manhattan",
        )

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("carnegie")

        assert resolved.kind == "region"
        assert resolved.method == "fuzzy"
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.FUZZY
        assert resolved.region_name == "Upper East Side-Carnegie Hill"

    def test_substring_match_can_return_ambiguous(self, db):
        region_type = "test"
        _create_region(
            db,
            region_type=region_type,
            region_name="East Midtown-Turtle Bay",
            parent_region="Manhattan",
        )
        _create_region(
            db,
            region_type=region_type,
            region_name="West Midtown",
            parent_region="Manhattan",
        )

        resolver = LocationResolver(db, region_code=region_type)
        resolved = resolver.resolve("midtown")

        assert resolved.method == "fuzzy"
        assert resolved.requires_clarification is True
        assert resolved.tier == ResolutionTier.FUZZY
        assert resolved.candidates is not None
        assert len(resolved.candidates) >= 2

    def test_no_match_returns_none(self, db):
        resolver = LocationResolver(db, region_code="test")
        resolved = resolver.resolve("narnia")

        assert resolved.kind == "none"
        assert resolved.method == "none"
        assert resolved.not_found is True
        assert resolved.region_id is None
        assert resolved.borough is None

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
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.EXACT
        assert resolved.region_name == "Lower East Side"

    def test_tier4_embedding_match_when_enabled(self, db, monkeypatch):
        region_type = "test"
        region = _create_region(
            db,
            region_type=region_type,
            region_name="Upper East Side-Carnegie Hill",
            parent_region="Manhattan",
        )

        resolver = LocationResolver(db, region_code=region_type)

        monkeypatch.setattr(
            resolver.embedding_service,
            "get_candidates",
            lambda *_args, **_kwargs: [
                {
                    "region_id": str(region.id),
                    "region_name": region.region_name,
                    "borough": region.parent_region,
                    "similarity": 0.91,
                }
            ],
        )
        monkeypatch.setattr(
            resolver.embedding_service,
            "pick_best_or_ambiguous",
            lambda candidates: (candidates[0], None),
        )

        resolved = resolver.resolve("museum mile", enable_semantic=True)

        assert resolved.method == "embedding"
        assert resolved.resolved is True
        assert resolved.tier == ResolutionTier.EMBEDDING
        assert resolved.region_name == "Upper East Side-Carnegie Hill"

    def test_tier4_embedding_ambiguous_when_enabled(self, db, monkeypatch):
        region_type = "test"
        r1 = _create_region(db, region_type=region_type, region_name="Upper East Side", parent_region="Manhattan")
        r2 = _create_region(db, region_type=region_type, region_name="Upper West Side", parent_region="Manhattan")

        resolver = LocationResolver(db, region_code=region_type)
        candidates = [
            {"region_id": str(r1.id), "region_name": r1.region_name, "borough": r1.parent_region, "similarity": 0.83},
            {"region_id": str(r2.id), "region_name": r2.region_name, "borough": r2.parent_region, "similarity": 0.82},
        ]
        monkeypatch.setattr(resolver.embedding_service, "get_candidates", lambda *_args, **_kwargs: candidates)
        monkeypatch.setattr(resolver.embedding_service, "pick_best_or_ambiguous", lambda _c: (None, candidates))

        resolved = resolver.resolve("central park", enable_semantic=True)

        assert resolved.method == "embedding"
        assert resolved.requires_clarification is True
        assert resolved.tier == ResolutionTier.EMBEDDING
        assert resolved.candidates is not None
        assert len(resolved.candidates) >= 2

    def test_tier5_llm_cached_alias_short_circuits(self, db, monkeypatch):
        region_type = "test"
        region = _create_region(
            db,
            region_type=region_type,
            region_name="Upper East Side-Carnegie Hill",
            parent_region="Manhattan",
        )

        resolver = LocationResolver(db, region_code=region_type)

        # First call: LLM resolves + caches.
        monkeypatch.setattr(
            resolver.embedding_service,
            "get_candidates",
            lambda *_args, **_kwargs: [],
        )
        monkeypatch.setattr(
            resolver.llm_service,
            "resolve",
            lambda **_kwargs: {
                "neighborhoods": [region.region_name],
                "confidence": 0.92,
                "reason": "landmark mapping",
            },
        )

        first = resolver.resolve("museum mile", enable_semantic=True)
        assert first.method == "llm"
        assert first.tier == ResolutionTier.LLM
        assert first.resolved is True
        assert first.region_name == region.region_name

        # Second call: should use cached alias row, not call LLM again.
        monkeypatch.setattr(
            resolver.llm_service,
            "resolve",
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called when cached")),
        )
        second = resolver.resolve("museum mile", enable_semantic=True)
        assert second.method == "llm"
        assert second.tier == ResolutionTier.LLM
        assert second.resolved is True
        assert second.region_name == region.region_name
